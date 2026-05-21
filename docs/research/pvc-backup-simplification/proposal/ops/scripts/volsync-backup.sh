#!/usr/bin/env bash
# Trigger a manual VolSync backup for an app and wait for completion.
# Port of mirceanton/home-ops .scripts/volsync-backup.sh (no shape changes
# needed — patches the ReplicationSource the same way).
#
# Usage: volsync-backup.sh <PVC> <NAMESPACE> <TRIGGER>
# TRIGGER is a unique identifier (timestamp); the Taskfile wrapper generates it.
#
# RS name convention (matches chart vb.rsName): metadata.name == <PVC>.

set -euo pipefail

CYAN='\033[0;36m'; RED='\033[0;31m'; NC='\033[0m'
log()  { printf "${CYAN}[volsync-backup]${NC} %s\n" "$*"; }
fail() { printf "${RED}[volsync-backup]${NC} %s\n" "$*" >&2; exit 1; }

PVC="${1:?pvc name required}"
NS="${2:?namespace required}"
TRIGGER="${3:?trigger id required}"

log "patching ReplicationSource ${NS}/${PVC} with manual trigger=${TRIGGER}"
kubectl -n "${NS}" patch replicationsource "${PVC}" --type merge \
  -p "{\"spec\":{\"trigger\":{\"manual\":\"${TRIGGER}\"}}}" >/dev/null

log "waiting for mover to complete (this can take a while on first run)"
while :; do
  last=$(kubectl -n "${NS}" get replicationsource "${PVC}" \
    -o jsonpath='{.status.lastManualSync}' 2>/dev/null || true)
  status=$(kubectl -n "${NS}" get replicationsource "${PVC}" \
    -o jsonpath='{.status.latestMoverStatus.result}' 2>/dev/null || true)
  log "  lastManualSync=${last:-<none>}  moverResult=${status:-<pending>}"
  [ "${last}" = "${TRIGGER}" ] && break
  sleep 5
done

result=$(kubectl -n "${NS}" get replicationsource "${PVC}" \
  -o jsonpath='{.status.latestMoverStatus.result}')
if [ "${result}" != "Successful" ]; then
  kubectl -n "${NS}" get replicationsource "${PVC}" \
    -o jsonpath='{.status.latestMoverStatus.logs}' | tail -50 >&2
  fail "mover result=${result}, not Successful"
fi
log "backup complete"
