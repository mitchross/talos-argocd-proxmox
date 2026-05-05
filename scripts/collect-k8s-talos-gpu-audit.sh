#!/usr/bin/env bash
set -u
set -o pipefail

TS="$(date -u +%Y%m%dT%H%M%SZ)"
CTX="$(kubectl config current-context 2>/dev/null || echo unknown-context)"
SAFE_CTX="$(echo "$CTX" | tr -c 'A-Za-z0-9_.-' '_')"
OUT="./k8s-talos-gpu-audit-${SAFE_CTX}-${TS}"

mkdir -p "$OUT"

log() {
  echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$OUT/run.log"
}

run() {
  local name="$1"
  shift
  local file="$OUT/${name}.txt"

  {
    echo "### ${name}"
    echo "### UTC: $(date -u --iso-8601=seconds)"
    echo "### CMD: $*"
    echo
    bash -lc "$*"
  } >"$file" 2>&1

  log "wrote ${file}"
}

run_json() {
  local name="$1"
  shift
  local file="$OUT/${name}.json"

  {
    bash -lc "$*"
  } >"$file" 2>&1

  log "wrote ${file}"
}

log "collecting Kubernetes/Talos/GPU audit into $OUT"
log "kubectl context: $CTX"

# Basic cluster state
run "00-context-version" '
kubectl config current-context
echo
kubectl version
echo
kubectl cluster-info
'

run "01-nodes-wide" '
kubectl get nodes -o wide
echo
kubectl get nodes --show-labels
'

run_json "02-nodes-json" '
kubectl get nodes -o json
'

run "03-top-nodes" '
kubectl top nodes 2>/dev/null || echo "metrics-server unavailable or kubectl top failed"
'

run "04-top-pods" '
kubectl top pods -A --sort-by=memory 2>/dev/null || echo "metrics-server unavailable or kubectl top failed"
'

# ArgoCD app health / sync waves
run "10-argocd-apps" '
kubectl get applications -n argocd \
  -o custom-columns=NAME:.metadata.name,WAVE:.metadata.annotations.argocd\\.argoproj\\.io/sync-wave,SYNC:.status.sync.status,HEALTH:.status.health.status,PROJECT:.spec.project \
  2>/dev/null || echo "No ArgoCD Application CRs found or argocd namespace unavailable"
'

run_json "11-argocd-apps-json" '
kubectl get applications -n argocd -o json 2>/dev/null || true
'

# PVC / storage / backup state
run "20-pv-pvc" '
kubectl get pv -o wide
echo
kubectl get pvc -A -o wide --show-labels
'

run "21-volsync" '
kubectl get replicationsource,replicationdestination -A -o wide 2>/dev/null || true
'

run "22-longhorn" '
kubectl -n longhorn-system get pods -o wide 2>/dev/null || true
echo
kubectl -n longhorn-system get volumes.longhorn.io -o wide 2>/dev/null || true
echo
kubectl -n longhorn-system get replicas.longhorn.io -o wide 2>/dev/null || true
echo
kubectl -n longhorn-system get settings.longhorn.io 2>/dev/null || true
'

run "23-cnpg" '
kubectl get clusters.postgresql.cnpg.io -A -o wide 2>/dev/null || true
echo
kubectl get backups.postgresql.cnpg.io -A -o wide 2>/dev/null || true
echo
kubectl get scheduledbackups.postgresql.cnpg.io -A -o wide 2>/dev/null || true
'

# GPU node discovery
run "30-gpu-nodes" '
kubectl get nodes -l nvidia.com/gpu.present=true -o wide
echo
kubectl get nodes -l nvidia.com/gpu.present=true --show-labels
'

GPU_NODES="$(kubectl get nodes -l nvidia.com/gpu.present=true -o jsonpath='{range .items[*]}{.metadata.name}{" "}{end}' 2>/dev/null || true)"

if [ -z "${GPU_NODES// }" ]; then
  log "no nodes found with label nvidia.com/gpu.present=true"
else
  log "GPU nodes: $GPU_NODES"

  for node in $GPU_NODES; do
    safe_node="$(echo "$node" | tr -c 'A-Za-z0-9_.-' '_')"

    run "31-pods-on-gpu-node-${safe_node}" "
kubectl get pods -A -o wide --field-selector spec.nodeName=${node}
"

    run "32-describe-gpu-node-${safe_node}" "
kubectl describe node ${node}
"

    run "33-gpu-node-allocated-${safe_node}" "
kubectl describe node ${node} | sed -n '/Allocated resources:/,/Events:/p'
"
  done
fi

# Which pods request GPUs?
run "34-pods-requesting-gpu" '
if command -v jq >/dev/null 2>&1; then
  kubectl get pods -A -o json | jq -r "
    .items[]
    | . as \$pod
    | [
        \$pod.metadata.namespace,
        \$pod.metadata.name,
        \$pod.spec.nodeName,
        ([ \$pod.spec.containers[]?.resources.requests[\"nvidia.com/gpu\"] // 0 ] | map(tonumber? // 0) | add),
        ([ \$pod.spec.containers[]?.resources.limits[\"nvidia.com/gpu\"] // 0 ] | map(tonumber? // 0) | add)
      ]
    | select(.[3] != 0 or .[4] != 0)
    | @tsv
  " | column -t
else
  echo "jq missing; raw grep fallback:"
  kubectl get pods -A -o yaml | grep -B20 -A20 "nvidia.com/gpu" || true
fi
'

# NVIDIA operator / powerlimit pods
run "40-nvidia-pods" '
kubectl get pods -A -o wide | grep -Ei "nvidia|gpu|llama|comfy" || true
echo
kubectl -n gpu-operator get pods -o wide 2>/dev/null || true
'

run "41-nvidia-operator-resources" '
kubectl get clusterpolicy -A -o wide 2>/dev/null || true
echo
kubectl get runtimeclass 2>/dev/null || true
echo
kubectl get nodes -o jsonpath="{range .items[*]}{.metadata.name}{\"\t\"}{.status.allocatable.nvidia\.com/gpu}{\"\t\"}{.status.capacity.nvidia\.com/gpu}{\"\n\"}{end}" 2>/dev/null || true
'

# Pick nvidia-powerlimit pod(s) and run nvidia-smi inside them
POWERLIMIT_PODS="$(kubectl -n gpu-operator get pods -l app.kubernetes.io/name=nvidia-powerlimit -o jsonpath='{range .items[*]}{.metadata.name}{" "}{end}' 2>/dev/null || true)"

# Fallback if label differs
if [ -z "${POWERLIMIT_PODS// }" ]; then
  POWERLIMIT_PODS="$(kubectl -n gpu-operator get pods -o name 2>/dev/null | grep -E 'nvidia-powerlimit' | sed 's#pod/##' | tr '\n' ' ' || true)"
fi

if [ -z "${POWERLIMIT_PODS// }" ]; then
  log "no nvidia-powerlimit pods found in gpu-operator"
else
  log "nvidia-powerlimit pods: $POWERLIMIT_PODS"

  for pod in $POWERLIMIT_PODS; do
    safe_pod="$(echo "$pod" | tr -c 'A-Za-z0-9_.-' '_')"

    run "50-nvidia-smi-${safe_pod}" "
kubectl -n gpu-operator exec ${pod} -- bash -lc '
set +e
echo \"### hostname\"
hostname
echo
echo \"### nvidia-smi\"
nvidia-smi
echo
echo \"### query gpu\"
nvidia-smi --query-gpu=index,uuid,name,pstate,power.draw,power.limit,power.default_limit,power.max_limit,memory.used,memory.total,utilization.gpu,temperature.gpu --format=csv
echo
echo \"### compute apps\"
nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name,used_memory --format=csv
echo
echo \"### pmon one sample\"
nvidia-smi pmon -c 1
'
"

    run "51-nvidia-pid-cgroups-${safe_pod}" "
kubectl -n gpu-operator exec ${pod} -- bash -lc '
set +e
echo \"### PIDs from nvidia-smi and their cgroups\"
for pid in \$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | grep -E \"^[0-9]+\" | sort -u); do
  echo
  echo \"================================================================================\"
  echo \"PID: \$pid\"
  echo \"CMDLINE:\"
  tr \"\\0\" \" \" < /proc/\$pid/cmdline 2>/dev/null || true
  echo
  echo
  echo \"CGROUP:\"
  cat /proc/\$pid/cgroup 2>/dev/null || true
  echo
  echo \"ENV_HINTS:\"
  tr \"\\0\" \"\\n\" < /proc/\$pid/environ 2>/dev/null | grep -Ei \"KUBERNETES|POD|NAMESPACE|NVIDIA|CUDA|LLAMA|COMFY\" || true
done
'
"
  done
fi

# Container ID to pod mapping
run "52-containerid-to-pod-map" '
if command -v jq >/dev/null 2>&1; then
  kubectl get pods -A -o json | jq -r "
    .items[] as \$pod
    | \$pod.status.containerStatuses[]?
    | [
        \$pod.metadata.namespace,
        \$pod.metadata.name,
        .name,
        \$pod.spec.nodeName,
        (.containerID // \"\")
      ]
    | @tsv
  " | sed "s#containerd://##g; s#docker://##g; s#cri-o://##g" | column -t
else
  echo "jq missing; cannot produce clean containerID map"
fi
'

# AI namespaces likely relevant to your repo
run "60-ai-workloads" '
for ns in llama-cpp comfyui open-webui searxng gpu-operator; do
  echo
  echo "################################################################################"
  echo "namespace: $ns"
  echo "################################################################################"
  kubectl -n "$ns" get all -o wide 2>/dev/null || true
  echo
  kubectl -n "$ns" get pvc -o wide 2>/dev/null || true
  echo
  kubectl -n "$ns" get events --sort-by=.lastTimestamp 2>/dev/null | tail -80 || true
done
'

# Cluster events
run "90-events" '
kubectl get events -A --sort-by=.lastTimestamp | tail -300
'

# Optional Talos visibility if talosctl is configured and node IPs are reachable
if command -v talosctl >/dev/null 2>&1; then
  run "95-talosctl-version" '
talosctl version 2>/dev/null || true
'

  if [ -n "${GPU_NODES// }" ]; then
    for node in $GPU_NODES; do
      safe_node="$(echo "$node" | tr -c 'A-Za-z0-9_.-' '_')"
      node_ip="$(kubectl get node "$node" -o jsonpath='{.status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null || true)"

      if [ -n "$node_ip" ]; then
        run "96-talos-processes-gpu-node-${safe_node}" "
talosctl -n ${node_ip} processes 2>/dev/null | grep -Ei 'llama|comfy|python|nvidia|containerd|kubelet' || true
"

        run "97-talos-dmesg-gpu-node-${safe_node}" "
talosctl -n ${node_ip} dmesg 2>/dev/null | grep -Ei 'nvidia|vfio|pci|aer|gpu|error|reset|iommu' | tail -300 || true
"
      fi
    done
  fi
else
  echo "talosctl not installed or not in PATH" > "$OUT/95-talosctl-skipped.txt"
  log "skipped talosctl section"
fi

# Package it
tarball="${OUT}.tar.gz"
tar -czf "$tarball" "$OUT"

log "done"
log "tarball: $tarball"

echo
echo "Created:"
echo "  $OUT"
echo "  $tarball"
