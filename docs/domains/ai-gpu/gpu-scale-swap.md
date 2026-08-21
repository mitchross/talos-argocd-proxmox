# GPU scale-swap runbook

How to change which workload owns the sole RTX 3090 — safely, via git, in one
commit. This is the canonical procedure; the one-liners scattered in the
manifests all point here.

## The rule

GPU workloads are **mutually-exclusive whole-card**: time-slicing is disabled,
every GPU pod requests whole `nvidia.com/gpu` cards, and each Deployment uses
`strategy: Recreate`. **Never two pods on the cards at once.** You don't
"deploy" a GPU app — you **swap** which one holds the cards by flipping
committed `replicas:` values.

Two things make this safe by construction:

1. **The scheduler enforces exclusivity.** A newly scaled-up pod sits
   `Pending` until the outgoing pod actually releases its card(s).
   `0/2 nodes available ... Insufficient nvidia.com/gpu` during a swap is
   **normal**, not a broken scheduler — it clears when the old pod finishes
   terminating.
2. **ArgoCD selfHeal reverts manual scaling.** `kubectl scale` is undone
   within minutes. The committed value in git is the only real switch.

## Card truth table

| App | Cards | `replicas` in git (current) | File |
|---|---|---|---|
| **llama-cpp** (Qwen 3.8 UD-IQ4_XS, active) | **1** | `1` | `my-apps/ai/llama-cpp/deployment.yaml` |
| **vLLM** (Qwen 3.8 W4A16, rollback) | 1 | `0` | `my-apps/ai/vllm/deployment.yaml` |
| **NInfer-3090** (Qwen 3.8 .ninfer, parked candidate) | 1 | `0` | `my-apps/ai/ninfer/deployment.yaml` |
| **ComfyUI** (image gen — see note below) | 1 | `0` | `my-apps/ai/comfyui/deployment.yaml` |
| **SwarmUI** (image gen — see note below) | 1 | `0` | `my-apps/ai/swarmui/deployment.yaml` |
| llmfit (batch benchmark **Jobs**, not always-on) | 1 or 2 | n/a | `my-apps/ai/llmfit/` |

> **Single-card reality (2026-08-21, permanent):** the chassis holds one RTX
> 3090. A valid state has exactly one `replicas: 1` GPU Deployment.

There are no valid two-workload combinations. The dual-GPU llmfit Job cannot
run on this chassis.

> **Image gen: ComfyUI vs SwarmUI — decision pending.** ComfyUI's manifest is
> marked *retired, replaced by SwarmUI* (SwarmUI self-starts its own ComfyUI),
> but the docs' vision→image wiring still describes ComfyUI and no final call
> has been made. Both sit at `replicas: 0`; neither is canonical yet. If you
> need image gen today, pick one, bring it up per the procedure below, and
> scale it back to 0 when done.

## The procedure

1. **Pick the target state** from the truth table (exactly one active row).
2. **Edit the `replicas:` values in ONE commit** — outgoing app(s) to `0`,
   incoming app(s) to `1`, in their `deployment.yaml` files. One commit means
   ArgoCD applies both sides together and the scheduler sequences the rest.
3. **Push.** The my-apps AppSet (wave 6) syncs automatically; no manual sync
   needed.
4. **Wait out the handover.** The incoming pod stays `Pending` while the
   outgoing pod terminates (model unload can take ~a minute). Do **not**
   "fix" the Pending state — see rule 1 above.
5. **Verify:**

```bash
# Old pod gone, new pod Running
kubectl -n llama-cpp get pods; kubectl -n vllm get pods
kubectl -n comfyui get pods; kubectl -n swarmui get pods

# Who actually holds the cards (run inside the power-limit admin DaemonSet,
# which sees all GPUs without consuming an allocation)
kubectl -n gpu-operator exec ds/nvidia-powerlimit -- nvidia-smi

# Endpoint answers (from any in-cluster pod)
curl -s http://llama-cpp-service.llama-cpp.svc.cluster.local:8080/v1/models
```

## Side effects to expect

- **Scaling llama-cpp to 0** → every Qwen consumer loses inference, including
  Open WebUI, Perplexica, and Deal Scout. Treat it as an app-degraded window.
- **ComfyUI's vision→image workflow needs llama-cpp too** — it calls the
  llama-cpp multimodal endpoint for vision. Bringing up ComfyUI alone leaves
  its vision/caption nodes failing against a dead Service. With one card, that
  combined workflow cannot run concurrently.
- **llmfit Jobs** need the active server parked first; only single-GPU Jobs fit.

## Don'ts

- Don't `kubectl scale` (selfHeal reverts it — commit the value).
- Don't set `NVIDIA_VISIBLE_DEVICES`/`CUDA_VISIBLE_DEVICES` in pod env — they
  bypass the device plugin's accounting (sole exception: the infrastructure
  `nvidia-powerlimit` admin DaemonSet).
- Don't switch a GPU Deployment to `RollingUpdate` — Recreate is what
  guarantees the old pod releases the card (and avoids RWO Multi-Attach).
- Don't delete the 200 W power cap to "fix" slowness — tune
  `POWER_LIMIT_WATTS` in
  `infrastructure/controllers/nvidia-gpu-operator/powerlimit-daemonset.yaml`
  instead. The cap is set by the house circuit, not by the efficiency knee;
  raising it needs an electrical decision, not just a performance one.

Related: [model catalog](model-catalog.md) (who points at what) ·
[3090 LLM optimization](3090-llm-optimization.md) · `my-apps/ai/CLAUDE.md`
(GPU workload pattern).
