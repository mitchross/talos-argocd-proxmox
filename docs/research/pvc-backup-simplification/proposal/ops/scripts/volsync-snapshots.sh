#!/usr/bin/env bash
# List Kopia snapshots for an app's volsync repo.
# Port of mirceanton/home-ops .scripts/volsync-snapshots.sh
#   - Restic image -> Kopia (perfectra1n/volsync's mover image carries kopia)
#   - secret name <APP>-volsync-secret -> our chart's volsync-<PVC> secret
#
# Usage: volsync-snapshots.sh <PVC> <NAMESPACE>
#
# The Taskfile `volsync:snapshots` wrapper handles arg validation; this
# script assumes both args are set.

set -euo pipefail

CYAN='\033[0;36m'; RED='\033[0;31m'; NC='\033[0m'
log()  { printf "${CYAN}[volsync-snapshots]${NC} %s\n" "$*"; }
fail() { printf "${RED}[volsync-snapshots]${NC} %s\n" "$*" >&2; exit 1; }

PVC="${1:?pvc name required}"
NS="${2:?namespace required}"
SECRET="volsync-${PVC}"
POD="volsync-snapshots-${PVC}"

kubectl -n "${NS}" get secret "${SECRET}" >/dev/null 2>&1 \
  || fail "secret ${NS}/${SECRET} missing (is the chart deployed for ${PVC}?)"

log "spawning throwaway kopia pod ${NS}/${POD}"
kubectl -n "${NS}" run "${POD}" \
  --image=ghcr.io/perfectra1n/volsync:v0.17.11 \
  --restart=Never \
  --command -- kopia snapshot list --json --all \
  --overrides='{"spec":{"containers":[{"name":"'"${POD}"'","envFrom":[{"secretRef":{"name":"'"${SECRET}"'"}}]}]}}' \
  >/dev/null

# Poll up to 60s for pod to terminate
for _ in $(seq 1 30); do
  phase=$(kubectl -n "${NS}" get pod "${POD}" -o jsonpath='{.status.phase}' 2>/dev/null || true)
  case "${phase}" in
    Succeeded) break ;;
    Failed)    kubectl -n "${NS}" logs "${POD}" >&2; kubectl -n "${NS}" delete pod "${POD}" --wait=false; fail "kopia pod failed" ;;
    "")        sleep 2 ;;
    *)         sleep 2 ;;
  esac
done

kubectl -n "${NS}" logs "${POD}"
kubectl -n "${NS}" delete pod "${POD}" --wait=false >/dev/null
