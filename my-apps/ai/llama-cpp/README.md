# llama.cpp — Qwen3.8-Flash-Next Q4 on one RTX 3090

This is the active OpenAI-compatible chat, tool, and vision backend:

- in cluster: `http://llama-cpp-service.llama-cpp.svc.cluster.local:8080/v1`
- on the LAN: `https://llama.vanillax.me/v1` and the compatibility hostname
  `https://vllm.vanillax.me/v1`
- API model: `Qwen3.8-Flash-Next Q4`

The API model name identifies the physical AtomicChat
AD-4.27bpw-Q4_K_M-M64 checkpoint. Do not use `qwen3.8-27b` for this model;
that name belongs to the separate 27B checkpoint.

## Pinned inputs

| Input | Pin |
|---|---|
| Engine source | upstream llama.cpp `4e97ac86ebe2c4cb8212d98d2641ad6768810896` (`b10666`) |
| Engine image | `ghcr.io/ggml-org/llama.cpp:server-cuda-b10666@sha256:a2d04d1d1c2b2abe287fef9a22a3700a7fa20aec4c4ab56135e0099f38119848` (amd64) |
| Model repository | `AtomicChat/Qwen3.8-Flash-Next-GGUF` revision `142262902a46f7daed19c79d0771534c8106ad59` |
| Weights | `Qwen3.8-Flash-Next-AD-4.27bpw-Q4_K_M-M64-00001-of-00033.gguf` through `00033-of-00033.gguf` |
| Vision projector | `mmproj-Qwen3.8-Flash-Next-F16.gguf`, SHA-256 `0e61454a76dd154a10aaa8fb1ada32615f55a13e4171014dacd06913e4aa6889` |

Official build `b10666` is produced from a commit after the qwen4exp merge
commit `6c84c7d5d8833c6e0df69628f75a0f599797934e`. The Deployment pins the
official tag and its linux/amd64 manifest digest; do not use pre-merge `b10236`.

The wave -1 Sync hook downloads and verifies all 33 Atomic Q4 shards and the
public F16 projector on the existing RWX model share. It also retains and
verifies the prior four-shard Unsloth model and BF16 projector for rollback.
Downloads resume `.part` files, check byte size and SHA-256, and atomically
rename verified artifacts.

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

`cache-sync-job.yaml` (wave 0 Sync hook) copies the Atomic model, its projector,
and the retained Unsloth rollback files from NFS to the cache. It compares
**name and size only** because the wave -1 source hook already pins SHA-256; a
second hash pass would stream both families through page cache on every sync.
It is idempotent, and a warm cache exits in seconds.

The cache PV is node-local by design (`nodeAffinity: gpu-worker=true`,
`persistentVolumeReclaimPolicy: Retain`) and is **not** on Longhorn and not
replicated — GGUF files are reproducible from NFS. The Atomic model and F16
projector use 88.88 GiB; the retained Unsloth model and projector use 104.53
GiB. Together they leave approximately 256 GiB on the 450 GiB cache.

## Runtime profile

- one whole RTX 3090 and one parallel slot
- 131,072-token context with symmetric q8_0 K/V cache
- Flash Attention and native Jinja; reasoning enabled at low effort
- F16 vision enabled with the projector on CPU to preserve the 131K GPU KV budget
- MTP disabled because the merged Flash-Next path does not include final MTP support
- automatic fit disabled; blocks 9-46 FFN tensors initially placed on CPU
- `--load-mode mmap --tensor-read-lazy auto`; no mlock, so tensors larger than
  4 GiB are demand-paged instead of being forced resident. Atomic shard 00002
  contains only the 38.4 GB decimal N-gram table, so it is not interleaved with
  CUDA-pinned ordinary weights and needs no explicit PLE tensor override.
- 20 CPU / 80 GiB requests, no CPU limit, and a 94 GiB memory limit; the 100
  GiB Talos VM keeps roughly 6 GiB outside the pod for Talos and node services
  while allowing useful mmap page cache. The sole GPU remains limit=request=1.

No existing model is deleted during this trial. The PVC's 150 GiB capacity is
a static Kubernetes declaration, not an export quota.

## Atomic layout acceptance gate — pending deployment

This commit changes the GGUF layout and projector while deliberately preserving
context, KV, batching, sampling, and the initial expert placement. It does not
claim a throughput win before the branch is merged and measured on the GPU
worker.

Acceptance requires a warm, single-stream `tg128` result of at least 15 tok/s
while the server remains configured for a 131,072-token slot. Record `pp512`,
streaming TTFT, device and cgroup memory, major faults, process read bytes, CPU
and GPU utilization, plus text, tool-call, and vision correctness. If the
conservative blocks 9-46 CPU placement misses the target, move one expert
boundary toward the GPU per measurement round; do not simultaneously change
context, KV type, or speculative decoding.

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

For an in-place llama.cpp rollback, restore the model path to
`unsloth-ud-q4-k-xl/Qwen3.8-Flash-Next-UD-Q4_K_XL-00001-of-00004.gguf`, restore
`mmproj-BF16.gguf`, and restore
`^per_layer_token_embd\.weight$=CPU,blk\.((9|[123][0123456789]|40|41|42|43|44|45|46))\.ffn_.*=CPU`.
Both model families remain on NFS and NVMe, so this is one normal `Recreate`
rollout with no download.

For a backend rollback, set llama.cpp to `replicas: 0`, set
`my-apps/ai/vllm/deployment.yaml` to `replicas: 1`, restore the vLLM HTTPRoute,
and repoint consumers in the same commit. The scheduler sequences the sole GPU;
never scale both to one.
