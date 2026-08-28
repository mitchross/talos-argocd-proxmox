# llama.cpp — Qwen3.8-Flash-Next Q4 on one RTX 3090

This is the active OpenAI-compatible chat, tool, and vision backend:

- in cluster: `http://llama-cpp-service.llama-cpp.svc.cluster.local:8080/v1`
- on the LAN: `https://llama.vanillax.me/v1` and the compatibility hostname
  `https://vllm.vanillax.me/v1`
- API model: `qwen3.8-27b`

`qwen3.8-27b` is temporarily a compatibility alias. The physical model is
Qwen3.8-Flash-Next UD-Q4_K_XL, so existing Pi, Perplexica, Deal Scout,
Karakeep, and other consumers do not need a coordinated rename for this trial.

## Pinned inputs

| Input | Pin |
|---|---|
| Engine source | upstream llama.cpp `4e97ac86ebe2c4cb8212d98d2641ad6768810896` (`b10666`) |
| Engine image | `ghcr.io/ggml-org/llama.cpp:server-cuda-b10666@sha256:a2d04d1d1c2b2abe287fef9a22a3700a7fa20aec4c4ab56135e0099f38119848` (amd64) |
| Model repository | `unsloth/Qwen3.8-Flash-Next-GGUF` revision `c8b5954a88c2775c546b92593eda40ea041d3176` |
| Weights | `Qwen3.8-Flash-Next-UD-Q4_K_XL-00001-of-00004.gguf` through `00004-of-00004.gguf` |
| Vision projector | `mmproj-BF16.gguf`, SHA-256 `2e788f8c511d8093c7b43cb87b2fd7e14228340318057f8fb20c86df2efe2355` |

Official build `b10666` is produced from a commit after the qwen4exp merge
commit `6c84c7d5d8833c6e0df69628f75a0f599797934e`. The Deployment pins the
official tag and its linux/amd64 manifest digest; do not use pre-merge `b10236`.

The wave-0 Sync hook downloads and verifies all four Q4 shards and the public
BF16 projector on the existing RWX model share. It resumes `.part` files,
checks byte size and SHA-256, and atomically renames verified artifacts. The
wave-1 Deployment mounts the share read-only and starts after the hook succeeds.

## Runtime profile

- one whole RTX 3090 and one parallel slot
- 131,072-token context with symmetric q8_0 K/V cache
- Flash Attention and native Jinja; reasoning enabled at low effort
- BF16 vision enabled with the projector on CPU to preserve the 131K GPU KV budget
- MTP disabled because the merged Flash-Next path does not include final MTP support
- automatic fit disabled; PLE and blocks 9-46 FFN tensors explicitly placed on CPU
- `--load-mode mmap --tensor-read-lazy auto`; no mlock, so tensors larger than
  4 GiB (including PLE/ngram) are demand-paged instead of being forced resident
- 20 CPU / 80 GiB requests, no CPU limit, and a 94 GiB memory limit; the 100
  GiB Talos VM keeps roughly 6 GiB outside the pod for Talos and node services
  while allowing useful mmap page cache. The sole GPU remains limit=request=1.

The NFS export reported 728 GiB free before download, so no existing model was
deleted. The PVC's 150 GiB capacity is a static Kubernetes declaration, not an
export quota.

## Rollback

Set llama.cpp to `replicas: 0`, set `my-apps/ai/vllm/deployment.yaml` to
`replicas: 1`, restore the vLLM HTTPRoute resource, and repoint consumers in the
same commit. The scheduler sequences the sole GPU; never scale both to one.
