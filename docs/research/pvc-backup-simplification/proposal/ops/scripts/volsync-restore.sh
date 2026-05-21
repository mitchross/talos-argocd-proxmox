#!/usr/bin/env bash
# Restore an app's PVC from a VolSync snapshot. Port of mirceanton/home-ops
# .scripts/volsync-restore.sh, with the Flux pieces swapped for Argo:
#
#   suspend HelmRelease  ->  argocd app set <app> --sync-policy none
#                            (or annotate argocd.argoproj.io/skip-reconcile: "true")
#   resume HelmRelease   ->  argocd app set <app> --sync-policy automated
#                            and trigger refresh
#
# RD name convention (matches chart vb.rdName): metadata.name == <PVC>-dst.
#
# Usage: volsync-restore.sh <PVC> <NAMESPACE> <TRIGGER> [RFC3339_TIMESTAMP]
# TS optional: if set, restores the snapshot taken at-or-before that time
# (passed to RD as spec.kopia.restoreAsOf). Without it: latest snapshot.
#
# REQUIRES: argocd CLI logged in. App name is assumed == ${NS}.

set -euo pipefail

CYAN='\033[0;36m'; RED='\033[0;31m'; NC='\033[0m'
log()  { printf "${CYAN}[volsync-restore]${NC} %s\n" "$*"; }
fail() { printf "${RED}[volsync-restore]${NC} %s\n" "$*" >&2; exit 1; }

PVC="${1:?pvc name required}"
NS="${2:?namespace required}"
TRIGGER="${3:?trigger id required}"
TS="${4:-}"
APP="${NS}"
RD="${PVC}-dst"

command -v argocd >/dev/null || fail "argocd CLI not on PATH"

# --- 1. Suspend the Argo app so it does not re-create the Deployment ---
log "suspending Argo auto-sync for ${APP}"
argocd app set "${APP}" --sync-policy none >/dev/null

# --- 2. Scale workloads owning the PVC down to 0 ---
# Naive: scale every Deployment + StatefulSet in the namespace. Adjust if
# your app has unrelated workloads in the same namespace.
log "scaling Deployments/StatefulSets in ${NS} to 0"
kubectl -n "${NS}" get deploy,sts -o name | while read -r r; do
  kubectl -n "${NS}" scale "${r}" --replicas=0
done

log "waiting up to 120s for pods to terminate"
for _ in $(seq 1 60); do
  count=$(kubectl -n "${NS}" get pods --no-headers 2>/dev/null | wc -l)
  [ "${count}" -eq 0 ] && break
  sleep 2
done

# --- 3. Patch ReplicationDestination to trigger restore ---
if [ -n "${TS}" ]; then
  log "patching RD ${NS}/${RD} with manual=${TRIGGER} restoreAsOf=${TS}"
  kubectl -n "${NS}" patch replicationdestination "${RD}" --type merge \
    -p "{\"spec\":{\"trigger\":{\"manual\":\"${TRIGGER}\"},\"kopia\":{\"restoreAsOf\":\"${TS}\"}}}" >/dev/null
else
  log "patching RD ${NS}/${RD} with manual=${TRIGGER} (latest)"
  kubectl -n "${NS}" patch replicationdestination "${RD}" --type merge \
    -p "{\"spec\":{\"trigger\":{\"manual\":\"${TRIGGER}\"}}}" >/dev/null
fi

# --- 4. Poll until restore reports the trigger and the mover succeeded ---
log "waiting for mover"
while :; do
  last=$(kubectl -n "${NS}" get replicationdestination "${RD}" \
    -o jsonpath='{.status.lastManualSync}' 2>/dev/null || true)
  status=$(kubectl -n "${NS}" get replicationdestination "${RD}" \
    -o jsonpath='{.status.latestMoverStatus.result}' 2>/dev/null || true)
  log "  lastManualSync=${last:-<none>}  moverResult=${status:-<pending>}"
  [ "${last}" = "${TRIGGER}" ] && break
  sleep 5
done

result=$(kubectl -n "${NS}" get replicationdestination "${RD}" \
  -o jsonpath='{.status.latestMoverStatus.result}')
if [ "${result}" != "Successful" ]; then
  kubectl -n "${NS}" get replicationdestination "${RD}" \
    -o jsonpath='{.status.latestMoverStatus.logs}' | tail -50 >&2
  fail "mover result=${result}, not Successful — NOT resuming app (leaving suspended for inspection)"
fi
log "restore complete"

# --- 5. Resume Argo auto-sync and force a reconcile ---
log "resuming Argo auto-sync + hard refresh"
argocd app set "${APP}" --sync-policy automated >/dev/null
argocd app sync "${APP}" >/dev/null
log "done"
