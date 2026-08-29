# llama.cpp — Qwen3.8-Flash-Next Q4 on one RTX 3090

This is the active OpenAI-compatible chat, tool, and vision backend:

- in cluster: `http://llama-cpp-service.llama-cpp.svc.cluster.local:8080/v1`
- on the LAN: `https://llama.vanillax.me/v1` and the compatibility hostname
  `https://vllm.vanillax.me/v1`
- API model: `Qwen3.8-Flash-Next Q4`

The API model name identifies the physical Unsloth UD-IQ4_XS checkpoint. Do
not use `qwen3.8-27b` for this model; that name belongs to the separate 27B
checkpoint.

## Pinned inputs

| Input | Pin |
|---|---|
| Engine source | upstream llama.cpp `4e97ac86ebe2c4cb8212d98d2641ad6768810896` (`b10666`) |
| Engine image | `ghcr.io/ggml-org/llama.cpp:server-cuda-b10666@sha256:a2d04d1d1c2b2abe287fef9a22a3700a7fa20aec4c4ab56135e0099f38119848` (amd64) |
| Model repository | `unsloth/Qwen3.8-Flash-Next-GGUF` revision `c8b5954a88c2775c546b92593eda40ea041d3176` |
| Weights | `Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf` through `00003-of-00003.gguf` |
| Vision projector | `mmproj-BF16.gguf`, SHA-256 `2e788f8c511d8093c7b43cb87b2fd7e14228340318057f8fb20c86df2efe2355` |

Official build `b10666` is produced from a commit after the qwen4exp merge
commit `6c84c7d5d8833c6e0df69628f75a0f599797934e`. The Deployment pins the
official tag and its linux/amd64 manifest digest; do not use pre-merge `b10236`.

The wave -1 Sync hook downloads and verifies all three IQ4_XS shards and the
public BF16 projector on the existing RWX model share. It retains the prior
AtomicChat and four-shard UD-Q4_K_XL artifacts for rollback. Downloads resume
`.part` files, check byte size and SHA-256, and atomically rename verified
artifacts.

## Model storage

Two tiers. NFS is the canonical archive; a node-local NVMe cache is what
inference actually reads.

| Tier | Backing | PVC | Role |
|---|---|---|---|
| Source | TrueNAS NFS, `192.168.10.133:/mnt/ai-pool/llama-cpp` | `llama-cpp-models-pvc` (RWX) | canonical archive, hydrated from Hugging Face |
| Cache | GPU node's 450 GB NVMe, Talos UserVolume `ai-model-cache` → `/var/mnt/ai-model-cache` | `ai-model-cache` (RWO, `Retain`) | what the Deployment mounts at `/models` |

The Deployment mounts **only** the cache. NFS must stay out of the inference
path: llama.cpp demand-pages tensors under `--load-mode mmap`, so a page-cache
miss against NFS becomes a network round trip, and under memory pressure that
collapses throughput to well under 1 tok/s.

`cache-sync-job.yaml` (wave 0 Sync hook) copies the IQ4_XS model, its projector,
and the retained rollback files from NFS to the cache. It compares
**name and size only** because the wave -1 source hook already pins SHA-256; a
second hash pass would stream both families through page cache on every sync.
It is idempotent, and a warm cache exits in seconds.

The cache PV is node-local by design (`nodeAffinity: gpu-worker=true`,
`persistentVolumeReclaimPolicy: Retain`) and is **not** on Longhorn and not
replicated — GGUF files are reproducible from NFS. IQ4_XS adds approximately
87.25 GiB to the retained AtomicChat and UD-Q4_K_XL families. All three model
families use approximately 281 GiB and leave roughly 169 GiB on the 450 GiB
cache.

## Runtime profile

- one whole RTX 3090 and one parallel slot
- 131,072-token context with symmetric q8_0 K/V cache
- Flash Attention and native Jinja; reasoning enabled at low effort
- BF16 vision enabled with the projector on CUDA
- MTP disabled because the merged Flash-Next path does not include final MTP support
- automatic fit disabled; `--n-gpu-layers 99 --n-cpu-moe 45` keeps non-expert
  work on CUDA while the first 45 layers' expert weights use host RAM
- `--load-mode mmap --tensor-read-lazy on`; no mlock, so the dedicated IQ4_XS
  N-gram shard stays disk-backed and only touched rows enter page cache
- batch size 4096 and micro-batch size 2048
- 20 CPU / 80 GiB requests, no CPU limit, and a 94 GiB memory limit; the 100
  GiB Talos VM keeps roughly 6 GiB outside the pod for Talos and node services
  while allowing useful mmap page cache. The sole GPU remains limit=request=1.

No existing model is deleted during this trial. The PVC's 150 GiB capacity is
a static Kubernetes declaration, not an export quota.

## IQ4_XS placement acceptance gate — pending deployment

This change replaces whole-layer auto-fit with expert-only CPU placement while
preserving context, KV, sampling, and the external API. It does not claim a
throughput win before the branch is merged and measured on the GPU worker.

Acceptance requires a warm, single-stream `tg128` result of at least 15 tok/s
while the server remains configured for a 131,072-token slot. Record `pp512`,
streaming TTFT, device and cgroup memory, major faults, process read bytes, CPU
and GPU utilization, plus text, tool-call, and vision correctness. If the
45-CPU-expert-layer placement misses the target, tune only `--n-cpu-moe` one
boundary per measurement round; do not simultaneously change context, KV type,
or speculative decoding.

## Historical Atomic auto-fit trial — 2026-08-29

The official b10666 image loaded the AtomicChat model with `--fit on` and the
full 131K slot, but whole-layer placement reached only 0.44-0.58 generated
tokens per second. The pod used approximately 23.4 GiB VRAM and drove CPU while
GPU activity stayed low and bursty. That result is the reason this trial uses
explicit expert-only placement instead of auto-fit.

## Historical Unsloth baseline — 2026-08-28

- llama.cpp `b10666` / `4e97ac86e`; GGUF architecture `qwen4exp`
- model plus CPU-resident BF16 projector loaded in 3m51.26s from NFS
- one slot with `n_ctx_slot = 131072`; zero container restarts after rollout
- RTX 3090 used 24,074 MiB idle and 24,114 MiB after smoke tests
- cgroup memory was 79.4 GiB after tests and peaked at 80.6 GiB; process RSS
  was 76.1 GiB (73.0 GiB file-backed, 2.9 GiB anonymous). This confirms the
  PLE/model mapping is mixed mmap + page cache rather than fully resident anon
  memory. `kubectl top` working set was 35.5 GiB for the pod and 47.5 GiB for
  the node after testing.
- text smoke test: 10.46 prompt tok/s, 4.95 generation tok/s, 11.77s total
- warm streaming TTFT: 0.218s; 13.60 prompt tok/s and 6.29 generation tok/s
- tool smoke test: valid `get_weather({"city":"Detroit"})` call; 25.77 prompt
  tok/s and 5.67 generation tok/s
- vision smoke test: correctly answered `Bright red` for a 224x224 red PNG;
  14.01 prompt tok/s and 7.19 generation tok/s

The initial blocks 10-46 placement left 21,954 MiB allocated and failed a
612.01 MiB q8_0 KV allocation. Moving only block 9 FFN to CPU reduced model
placement to 20,444 MiB and allowed the 131K KV cache to initialize. The BF16
projector then needed another 865.48 MiB on CUDA, so it remains enabled but
uses `--no-mmproj-offload`.

## Rollback

For an in-place llama.cpp rollback, restore the Atomic model path
`atomic-ad-4.27-q4-k-m-m64/Qwen3.8-Flash-Next-AD-4.27bpw-Q4_K_M-M64-00001-of-00033.gguf`,
restore `mmproj-F16.gguf` and `--no-mmproj-offload`, set micro-batch back to
512, set lazy reads to `auto`, remove `--n-gpu-layers` and `--n-cpu-moe`, then
restore `--fit on --fit-ctx 131072 --fit-target 512`. All artifacts remain on
NFS and NVMe, so this is one normal `Recreate` rollout with no download.

For a backend rollback, set llama.cpp to `replicas: 0`, set
`my-apps/ai/vllm/deployment.yaml` to `replicas: 1`, restore the vLLM HTTPRoute,
and repoint consumers in the same commit. The scheduler sequences the sole GPU;
never scale both to one.
