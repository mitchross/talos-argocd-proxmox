# AI model catalog

Current model inventory, runtime ownership, and app wiring for local chat
inference. The GPU swap procedure lives in
[`gpu-scale-swap.md`](gpu-scale-swap.md).

## Current state

| Backend | Replicas | Cards | Served model | Status |
|---|---:|---:|---|---|
| llama.cpp | `1` | **1** | `qwen3.8-27b` | Active production backend |
| vLLM | `0` | 1 | `qwen3.8-27b` | Parked rollback |
| NInfer | `0` | 1 | `qwen3.8-ninfer` | Parked evaluation |
| ComfyUI / SwarmUI | `0` | 1 | Image generation | Parked |

The chassis has one RTX 3090. Exactly one GPU Deployment may have
`replicas: 1`.

## Active Qwen3.8 backend

llama.cpp serves the canonical `qwen3.8-27b` id:

| Property | Value |
|---|---|
| Engine | stock llama.cpp `b10752` CUDA12 |
| Weights | Unsloth `Qwen3.8-27B-UD-Q4_K_XL.gguf` (~17.6 GB) |
| Vision | BF16 Qwen3.8-27B projector |
| KV | q8_0 K/V for target and MTP draft |
| Context allocation | 65,536 tokens |
| Concurrency | one sequence slot |
| Placement | target + draft fully on RTX 3090 |
| Speculation | MTP Q4_0, `n-max=2` |
| Backend default | low reasoning; temp 0.7, top-p 0.8, top-k 20, min-p 0, presence-penalty 1.5 |
| Power cap | 220 W |

`b10751` fixed a Qwen3.8-27B MTP KV-initialization regression present in
`b10745`; production uses `b10752`. The 65K window is deliberately conservative:
stability, tools, vision, Pi.dev and multi-turn correctness matter more than
advertising the largest context that can boot.

### Measured production baseline — 2026-09-03

Normal Open WebUI responses measured about **42-43 generated tok/s**. While
generating, the single RTX 3090 reported approximately **22,740 MiB / 24,576
MiB VRAM**, **87% GPU utilization**, and **216 W / 220 W**. These are
real-machine observations on the Threadripper 2950X host, not synthetic maxima.

## Storage and staging

The TrueNAS llama.cpp share is the canonical archive. A wave -1 hook downloads
and SHA-verifies the Q4_K_XL target, BF16 projector and Q4_0 MTP artifact; a
wave 0 hook hydrates those files into the GPU worker's local NVMe cache. The
serving pod mounts only the local cache.

A revisioned ready stamp plus a serving initContainer gates startup until the
exact local-NVMe artifact set is present. The old vLLM model and compile caches
remain intact for rollback.

## App wiring

Canonical Git-managed direct-client configuration:

- endpoint: `http://llama-cpp-service.llama-cpp.svc.cluster.local:8080/v1`
- model: `qwen3.8-27b`
- LAN endpoint: `https://llama.vanillax.me/v1`

`https://vllm.vanillax.me/v1` remains a compatibility LAN hostname and also
routes to llama.cpp. The old in-cluster
`vllm-service.vllm.svc.cluster.local:8080` name remains an `ExternalName` alias
for persistent clients whose configuration lives outside Git, such as already
imported n8n workflows.

Git-managed consumers should use `llama-cpp-service` directly. Current direct
consumers include Open WebUI, Perplexica/Vane, LiteLLM, Presenton, SurfSense,
HolmesGPT, Hindsight, Project Nomad, and the ComfyUI vision bridge.

## Pi.dev

Pi.dev uses the same `qwen3.8-27b` API id through
`https://llama.vanillax.me/v1`. The workstation configuration lives in
[`pi-agent-local-dev.md`](pi-agent-local-dev.md). Pi sends top-level
`reasoning_effort`; medium is the normal coding default and xhigh is reserved
for difficult reasoning.

## Rollback

The vLLM manifests, model cache and compile caches are retained. Rollback is a
single GitOps change that flips GPU ownership, restores the vLLM route/service,
and rewires Git-managed consumers. Never scale both backends to one.
