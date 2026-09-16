# AI model catalog

Current local and external model inventory plus app wiring. Official FP8 was
verified live on both cards on 2026-09-06. DeepSeek Flash is a paid OpenRouter
route, not a second local GPU model. `pi-auto` is a LiteLLM virtual model that
chooses between those two routes; it is not a third model. The medium Qwen
fallback is the Git-declared policy; reverify it after vLLM or client-policy changes. The
[capacity audit](3090-llm-optimization.md) records runtime evidence and limits.

## Declared GPU ownership

| Backend | Replicas | Cards per pod | Served model | Status |
|---|---:|---:|---|---|
| vLLM | `1` | **2** | `qwen3.8-27b` | Official FP8 production |
| NInfer | `0` | 1 | `qwen3.8-ninfer` | Parked evaluation |
| ComfyUI / SwarmUI | `0` | 1 | Image generation | Parked |

Both RTX 3090s belong to vLLM. Other GPU workloads must remain parked;
[GPU scale-swap](gpu-scale-swap.md) owns the procedure. Flash Next remains
[a researched alternative](flash-next-dual-3090.md).

## Official Qwen3.8-27B FP8

| Property | Value |
|---|---|
| Engine | stock vLLM `v0.29.0`, pinned digest |
| Weights | official `Qwen/Qwen3.8-27B-FP8`, pinned revision |
| Placement | TP=2, two RTX 3090s, no CPU weight offload |
| KV / recurrent state | FP8 E4M3 / float16 |
| Context ceiling | 262,144 tokens |
| Concurrency | two sequences sharing the KV pool |
| Vision | native encoder; one image per request, video disabled |
| Reasoning | explicit off / low / medium / xhigh; medium default |
| Speculation | disabled; MTP deferred until long-session fixes are validated |
| Power | 220 W per card |

The official checkpoint is about 30.89 GB (28.77 GiB). RTX 3090 uses an
Ampere-compatible weight-only FP8 path. Host RAM is loading/transport headroom,
not additional GPU KV capacity. 262K is a server ceiling, not a promise of two
simultaneous full-length sessions. AutoRound INT4/W4A8 is a later speed A/B.

The [canonical vLLM runbook](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/ai/vllm/README.md)
owns exact flags, source references, reasoning/sampling examples, rollout
checks and rollback. The capacity audit distinguishes smoke checks from
performance and sustained quality measurements.

Normal coding uses explicit `medium`; `low` is for lighter requests and
`xhigh` is opt-in for difficult tasks. Preservation remains enabled for agents;
stateless chats may disable it. Thinking-off requests send both flags false
and the separate non-thinking sampler documented in the canonical runbook.
Open WebUI normalizes generic `high` to medium; Pi exposes only valid efforts.

## DeepSeek Flash through OpenRouter and LiteLLM

| Property | Value |
|---|---|
| Hosting | OpenRouter-selected provider; external to this cluster |
| Gateway model | `deepseek-flash` |
| LiteLLM upstream | `openrouter/~deepseek/deepseek-flash-latest` |
| Pi provider | `vanillax-openrouter/deepseek-flash` |
| Model context metadata | 1,048,576 tokens; current top-provider limit is 1,000,000 |
| Output metadata | 393,216 tokens upstream; Pi deliberately caps 32,768 |
| Input | text and images |
| Reasoning | enabled by default at high; alias advertises low / high / max |
| Conservative Pi price | $0.03/M cached input, $0.30/M input, $1.20/M output |

DeepSeek Flash consumes no local GPU capacity. Pi reaches it through the same
authenticated LiteLLM endpoint used for Qwen, but LiteLLM then calls OpenRouter
with `OPENROUTER_API_KEY` from the `litellm` ExternalSecret. Prompts therefore
leave the homelab, may reach an OpenRouter-selected provider, and incur API
cost. The `latest` alias may change target, limits, supported inputs, providers,
and prices without a Git edit. The static Pi and LiteLLM metadata uses the
2026-09-16 peak time-window rate rather than the lower base rate; actual
OpenRouter responses and LiteLLM/Langfuse spend are authoritative.
[OpenRouter's live model catalog](https://openrouter.ai/api/v1/models) and
[LiteLLM's OpenRouter provider guide](https://docs.litellm.ai/docs/providers/openrouter)
own the moving upstream contract.

## Pi Auto Router

| Property | Value |
|---|---|
| Gateway model | `pi-auto` |
| LiteLLM implementation | beta `auto_router/complexity_router` in pinned `v1.101.0` |
| Local tiers | `SIMPLE`, `MEDIUM` → `qwen3.8-27b` |
| Paid tiers | `COMPLEX`, `REASONING` → `deepseek-flash` |
| Empty/default route | `qwen3.8-27b` |
| Classification boundary | each new human turn; continuation/tool calls keep that turn's model |
| Session pin | off; a later human turn may select the other backend |
| Advertised limits | 229,376 input plus 32,768 output; Pi uses a 262,144-token total window |

The built-in heuristic adds no classifier model call. One request is served by
one backend; this is complexity selection, not response splitting or a
Qwen-to-cloud failure fallback. A complex or reasoning turn sends the full
submitted context to OpenRouter and incurs DeepSeek Flash cost. The forced
`qwen3.8-27b` and `deepseek-flash` routes remain available when automatic
selection is inappropriate.
[LiteLLM Auto Routing](https://docs.litellm.ai/docs/proxy/auto_routing) documents
the beta classifier and decision metadata.

## Storage and staging

A Git-pinned manifest records revision, size and SHA-256 for all 77 checkpoint
artifacts. A download hook writes the TrueNAS archive, then a cache-sync hook
verifies and copies it to local NVMe. The serving init container requires the
matching readiness marker and complete file inventory; serving stays offline
from local storage. Interrupted downloads resume, while corrupt copies fail
verification. Existing AutoRound and GGUF files remain for comparison/rollback.

NAS free space and export write permissions remain rollout checks; local NVMe
had approximately 123 GiB free before staging. Follow the vLLM runbook to
inspect hooks, health, vision, tools, reasoning and long-context behavior.

## App wiring

- gateway models: local `qwen3.8-27b`, external `deepseek-flash`, and virtual `pi-auto`
- application gateway: `http://litellm-service.litellm.svc.cluster.local:4000/v1`
- workstation gateway: `https://litellm.vanillax.me/v1`
- authentication: namespace-local ExternalSecret from `litellm/master_key`
- Qwen upstream / diagnostics: `http://vllm-service.vllm.svc.cluster.local:8080/v1`
- DeepSeek upstream: OpenRouter using `open-router/api-key-open-router` from 1Password

All Git-declared local LLM consumers use LiteLLM: Open WebUI, Perplexica/Vane,
Presenton, SurfSense, HolmesGPT, Hindsight, Project Nomad, ComfyUI's vision
bridge, WorldMonitor, Keep, Deal Scout, Karakeep, News Reader and n8n workflows.
Parked replicas and disabled workflows remain parked/disabled. Keep's provider
appends `/v1/completions` itself, so its configured gateway URL omits `/v1`.
The [observability runbook](ai-observability.md) covers authentication,
persisted settings, ingestion verification and rollback.

`llama.vanillax.me` and `vllm.vanillax.me` are direct diagnostic routes onto the
same vLLM Service. Applications must use the
authenticated gateway to appear in Langfuse. Direct benchmark probes intentionally
bypass gateway telemetry and must not be mistaken for application traffic.

## Pi.dev

Pi defaults to `vanillax-vllm/qwen3.8-27b` through
`https://litellm.vanillax.me/v1`. `pi-flash` creates a forced DeepSeek-only
session; `pi-withflash` requests `vanillax-auto/pi-auto`, allowing LiteLLM to
select Qwen or DeepSeek Flash per human turn. The same repo-owned extension
supplies session metadata to all Pi providers but rewrites sampling only for
direct Qwen requests. Open
WebUI and the other Git-declared apps continue to use local Qwen unless their
model is explicitly changed.

All three Pi routes collect LiteLLM metrics and Langfuse AI observations; direct
vLLM callers bypass that gateway. See [AI observability](ai-observability.md)
for verification and fallback. The [workstation guide](pi-agent-local-dev.md)
owns the three provider blocks, launchers, automatic-routing boundary, Qwen
reasoning and sampling, compaction, validation, and rollback. Start a new
session when a possible OpenRouter turn should not inherit local-only conversation.

## Rollback

vLLM is the only GPU inference backend. Revert the offending commit through Git
and let the staging hooks re-run against the retained cache; follow the canonical
vLLM runbook for verification.
