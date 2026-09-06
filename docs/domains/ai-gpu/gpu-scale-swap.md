# GPU scale-swap runbook

How to change which workloads own the two RTX 3090s — safely, via git, in one
commit. This is the canonical procedure; the one-liners scattered in the
manifests all point here.

## The rule

GPU workloads are **mutually-exclusive whole-card**: time-slicing is disabled,
every GPU pod requests whole `nvidia.com/gpu` cards, and each Deployment uses
`strategy: Recreate`. **Never two pods on the card at once.** You don't
"deploy" a GPU app — you **swap** which one holds the card by flipping
committed replica counts.

Two things make this safe by construction:

1. **The scheduler enforces exclusivity.** A newly scaled-up pod sits
   `Pending` until the outgoing pod actually releases its card.
   `Insufficient nvidia.com/gpu` during a swap is normal.
2. **ArgoCD selfHeal reverts manual scaling.** `kubectl scale` is undone.
   The committed value in git is the only real switch.

## Card truth table

| App | Cards | `replicas` in git (current) | File |
|---|---:|---:|---|
| **llama.cpp** (Qwen3.8-27B UD-Q4_K_XL, active) | **1** | `1` | `my-apps/ai/llama-cpp/deployment.yaml` |
| **vLLM** (Qwen3.8-27B W4A16, rollback) | 1 | `0` | `my-apps/ai/vllm/deployment.yaml` |
| **NInfer-3090** (Qwen3.8 .ninfer, parked candidate) | 1 | `0` | `my-apps/ai/ninfer/deployment.yaml` |
| **ComfyUI** | 1 | `0` | `my-apps/ai/comfyui/deployment.yaml` |
| **SwarmUI** | 1 | `0` | `my-apps/ai/swarmui/deployment.yaml` |
| llmfit (batch benchmark Jobs) | 1 | n/a | `my-apps/ai/llmfit/` |

The chassis has two RTX 3090s. The current steady state uses one for llama.cpp
and leaves one spare. Sum `replicas × requested cards` across active workloads;
the total must not exceed two. A two-card Flash Next trial must first park the
production backend. See [the feasibility study](flash-next-dual-3090.md).

## The procedure

1. Pick the target state from the truth table.
2. Edit outgoing and incoming committed replica counts in **one PR/commit**.
3. Push a PR; the user merges it, then ArgoCD reconciles the new state.
4. Wait for the outgoing pod to release the GPU; do not "fix" the incoming
   pod while it is Pending.
5. Verify:

```bash
kubectl -n llama-cpp get pods
kubectl -n vllm get pods
kubectl -n comfyui get pods
kubectl -n swarmui get pods

# Card owner / live cap.
kubectl -n gpu-operator exec ds/nvidia-powerlimit -- nvidia-smi

# Active production endpoint.
curl -s http://llama-cpp-service.llama-cpp.svc.cluster.local:8080/v1/models
```

The LAN compatibility hostname `https://vllm.vanillax.me/v1` currently routes
to llama.cpp too; the canonical in-cluster endpoint is `llama-cpp-service`.

## Side effects to expect

- Scaling llama.cpp to 0 removes the active chat/vision backend for Open WebUI,
  Perplexica, SurfSense, LiteLLM, Hindsight, Presenton, HolmesGPT, Project Nomad,
  and any Pi.dev sessions using the cluster endpoint.
- ComfyUI's vision-to-image helper depends on the active chat backend. With one
  card, ComfyUI and the chat backend cannot both own the GPU simultaneously.
- A two-card llmfit Job requires the active server parked first. A one-card
  Job can use the spare, but concurrent load invalidates comparison benchmarks.

## Don'ts

- Don't `kubectl scale`; selfHeal reverts it.
- Don't set `NVIDIA_VISIBLE_DEVICES`/`CUDA_VISIBLE_DEVICES` in GPU workload pods.
  The infrastructure `nvidia-powerlimit` DaemonSet is the intentional exception.
- Don't switch a GPU Deployment to `RollingUpdate`; `Recreate` releases the
  whole card cleanly and avoids RWO Multi-Attach.
- Don't raise the **220 W** production power cap just to chase throughput.
  `POWER_LIMIT_WATTS` lives in
  `infrastructure/controllers/nvidia-gpu-operator/powerlimit-daemonset.yaml`;
  changing it is an electrical/circuit decision.

Related: [model catalog](model-catalog.md) ·
[3090 LLM optimization](3090-llm-optimization.md) · `my-apps/ai/CLAUDE.md`
