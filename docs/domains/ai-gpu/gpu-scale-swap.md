# GPU scale-swap runbook

How to change which workload owns the two RTX 3090s — safely, via git, in one
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
| **vLLM** (default app inference, TP=2) | **2** | `1` | `my-apps/ai/vllm/deployment.yaml` |
| **llama-cpp** (preset bank, multimodal) | 1 | `0` | `my-apps/ai/llama-cpp/deployment.yaml` |
| **ComfyUI** (image gen — see note below) | 1 | `0` | `my-apps/ai/comfyui/deployment.yaml` |
| **SwarmUI** (image gen — see note below) | 1 | `0` | `my-apps/ai/swarmui/deployment.yaml` |
| llmfit (batch benchmark **Jobs**, not always-on) | 1 or 2 | n/a | `my-apps/ai/llmfit/` |

A valid target state is any set of `replicas: 1` rows whose **card total ≤ 2**.
Working combos: vLLM alone (2 cards) · llama-cpp + one image-gen app (1+1) ·
llama-cpp alone · one image-gen app alone.

> **Image gen: ComfyUI vs SwarmUI — decision pending.** ComfyUI's manifest is
> marked *retired, replaced by SwarmUI* (SwarmUI self-starts its own ComfyUI),
> but the docs' vision→image wiring still describes ComfyUI and no final call
> has been made. Both sit at `replicas: 0`; neither is canonical yet. If you
> need image gen today, pick one, bring it up per the procedure below, and
> scale it back to 0 when done.

## The procedure

1. **Pick the target state** from the truth table (card total ≤ 2).
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
kubectl -n vllm get pods; kubectl -n llama-cpp get pods
kubectl -n comfyui get pods; kubectl -n swarmui get pods

# Who actually holds the cards (run inside the power-limit admin DaemonSet,
# which sees all GPUs without consuming an allocation)
kubectl -n gpu-power-limit exec ds/gpu-power-limit -- nvidia-smi

# Endpoint answers (from any in-cluster pod)
curl -s http://vllm-service.vllm.svc.cluster.local:8080/v1/models
```

## Side effects to expect

- **Scaling llama-cpp to 0** → the external route `llama.vanillax.me` returns
  "no healthy upstream" until it's scaled back up. Expected, not an outage.
- **Scaling vLLM to 0** → OpenWebUI, Perplexica, Project NOMAD, and Karakeep
  lose their inference backend (they all point at vLLM / `qwen3.6-27b`).
  Treat vLLM-down as "apps degraded" and keep the window short.
- **ComfyUI's vision→image workflow needs llama-cpp too** — it calls the
  llama-cpp multimodal endpoint for vision. Bringing up ComfyUI alone leaves
  its vision/caption nodes failing against a dead service. That combo is a
  **two-app bring-up**: ComfyUI (1 card) + llama-cpp (1 card) = both cards.
- **llmfit Jobs** need free cards to schedule; the dual-GPU job can only run
  when everything else is at 0.

## Don'ts

- Don't `kubectl scale` (selfHeal reverts it — commit the value).
- Don't set `NVIDIA_VISIBLE_DEVICES`/`CUDA_VISIBLE_DEVICES` in pod env — they
  bypass the device plugin's accounting (sole exception: the `gpu-power-limit`
  admin DaemonSet).
- Don't switch a GPU Deployment to `RollingUpdate` — Recreate is what
  guarantees the old pod releases the card (and avoids RWO Multi-Attach).
- Don't delete the 290 W power cap to "fix" slowness — tune
  `POWER_LIMIT_WATTS` in `my-apps/ai/gpu-power-limit/` instead.

Related: [model catalog](model-catalog.md) (who points at what) ·
[3090 LLM optimization](3090-llm-optimization.md) (why vLLM TP=2 is the
default) · `my-apps/ai/CLAUDE.md` (GPU workload pattern).
