# AI model catalog

**Two models. One local, one paid.** Everything else is wiring.

| Model | Where it runs | Cost | Reached as |
|---|---|---|---|
| `qwen3.8-27b` | your two RTX 3090s | free | `qwen3.8-27b` |
| `deepseek-flash` | OpenRouter, external | paid | `deepseek-flash` |
| `pi-auto` | picks between the two | mixed | `pi-auto` |

`pi-auto` is not a third model. It is a LiteLLM router that chooses one of the
other two per request.

## Who owns the GPUs

| Backend | Replicas | Cards | Model | Status |
|---|---:|---:|---|---|
| vLLM | `1` | **2** | `qwen3.8-27b` | production |
| NInfer | `0` | 1 | `qwen3.8-ninfer` | parked |
| ComfyUI / SwarmUI | `0` | 1 | image generation | parked |

Both cards belong to vLLM. Other GPU workloads stay parked.
[GPU scale-swap](gpu-scale-swap.md) owns the procedure.

## Local: Qwen3.8-27B FP8

| Property | Value |
|---|---|
| Engine | stock vLLM `v0.29.0`, pinned digest |
| Weights | official `Qwen/Qwen3.8-27B-FP8`, pinned revision |
| Placement | TP=2, two RTX 3090s, no CPU offload |
| KV / recurrent state | FP8 E4M3 / float16 |
| Context ceiling | 262,144 tokens |
| Concurrency | two sequences sharing the KV pool |
| Vision | one image per request, video disabled |
| Reasoning | off / low / medium / xhigh; **xhigh** default |
| Speculation | disabled |
| Power | 220 W per card |

262K is a server ceiling, not a promise of two simultaneous full-length
sessions. Use `xhigh` by default for the accuracy-first policy; select `medium`
or `low` for less reasoning, or explicitly turn thinking off. More reasoning
can consume more time and tokens; a quality improvement is not guaranteed.

Exact flags, rollout checks and rollback live in the
[vLLM runbook](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/ai/vllm/README.md).

## Paid: DeepSeek Flash

| Property | Value |
|---|---|
| Gateway model | `deepseek-flash` |
| LiteLLM upstream | `openrouter/~deepseek/deepseek-flash-latest` |
| Context | 1,048,576 tokens |
| Output | 943,718 upstream; Pi deliberately caps 32,768 |
| Input | text and images |
| Reasoning | low / high / max |
| Planning estimate | $0.30/M in, $1.20/M out, $0.03/M cached |

**Prompts leave the homelab.** They reach an OpenRouter-selected provider and
cost money. The `latest` alias can change target, limits and price with no Git
edit, so treat the price above as an estimate. OpenRouter billed usage is
authoritative.

## The router

| Property | Value |
|---|---|
| Gateway model | `pi-auto` |
| Implementation | **beta** `auto_router/complexity_router`, LiteLLM `v1.102.1` |
| Local tiers | `SIMPLE`, `MEDIUM` → `qwen3.8-27b-auto` |
| Paid tiers | `COMPLEX` → `deepseek-flash` at `high`; `REASONING` at `max` |
| Classifier | local Qwen, greedy, 64 tokens |
| Classified | every request |
| Classifier failure | `deepseek-flash` |
| Stuck-task rescue | `stall_escalation_enabled`, 3 repeats in 6 tool calls |
| Manual override | `LITELLM ESCALATE` in a message bumps one tier |
| Session pin | off |
| Context escalation | on; an oversized prompt moves up rather than truncating |
| Advertised limits | 229,376 input plus 32,768 output |

One request goes to one backend. This is model selection, not response
splitting. Local generation inherits xhigh from vLLM; the classifier still
explicitly disables thinking. DeepSeek's high/max settings are unchanged.

`qwen3.8-27b-auto` is the same vLLM backend as `qwen3.8-27b` under a second
name, so the router's DeepSeek failover reaches `pi-auto` alone and never the
shared route every other client uses.

Full behaviour: [Pi agent guide](pi-agent-local-dev.md).

## Wiring

| Path | Endpoint |
|---|---|
| Apps → gateway | `http://litellm-service.litellm.svc.cluster.local:4000/v1` |
| Workstation → gateway | `https://litellm.vanillax.me/v1` |
| Gateway → Qwen | `http://vllm-service.vllm.svc.cluster.local:8080/v1` |
| Gateway → DeepSeek | OpenRouter, key from 1Password |
| Direct diagnostics | `llama.vanillax.me`, `vllm.vanillax.me` |

Auth is a namespace-local ExternalSecret from `litellm/master_key`.

Every declared LLM consumer uses LiteLLM: Open WebUI, Perplexica/Vane,
Presenton, SurfSense, HolmesGPT, Hindsight, Project Nomad, ComfyUI's vision
bridge, WorldMonitor, Deal Scout, Karakeep and News Reader. They all
stay on local Qwen unless their model is changed explicitly.

Direct vLLM callers bypass Langfuse. Applications must use the authenticated
gateway to appear in telemetry.

## Storage

A Git-pinned manifest records revision, size and SHA-256 for all 77 checkpoint
artifacts. A download hook writes the TrueNAS archive; a cache-sync hook
verifies and copies it to local NVMe. The serving init container requires the
readiness marker and a complete file inventory, so serving never starts against
a partial copy. Interrupted downloads resume; corrupt copies fail verification.

## Rollback

vLLM is the only GPU inference backend. Revert the commit and let the staging
hooks re-run against the retained cache.
