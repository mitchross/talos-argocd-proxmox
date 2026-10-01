#!/usr/bin/env bash
# validate-cluster-health.sh — Read-only post-rollout health snapshot.
#
# Prints a one-screen summary plus full detail sections, so you can confirm the
# cluster is healthy after a node change (resize, reboot, upgrade) before moving on.
#
# Read-only: no kubectl drain/uncordon/edit, no qm calls. Uses metrics-server
# (kubectl top) where available; sections gracefully degrade if a CRD or
# operator is absent.
#
# Run from repo root or anywhere with kubectl context pointed at the cluster:
#   ./scripts/validate-cluster-health.sh
#   ./scripts/validate-cluster-health.sh --node talos-prod-cluster-workers-48ddwn
#
# Exit: 0 HEALTHY (checked smoke signals only), 1 UNHEALTHY, 2 UNKNOWN/check failed.
# Kubernetes nodes, pods, ArgoCD Applications and Longhorn volumes are required
# in this repository. Missing APIs, access errors and invalid responses are UNKNOWN.
# This snapshot does not authorize destructive operations.

set -uo pipefail

NODE_FILTER=""
SUMMARY_ONLY=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --summary-only)
      SUMMARY_ONLY=true
      shift
      ;;
    --node)
      [[ $# -ge 2 ]] || { echo "--node requires a name" >&2; exit 2; }
      NODE_FILTER="$2"
      shift 2
      ;;
    -h|--help)
      sed -n '2,20p' "$0"
      exit 0
      ;;
    *)
      echo "unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

bold()  { printf '\033[1m%s\033[0m\n' "$*"; }
hdr()   { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
warn()  { printf '\033[1;33m%s\033[0m\n' "$*"; }
fail()  { printf '\033[1;31m%s\033[0m\n' "$*"; }

ISSUES=0
FAILED=0

run() { # run "label" -- cmd args...
  local label="$1"; shift
  [[ "$1" == "--" ]] && shift
  hdr "$label"
  "$@" 2>&1 || warn "UNKNOWN: diagnostic query failed (not a required smoke check)"
}

# ─────────────────────────────────────────────
# Smoke summary (top of report)
# ─────────────────────────────────────────────
hdr "SMOKE SUMMARY"

check() {
  local label="$1" resource="$2" namespace="$3" filter="$4"
  local response bad
  local -a args=(get "$resource" -o json --request-timeout=10s)
  if [[ "$namespace" == ALL ]]; then args+=(-A)
  elif [[ -n "$namespace" ]]; then args+=(-n "$namespace"); fi
  if ! response=$(kubectl "${args[@]}" 2>&1); then
    fail "UNKNOWN: $label query failed: $response"
    FAILED=$((FAILED+1)); return
  fi
  if ! jq -e '.items | type == "array" and length > 0' >/dev/null 2>&1 <<< "$response"; then
    fail "UNKNOWN: $label response is invalid or unexpectedly empty"
    FAILED=$((FAILED+1)); return
  fi
  if ! bad=$(jq -r "$filter" <<< "$response" 2>&1); then
    fail "UNKNOWN: $label response could not be evaluated: $bad"
    FAILED=$((FAILED+1)); return
  fi
  if [[ -n "$bad" ]]; then
    fail "UNHEALTHY: $label"; printf '%s\n' "$bad" | head -30
    ISSUES=$((ISSUES+1))
  else
    echo "HEALTHY: $label — no checked smoke issues found"
  fi
}

check Nodes nodes "" '
  .items[] | select((any(.status.conditions[]?; .type == "Ready" and .status == "True") | not)) |
  .metadata.name + " NotReady or missing Ready condition"'
check Pods pods ALL '
  .items[] | select(.status.phase == null or .status.phase == "Pending" or .status.phase == "Failed" or
    any(.status.containerStatuses[]?, .status.initContainerStatuses[]?;
      (.state.waiting.reason // "") | test("CrashLoopBackOff|ImagePullBackOff|ErrImagePull|Error")) or
    any(.status.containerStatuses[]?, .status.initContainerStatuses[]?;
      .state.terminated.reason == "OOMKilled")) |
  (.metadata.namespace + "/" + .metadata.name + " " + (.status.phase // "unknown phase"))'
check ArgoCD applications.argoproj.io argocd '
  .items[] | select(.status.sync.status != "Synced" or .status.health.status != "Healthy" or
    .status.operationState.phase == "Failed" or .status.operationState.phase == "Error") |
  .metadata.name + " " + (.status.sync.status // "unknown sync") + " " +
    (.status.health.status // "unknown health") + " " + (.status.operationState.phase // "no operation")'
check Longhorn volumes.longhorn.io longhorn-system '
  .items[] | select(.status.robustness != "healthy") |
  .metadata.name + " " + (.status.robustness // "unknown robustness")'

result() {
  echo
  if [[ "$FAILED" -gt 0 ]]; then
    fail "RESULT: UNKNOWN — $FAILED required check(s) failed; $ISSUES smoke issue group(s) observed."
    echo "Snapshot only; this does not authorize destructive operations."
    return 2
  elif [[ "$ISSUES" -gt 0 ]]; then
    fail "RESULT: UNHEALTHY — $ISSUES smoke issue group(s) observed."
    echo "Snapshot only; investigate causes before taking action."
    return 1
  fi
  bold "RESULT: HEALTHY — no checked smoke issues found."
  echo "Snapshot only; this does not authorize destructive operations."
  return 0
}

if "$SUMMARY_ONLY"; then result; exit $?; fi

# ─────────────────────────────────────────────
# Node detail
# ─────────────────────────────────────────────
run "Nodes (wide)" -- kubectl get nodes -o wide

run "Allocatable per node" -- bash -c '
  kubectl get nodes -o json \
    | jq -r ".items[] | [.metadata.name, .status.allocatable.cpu, .status.allocatable.memory] | @tsv" \
    | column -t
'

run "kubectl top nodes" -- kubectl top nodes --use-protocol-buffers=false

# ─────────────────────────────────────────────
# Top consumers
# ─────────────────────────────────────────────
run "Top 30 pods by memory (cluster-wide)" -- bash -c '
  kubectl top pods -A --use-protocol-buffers=false --sort-by=memory 2>/dev/null \
    | head -31
'

run "Top 30 pods by CPU (cluster-wide)" -- bash -c '
  kubectl top pods -A --use-protocol-buffers=false --sort-by=cpu 2>/dev/null \
    | head -31
'

if [[ -n "$NODE_FILTER" ]]; then
  run "Pods on $NODE_FILTER" -- kubectl get pods -A \
    --field-selector spec.nodeName="$NODE_FILTER" -o wide
fi

# ─────────────────────────────────────────────
# Storage / replication
# ─────────────────────────────────────────────
run "Longhorn volume summary (state x robustness)" -- bash -c '
  kubectl get volumes.longhorn.io -n longhorn-system -o json 2>/dev/null \
    | jq -r ".items[] | [.status.state, .status.robustness] | @tsv" \
    | sort | uniq -c | sort -rn || echo "UNKNOWN: Longhorn diagnostic query failed"
'

run "kopiur snapshot policies + schedules" -- bash -c '
  kubectl get snapshotpolicy,snapshotschedule -A 2>/dev/null \
    || echo "UNKNOWN: kopiur diagnostic query failed"
'

run "kopiur snapshots (latest per source)" -- bash -c '
  kubectl get snapshot.kopiur.home-operations.com -A 2>/dev/null \
    || echo "UNKNOWN: kopiur diagnostic query failed"
'

# ─────────────────────────────────────────────
# GPU
# ─────────────────────────────────────────────
GPU_NODE=$(kubectl get nodes -l gpu-worker=true -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
if [[ -n "$GPU_NODE" ]]; then
  run "GPU node ($GPU_NODE) describe — Allocated resources" -- bash -c "
    kubectl describe node '$GPU_NODE' \
      | sed -n '/Allocated resources/,/Events/p'
  "
  # shellcheck disable=SC2016 # Expanded by the nested diagnostic shell.
  run "nvidia-smi from nvidia-driver-daemonset (if present)" -- bash -c '
    POD=$(kubectl -n gpu-operator get pod -l app=nvidia-driver-daemonset \
      -o jsonpath="{.items[0].metadata.name}" 2>/dev/null)
    if [[ -n "$POD" ]]; then
      kubectl -n gpu-operator exec "$POD" -- nvidia-smi 2>/dev/null
    else
      POD=$(kubectl get pods -A -l app=nvidia-powerlimit \
        -o jsonpath="{.items[0].metadata.namespace}/{.items[0].metadata.name}" 2>/dev/null)
      if [[ -n "$POD" ]]; then
        ns="${POD%/*}"; name="${POD#*/}"
        kubectl -n "$ns" exec "$name" -- nvidia-smi 2>/dev/null
      else
        echo "(no nvidia-* pod found to exec into)"
      fi
    fi
  '
fi

# ─────────────────────────────────────────────
# Recent warning events
# ─────────────────────────────────────────────
run "Recent Warning events (last 60)" -- bash -c '
  kubectl get events -A --sort-by=.lastTimestamp \
    --field-selector type=Warning 2>/dev/null \
    | tail -60
'

result
exit $?
