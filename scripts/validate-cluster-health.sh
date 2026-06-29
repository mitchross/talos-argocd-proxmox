#!/usr/bin/env bash
# validate-cluster-health.sh — Read-only post-rollout health snapshot.
#
# Designed to be run after each node's `qm set` resize during the Phase 1
# memory right-sizing rollout. Prints a one-screen summary plus full
# detail sections so you can confirm the cluster is healthy before
# advancing to the next node.
#
# Read-only: no kubectl drain/uncordon/edit, no qm calls. Uses metrics-server
# (kubectl top) where available; sections gracefully degrade if a CRD or
# operator is absent.
#
# Run from repo root or anywhere with kubectl context pointed at the cluster:
#   ./scripts/validate-cluster-health.sh
#   ./scripts/validate-cluster-health.sh --node talos-prod-cluster-workers-48ddwn
#
# Exit code: 0 if no immediate red flags, 1 if any of the smoke checks
# (NotReady nodes, ArgoCD Degraded apps, Longhorn Degraded volumes,
# Pending/CrashLoopBackOff/OOMKilled pods) are non-empty.

set -uo pipefail

NODE_FILTER=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --node)
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

run() { # run "label" -- cmd args...
  local label="$1"; shift
  [[ "$1" == "--" ]] && shift
  hdr "$label"
  "$@" 2>&1 || true
}

count_lines() { awk 'NR>0{c++} END{print c+0}'; }

# ─────────────────────────────────────────────
# Smoke summary (top of report)
# ─────────────────────────────────────────────
hdr "SMOKE SUMMARY"

NOT_READY=$(kubectl get nodes --no-headers 2>/dev/null \
  | awk '$2!="Ready"{print $1" "$2}')
if [[ -n "$NOT_READY" ]]; then
  fail "NotReady nodes:"; echo "$NOT_READY"; ISSUES=$((ISSUES+1))
else
  echo "Nodes: all Ready"
fi

BAD_PODS=$(kubectl get pods -A --no-headers 2>/dev/null \
  | awk '$4 ~ /Pending|CrashLoopBackOff|OOMKilled|Evicted|ImagePullBackOff|Error|ErrImagePull/ {print}')
if [[ -n "$BAD_PODS" ]]; then
  fail "Problem pods:"; echo "$BAD_PODS" | head -30
  echo "(showing first 30; total $(echo "$BAD_PODS" | count_lines))"
  ISSUES=$((ISSUES+1))
else
  echo "Pods: no Pending/CrashLoopBackOff/OOMKilled/Evicted/ImagePullBackOff"
fi

if kubectl get applications.argoproj.io -n argocd >/dev/null 2>&1; then
  ARGO_BAD=$(kubectl get applications.argoproj.io -n argocd \
    -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.sync.status}{"\t"}{.status.health.status}{"\n"}{end}' 2>/dev/null \
    | awk -F'\t' '$2!="Synced" || ($3!="Healthy" && $3!="")')
  if [[ -n "$ARGO_BAD" ]]; then
    warn "ArgoCD apps not Synced+Healthy:"
    echo "$ARGO_BAD" | column -t -s $'\t'
    ISSUES=$((ISSUES+1))
  else
    echo "ArgoCD: all apps Synced+Healthy"
  fi
fi

if kubectl get volumes.longhorn.io -n longhorn-system >/dev/null 2>&1; then
  LH_BAD=$(kubectl get volumes.longhorn.io -n longhorn-system \
    -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.state}{"\t"}{.status.robustness}{"\n"}{end}' 2>/dev/null \
    | awk -F'\t' '$3!="healthy" && $3!=""')
  if [[ -n "$LH_BAD" ]]; then
    warn "Longhorn volumes not healthy:"
    echo "$LH_BAD" | column -t -s $'\t'
    ISSUES=$((ISSUES+1))
  else
    echo "Longhorn: all volumes healthy"
  fi
fi

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
    | sort | uniq -c | sort -rn || echo "(longhorn CRDs not available)"
'

run "kopiur snapshot policies + schedules" -- bash -c '
  kubectl get snapshotpolicy,snapshotschedule -A 2>/dev/null \
    || echo "(kopiur CRDs not available)"
'

run "kopiur snapshots (latest per source)" -- bash -c '
  kubectl get snapshot.kopiur.home-operations.com -A 2>/dev/null \
    || echo "(kopiur CRDs not available)"
'

# ─────────────────────────────────────────────
# Databases
# ─────────────────────────────────────────────
run "CNPG clusters" -- bash -c '
  kubectl get clusters.postgresql.cnpg.io -A 2>/dev/null \
    || echo "(cnpg CRDs not available)"
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

echo
if [[ "$ISSUES" -gt 0 ]]; then
  fail "RESULT: $ISSUES smoke check(s) flagged. Review sections above before proceeding."
  exit 1
fi
bold "RESULT: smoke checks clean. Safe to proceed to the next node."
exit 0
