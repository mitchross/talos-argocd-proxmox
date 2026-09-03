# llama.cpp — Qwen3.8-27B on one RTX 3090

**Active production local-LLM backend.** vLLM remains deployed at zero replicas
as the rollback path.

- in cluster: `http://llama-cpp-service.llama-cpp.svc.cluster.local:8080/v1`
- canonical LAN endpoint: `https://llama.vanillax.me/v1`
- compatibility LAN endpoint: `https://vllm.vanillax.me/v1`
- API model: `qwen3.8-27b`

## Production profile

| Setting | Value |
|---|---|
| GPU | 1x RTX 3090 24 GB |
| Power cap | 220 W |
| Engine | stock llama.cpp `b10752`, official CUDA12 linux/amd64 image |
| Target | `unsloth/Qwen3.8-27B-GGUF` `UD-Q4_K_XL` |
| Target size | ~17.6 GB |
| Vision | `mmproj-BF16.gguf` |
| Speculation | MTP, Q4_0 draft, `n-max=2` |
| Context | 65,536 tokens |
| KV | q8_0 target + draft |
| Placement | target + draft fully on GPU; no CPU MoE/offload hot path |
| Concurrency | one slot |
| Storage | verified NFS archive -> GPU-node local NVMe cache |

Observed after the 2026-09-03 production cutover: normal Open WebUI responses
sustained about **42-43 generated tok/s**; under generation the RTX 3090 showed
about **22,740 MiB / 24,576 MiB VRAM**, **87% GPU utilization**, and **216 W /
220 W**. Treat these as the first real-machine baseline, not a synthetic ceiling.

The goal is an everyday backend, not a maximum-context benchmark. This
dense/full-GPU shape is roughly an order of magnitude faster on this exact host
than the Flash-Next IQ4_XS CPU-MoE trial, while retaining vision, reasoning,
tools and MTP.

## Pinned inputs

- image: `ghcr.io/ggml-org/llama.cpp:server-cuda-b10752@sha256:dde47811ea25c3a30233edba1bb898e7e7246ab653f94a3972b8497c4a349b4b`
- model SHA-256: `3f227079003add2511437e5b1e94812e363385225bf6a9b47b0054a72bc8b01e`
- vision projector SHA-256: `83ee4f4f205fa514161778c41df1ea14144faa0f713510893b63c2395f5c2d53`
- MTP Q4_0 SHA-256: `50d9ce5a6da381bbcfb31061cf73df94a90e6faf8efeddee379a9cb8f1501c6e`

`b10751` fixed the Qwen3.8-27B MTP KV-initialization regression reported in
`b10745`; `b10752` is the next official image and contains that fix.

## Storage and startup ordering

The wave -1 download hook SHA-verifies the model, projector and MTP artifact on
TrueNAS NFS. The wave 0 cache-sync hook copies only those three files into the
GPU worker's node-local `ai-model-cache` PVC. The serving pod mounts only the
NVMe cache.

A revisioned `.qwen38-27b-cache-ready` stamp is written only after all three
artifacts finish local-NVMe hydration. `wait-for-model-cache` blocks the serving
container until that exact revision and all files are present. This prevents an
existing Deployment from crash-looping while Argo hooks are still staging a
new model.

Old Flash-Next artifacts may remain on NFS/NVMe for manual recovery, but they
are not downloaded, synchronized or referenced by the active manifests.

## Runtime notes

- `GGML_CUDA_GRAPH_OPT=1` follows the fast RTX 3090 dense-Qwen3.8 serving
  reports.
- `GGML_CUDA_CUBLAS_COMPUTE_TYPE=fp32` avoids an Ampere multimodal cuBLAS
  failure observed during vision prefill.
- `--image-min-tokens 1024` favors vision/grounding correctness.
- reasoning defaults to low effort server-side. Qwen3.8 separately controls
  `enable_thinking` and reasoning effort (`low`, `medium`, `xhigh`); clients
  that expose an off switch must send `enable_thinking=false`, not merely omit
  `reasoning_effort`. The Pi.dev guide documents the exact mapping.
- `--reasoning-preserve` keeps reasoning state coherent across multi-turn use.
- Prefix `--cache-reuse` is intentionally omitted: llama.cpp disables it when
  the multimodal projector is loaded, so keeping the flag only produces a
  misleading startup warning.
- Sampling stays server-owned at temp 0.7 / top-p 0.8 / top-k 20 / min-p 0 /
  presence penalty 1.5 / repeat penalty 1.0 unless a client explicitly
  overrides it.

## Cutover / rollback

The active Kustomizations enforce `llama-cpp-server=1` and `vllm-server=0`.
The old `vllm-service.vllm.svc.cluster.local` DNS name is retained as an
`ExternalName` alias to llama.cpp because some persistent consumers (for
example already-imported n8n workflows) store their endpoint outside Git.
Git-managed consumers use `llama-cpp-service` directly.

To roll back, reverse the replica ownership, restore the vLLM HTTPRoute, and
repoint Git-managed consumers to vLLM in one PR. Never run both GPU deployments
at one replica on the single-card worker.
