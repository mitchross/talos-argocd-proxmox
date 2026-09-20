# GPU scale-swap runbook

**You do not deploy a GPU app. You swap which one holds the card**, by flipping
committed replica counts in one commit.

## The rule

GPU workloads are mutually-exclusive whole-card: time-slicing off, every pod
requests whole `nvidia.com/gpu` cards, every Deployment uses `strategy:
Recreate`. **Never two pods on a card.**

Two things make this safe:

1. The scheduler enforces it. A scaled-up pod sits `Pending` until the outgoing
   pod releases its card. `Insufficient nvidia.com/gpu` during a swap is normal.
2. ArgoCD selfHeal reverts `kubectl scale`. The committed value is the only real
   switch.

## Card truth table

| App | Cards | `replicas` in git | File |
|---|---:|---:|---|
| **vLLM** (Qwen3.8-27B FP8) | **2** | `1` | `my-apps/ai/vllm/deployment.yaml` |
| NInfer-3090 | 1 | `0` | `my-apps/ai/ninfer/deployment.yaml` |
| ComfyUI | 1 | `0` | `my-apps/ai/comfyui/deployment.yaml` |
| SwarmUI | 1 | `0` | `my-apps/ai/swarmui/deployment.yaml` |
| llmfit (batch Jobs) | 1 | n/a | `my-apps/ai/llmfit/` |

vLLM owns both cards, so **there is no spare GPU while it runs**. Sum
`replicas × cards` across active workloads; the total must not exceed two.
Replica overrides in each `kustomization.yaml` are authoritative.

## The procedure

About 10 minutes plus reconciliation.

1. Pick the target state from the truth table.
2. Edit outgoing and incoming replica counts in **one commit**.
3. Open a PR. Merge is the operator's call.
4. Wait for the outgoing pod to release the card. Do not "fix" a `Pending`
   incoming pod.
5. Verify:

```bash
kubectl -n vllm get pods
kubectl -n comfyui get pods
kubectl -n swarmui get pods
kubectl -n gpu-operator exec ds/nvidia-powerlimit -- nvidia-smi
curl -fsS https://vllm.vanillax.me/v1/models
```

Expect the incoming pod Running, two cards at 220 W, and the endpoint serving.

Both LAN hostnames route to vLLM. A swap changes replica ownership **and**
service/route wiring together.

## What breaks while vLLM is at 0

Open WebUI, Perplexica, SurfSense, LiteLLM, Hindsight, Presenton, HolmesGPT,
Project Nomad and any Pi session on the cluster endpoint lose their backend.

ComfyUI's vision-to-image helper needs the chat backend, so it cannot run
alongside vLLM. Any GPU llmfit Job needs the two-card server parked first.

## Don'ts

- Don't `kubectl scale` — selfHeal reverts it.
- Don't set `NVIDIA_VISIBLE_DEVICES` or `CUDA_VISIBLE_DEVICES` in workload pods.
  The `nvidia-powerlimit` DaemonSet is the intentional exception.
- Don't switch a GPU Deployment to `RollingUpdate`. `Recreate` releases the
  whole card cleanly and avoids RWO Multi-Attach.
- Don't raise the **220 W** cap to chase throughput. `POWER_LIMIT_WATTS` lives
  in `infrastructure/controllers/nvidia-gpu-operator/powerlimit-daemonset.yaml`;
  changing it is an electrical decision.

Related: [model catalog](model-catalog.md) ·
[3090 LLM optimization](3090-llm-optimization.md)
