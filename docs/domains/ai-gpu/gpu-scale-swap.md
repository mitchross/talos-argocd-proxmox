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

| App | Cards | `replicas` in git (declared) | File |
|---|---:|---:|---|
| **llama.cpp** (Qwen3.8-27B UD-Q4_K_XL, rollback) | 1 | `0` | `my-apps/ai/llama-cpp/deployment.yaml` |
| **vLLM** (official Qwen3.8-27B FP8) | **2** | `1` | `my-apps/ai/vllm/deployment.yaml` |
| **NInfer-3090** (Qwen3.8 .ninfer, parked candidate) | 1 | `0` | `my-apps/ai/ninfer/deployment.yaml` |
| **ComfyUI** | 1 | `0` | `my-apps/ai/comfyui/deployment.yaml` |
| **SwarmUI** | 1 | `0` | `my-apps/ai/swarmui/deployment.yaml` |
| llmfit (batch benchmark Jobs) | 1 | n/a | `my-apps/ai/llmfit/` |

The declared FP8 profile owns both cards. It takes effect after merge and
Argo reconciliation; there is no spare GPU while vLLM is running. Sum
`replicas × requested cards` across active workloads; the total must not
exceed two. Replica overrides in each `kustomization.yaml` are authoritative.

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
curl -fsS https://vllm.vanillax.me/v1/models
```

Both LAN hostnames route to vLLM. Existing in-cluster llama.cpp URLs alias
the vLLM Service. A rollback must change replica ownership and service/route
wiring together; see the [model catalog](model-catalog.md).

## Side effects to expect

- Scaling vLLM to 0 removes the active chat/vision backend for Open WebUI,
  Perplexica, SurfSense, LiteLLM, Hindsight, Presenton, HolmesGPT, Project Nomad,
  and any Pi.dev sessions using the cluster endpoint.
- ComfyUI's vision-to-image helper depends on the active chat backend. While vLLM owns both
  cards, ComfyUI cannot run alongside it.
- Any GPU llmfit Job requires the two-card server parked first.

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
