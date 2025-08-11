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
                   |  (BusyBox loop, curl + kubectl)|
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

## Sequence (Idle Downgrade)
```
User inactivity -> Metrics reflect low util & requests -> Orchestrator
poll cycle -> JSONPatch Ollama GPUs 2→1 -> One GPU freed.
```

## Sequence (ComfyUI Opportunistic Start)
```
User hits ComfyUI -> Request metric rises -> Orchestrator sees
Ollama at 1 GPU -> scale comfyui replicas 0→1 (gets 1 GPU).
```

## Sequence (Ollama Reclaim)
```
New Ollama traffic while ComfyUI active -> Orchestrator detects demand
-> scale comfyui 1→0 -> patch Ollama 1→2.
```

## Components
- ConfigMap `ai-orchestrator-config`: thresholds and PromQL queries.
- Deployment `ai-orchestrator`: busybox shell loop using curl + jq + kubectl.
- RBAC: scoped Roles in `ollama` and `comfyui` namespaces to patch deployments.

## Metrics / Queries
Adjust queries in `configmap.yaml` to match actual metric names if different:
- `ollamaRequestRate`: request rate for Ollama API.
- `comfyuiRequestRate`: HTTP hits to ComfyUI.
- `gpuUtil`: average GPU utilization (from DCGM exporter).

## Annotations
Ollama Deployment annotated with:
- `ai.orchestrator/gpu-mode: dual|single` (bookkeeping)
ComfyUI annotated with:
- `ai.orchestrator/managed: true`

## Idle Criteria
Default:
- GPU utilization <10%
- Request rate <0.02 req/sec (≈1 req per 50s) over 5m window
- Conditions true at poll time triggers downgrade.

## Scaling Actions
- Patch Ollama resources nvidia.com/gpu 2→1 or 1→2.
- Scale ComfyUI replicas 0↔1.

## Limitations / Future Improvements
- Prototype shell loop; rewrite in Go/Python for reliability (state, cooldowns, metrics batching).
- Add per-action cooldown annotations to avoid flapping.
- Validate metric names existence before acting.
- Use dedicated ServiceAccount with least privileges (already scoped) + networkPolicy.
- Optionally expose a manual override (HTTP endpoint) to force modes.

## ArgoCD Drift Handling
Dynamic patches cause ArgoCD drift. Configure generated Applications to ignore:
- Ollama container[0] resources (GPU changes)
- ComfyUI spec.replicas

Example `ignoreDifferences` (added via ApplicationSet template):
```
ignoreDifferences:
- group: apps
  kind: Deployment
  name: ollama
  namespace: ollama
  jsonPointers:
  - /spec/template/spec/containers/0/resources
- group: apps
  kind: Deployment
  name: comfyui
  namespace: comfyui
  jsonPointers:
  - /spec/replicas
```

## Sync Waves (Target)
1. Monitoring (Prometheus + DCGM) : wave 0
2. GPU Device Plugin              : wave 1
3. Core AI Apps (Ollama/ComfyUI)  : wave 2
4. Orchestrator                   : wave 3

Ensure waves updated in ApplicationSets or via per-application annotations.

