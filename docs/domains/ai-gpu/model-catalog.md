# AI model catalog

Git-declared model inventory and app wiring. The official FP8 cutover takes
effect after the user merges and ArgoCD reconciles; runtime verification is
still required. The last observed live backend was one-card llama.cpp.

## Declared GPU ownership

| Backend | Replicas | Cards per pod | Served model | Status |
|---|---:|---:|---|---|
| vLLM | `1` | **2** | `qwen3.8-27b` | Official FP8 production cutover |
| llama.cpp | `0` | 1 | `qwen3.8-27b` | Retained GGUF rollback |
| NInfer | `0` | 1 | `qwen3.8-ninfer` | Parked evaluation |
| ComfyUI / SwarmUI | `0` | 1 | Image generation | Parked |

Both RTX 3090s belong to vLLM. Other GPU workloads must remain parked;
[GPU scale-swap](gpu-scale-swap.md) owns the procedure. Flash Next remains
[a researched alternative](flash-next-dual-3090.md).

## Official Qwen3.8-27B FP8

| Property | Value |
|---|---|
| Engine | stock vLLM `v0.28.0`, pinned digest |
| Weights | official `Qwen/Qwen3.8-27B-FP8`, pinned revision |
| Placement | TP=2, two RTX 3090s, no CPU weight offload |
| KV / recurrent state | FP8 E4M3 / float16 |
| Context ceiling | 262,144 tokens |
| Concurrency | two sequences sharing the KV pool |
| Vision | native encoder; one image per request, video disabled |
| Reasoning | explicit off / low / medium / xhigh; low default |
| Speculation | disabled; MTP deferred until long-session fixes are validated |
| Power | 220 W per card |

The official checkpoint is about 30.89 GB (28.77 GiB). RTX 3090 uses an
Ampere-compatible weight-only FP8 path. Host RAM is loading/transport headroom,
not additional GPU KV capacity. 262K is a server ceiling, not a promise of two
simultaneous full-length sessions. AutoRound INT4/W4A8 is a later speed A/B.

The [canonical vLLM runbook](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/ai/vllm/README.md)
owns exact flags, source references, reasoning/sampling examples, rollout
checks and rollback. No throughput measurement is claimed for this new profile.

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

- model: `qwen3.8-27b`
- direct endpoint: `http://vllm-service.vllm.svc.cluster.local:8080/v1`
- existing app alias: `http://llama-cpp-service.llama-cpp.svc.cluster.local:8080/v1`
- LAN: `https://llama.vanillax.me/v1` and `https://vllm.vanillax.me/v1`

The llama.cpp Service aliases vLLM, preserving existing app configuration.
Both LAN hostnames route directly to the vLLM selector Service. Consumers
include Open WebUI, Perplexica/Vane, LiteLLM, Presenton, SurfSense, HolmesGPT,
Hindsight, Project Nomad, the ComfyUI vision bridge, WorldMonitor, Keep,
Deal Scout, Karakeep and the News Reader Temporal worker.

## Pi.dev

Pi.dev uses the same `qwen3.8-27b` API id through
`https://llama.vanillax.me/v1`. The workstation configuration lives in
[`pi-agent-local-dev.md`](pi-agent-local-dev.md). Because Qwen3.8 separates
`enable_thinking` from its valid effort values (`low`, `medium`, `xhigh`), Pi
uses explicit `chat_template_kwargs` so `off` really disables thinking and
`medium` is the normal coding default.

The workstation launchers are:

```bash
alias pi-qwen-only='pi --model vanillax-llama/qwen3.8-27b --thinking medium'
alias pi-withk3='pi --model vanillax-litellm/kimi-k3'
```

`pi-qwen-only` is the clean local-Qwen path. `pi-withk3` starts on Kimi K3 but
keeps Qwen available through `/model` because both are enabled in Pi settings.
Old Pi sessions created under the retired `vanillax-vllm` provider can retain
that provider name in session metadata; use a new session when validating the
current provider.

## Historical llama.cpp baseline — 2026-09-03

Normal Open WebUI responses measured about **42-43 generated tok/s**. While
generating, the single RTX 3090 reported approximately **22,740 MiB / 24,576
MiB VRAM**, **87% GPU utilization**, and **216 W / 220 W**. These are
real-machine observations on the Threadripper 2950X host, not synthetic maxima.

## Rollback

Revert the FP8 cutover commit through Git, retaining the earlier two-GPU
hardware change. This restores llama.cpp's replica, selector Service and
route, and parks vLLM. Follow the canonical vLLM runbook for verification.
The retained caches avoid another large download.
