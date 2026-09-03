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
| Backend default | low reasoning; temp 0.7, top-p 0.8, top-k 20, presence-penalty 1.5 |

`b10751` fixed a Qwen3.8-27B MTP KV-initialization regression present in
`b10745`; production uses `b10752`. The 65K window is deliberately conservative
for the first production cutover: stability, tools, vision, Pi and multi-turn
correctness matter more than advertising the largest context that can boot.

The 200 W power cap remains mandatory.

## Storage and staging

The TrueNAS llama.cpp share is the canonical archive. A wave -1 hook downloads
and SHA-verifies the Q4_K_XL target, BF16 projector and Q4_0 MTP artifact; a
wave 0 hook hydrates those files into the GPU worker's 450 GB local NVMe cache.
The serving pod mounts only the local cache.

The old vLLM model and compile caches remain intact for rollback.

## App wiring

Canonical Git-managed direct-client configuration:

- endpoint: `http://llama-cpp-service.llama-cpp.svc.cluster.local:8080/v1`
- model: `qwen3.8-27b`

Both `https://vllm.vanillax.me/v1` and `https://llama.vanillax.me/v1` route to
llama.cpp. The old in-cluster `vllm-service.vllm.svc.cluster.local:8080` name is
retained as an `ExternalName` alias for persistent clients whose configuration
is stored outside Git, such as already-imported n8n workflows.

## Rollback

The vLLM manifests, model cache and compile caches are retained. Rollback is a
single GitOps change that flips GPU ownership, restores the vLLM route/service,
and rewires Git-managed consumers. Never scale both backends to one.
