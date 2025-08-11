# AI Orchestrator

Purpose: Automatically manages GPU allocation between Ollama (primary) and ComfyUI (opportunistic) using Prometheus metrics.

## Policy
- Ollama runs with 2 GPUs for performance.
- When Ollama idle (low request rate + low GPU util) it is reduced to 1 GPU to free 1 GPU.
- While Ollama at 1 GPU and ComfyUI shows activity, ComfyUI is scaled to 1 replica (1 GPU).
- If Ollama demand rises again, ComfyUI is scaled down and Ollama scales back to 2 GPUs.

## High-Level Architecture
```
+------------------+        Prometheus        +--------------------+
|  DCGM Exporter   |  (GPU Util, Metrics)     |  HTTP Metrics Apps |
| (per GPU node)   +------------------------->+ (Ollama/ComfyUI)   |
+---------+--------+                          +-----+--------------+
          |                                         |
          |  GPU Util (DCGM_FI_DEV_GPU_UTIL)        | Request Rates
          v                                         v
                   +--------------------------------+
                   |        AI Orchestrator         |
                   |  (Alpine shell, curl + kubectl + jq)
                   +--------------------------------+
                         |            |
               Patch resources       Scale replicas
                         |            |
                         v            v
                +----------------+  +----------------+
                |  Ollama Deploy |  | ComfyUI Deploy |
                +----------------+  +----------------+
```

## Flow (State Transitions)
```
          +-----------------------------+
          | Ollama in Dual (2 GPUs)     |
          +--------------+--------------+
                         | (Idle: low req + low util)
                         v
          +-----------------------------+
          | Ollama Single (1 GPU)       |
          +------+-----------+----------+
                 |           |
     (Demand↑)   |           | (ComfyUI Activity)
                 |           v
                 |   +-------------------------+
                 |   | ComfyUI Active (1 GPU)  |
                 |   +------------+------------+
                 |                |
                 |   (ComfyUI Idle|  (Ollama Demand↑)
                 |    or Timeout) |
                 |                v
                 |        (Preempt -> scale ComfyUI 0)
                 +----------------> (Return to Dual)
```

Legend:
- Idle condition: GPU util < 10% AND Ollama req rate < 0.02 r/s.
- Demand condition: Ollama req rate >= 0.02 r/s.
- ComfyUI activity: ComfyUI req rate >= 0.02 r/s.

## Important: NVIDIA Time-Slicing vs Physical GPUs
- If the device plugin exposes time-sliced GPUs, your node may show "40" allocatable for 2x3090 (20 slices per card). In that mode, nvidia.com/gpu: 1 = one slice, not a full GPU.
- The orchestrator assumes physical-GPU semantics (2=two GPUs, 1=one GPU). To match that intent, either:
  1) Disable time-slicing in the NVIDIA device plugin (recommended for max performance), OR
  2) Change the orchestrator patch counts to 40 (dual/full) and 20 (single) to align with your slice configuration.

> Tip: Run `kubectl get nodes -o custom-columns=NAME:.metadata.name,GPUS:.status.allocatable.'nvidia\.com/gpu'` to see if you are in slice mode.

## Components
- ConfigMap `ai-orchestrator-config`: thresholds and PromQL queries.
- Deployment `ai-orchestrator`: alpine shell loop using curl + jq + kubectl.
- RBAC: scoped Roles in `ollama` and `comfyui` namespaces to patch deployments.
- PodSecurity: both Ollama and ComfyUI run as non-root with fsGroup for PVC writes.

## Metrics / Queries
Adjust queries in `configmap.yaml` to match actual metric names if different:
- `ollamaRequestRate`: request rate for Ollama API.
- `comfyuiRequestRate`: HTTP hits to ComfyUI.
- `gpuUtil`: average GPU utilization (from DCGM exporter). Template includes %NODE_NAME% substitution.

## Annotations
- Ollama: `ai.orchestrator/gpu-mode` used for bookkeeping.
- ComfyUI: `ai.orchestrator/gpu-required: "1"` is honored (only starts when one GPU is free).

## Idle Criteria
Default:
- GPU utilization <10%
- Request rate <0.02 req/sec (≈1 req per 50s)
- Conditions true at poll time triggers downgrade.

## Scaling Actions
- Patch Ollama resources nvidia.com/gpu 2→1 or 1→2 (or 40→20/20→40 in slice mode).
- Scale ComfyUI replicas 0↔1.

## How to Test Quickly
- Orchestrator running:
  - `kubectl -n ai-orchestrator logs deploy/ai-orchestrator --tail=100`
- Prometheus up (clean JSON):
  - `kubectl -n prometheus-stack run tmp-curl --rm -i --restart=Never --image=curlimages/curl:8.8.0 -- sh -lc 'curl -s "http://kube-prometheus-stack-prometheus.prometheus-stack:9090/api/v1/query?query=up" | jq -r .status'`
- Check GPU counts and replicas:
  - `kubectl -n ollama get deploy ollama -o jsonpath='{.spec.template.spec.containers[0].resources.limits[nvidia.com/gpu]}' ; echo`
  - `kubectl -n comfyui get deploy comfyui -o jsonpath='{.spec.replicas}' ; echo`

## ArgoCD Drift Handling
Dynamic patches cause ArgoCD drift. Configure generated Applications to ignore:
- Ollama container[0] resources (GPU changes)
- ComfyUI spec.replicas (and optionally resources)

Example (ApplicationSet): see repo `infrastructure/controllers/argocd/apps/my-apps-appset.yaml`.

## Sync Waves (Target)
1. Monitoring (Prometheus + DCGM) : wave 0
2. GPU Device Plugin              : wave 1
3. Core AI Apps (Ollama/ComfyUI)  : wave 2
4. Orchestrator                   : wave 3

If you stay with time-slicing and want me to switch orchestrator to patch 40/20 instead of 2/1, say the word.

