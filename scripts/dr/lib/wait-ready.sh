#!/usr/bin/env bash
# Block until a CNPG Cluster reports readyInstances=1 or timeout expires.
#
# Usage: wait-ready.sh <cluster-name> <namespace> <timeout-seconds>
# Exits 0 on Ready, 1 on timeout, 2 on persistent error state.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/common.sh"

[[ $# -eq 3 ]] || die "usage: wait-ready.sh <cluster> <namespace> <timeout-sec>"
CLUSTER="$1"; NS="$2"; TIMEOUT="$3"

deadline=$(( $(date +%s) + TIMEOUT ))
last_phase=""

while (( $(date +%s) < deadline )); do
  ready=$(kubectl -n "$NS" get cluster "$CLUSTER" -o jsonpath='{.status.readyInstances}' 2>/dev/null || echo "")
  phase=$(kubectl -n "$NS" get cluster "$CLUSTER" -o jsonpath='{.status.phase}' 2>/dev/null || echo "?")
  if [[ "$phase" != "$last_phase" ]]; then
    log "[$CLUSTER] phase='$phase' ready='$ready'"
    last_phase="$phase"
  fi
  if [[ "$ready" == "1" && "$phase" == "Cluster in healthy state" ]]; then
    ok "[$CLUSTER] Ready"
    exit 0
  fi
  sleep 10
done

warn "[$CLUSTER] timeout after ${TIMEOUT}s — final phase='$last_phase'"
exit 1
