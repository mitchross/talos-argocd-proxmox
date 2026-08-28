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
| Engine source | upstream llama.cpp `ca3d5a3e10d53f7ea672cb9b6178faca3e2807bc` |
| Engine image | `ghcr.io/mitchross/llama.cpp:server-cuda-qwen4exp-ca3d5a3e@sha256:d65024550d73e4746f0147cb877f6b98fb7885258b1e88d6dcd761a69964d029` |
| Model repository | `unsloth/Qwen3.8-Flash-Next-GGUF` revision `c8b5954a88c2775c546b92593eda40ea041d3176` |
| Weights | `Qwen3.8-Flash-Next-UD-Q4_K_XL-00001-of-00004.gguf` through `00004-of-00004.gguf` |
| Vision projector | `mmproj-F16.gguf`, SHA-256 `1f7b7f0b984cf065c604360c29c8098362ed61b290db0ff12c6f360bb1a8a980` |

The newest official image available during this migration, `b10644`, predates
the qwen4exp merge commit `6c84c7d5d8833c6e0df69628f75a0f599797934e`.
`build-qwen4exp-image.sh` therefore reproduces the temporary CUDA 12.8,
Ampere-only server image from the pinned post-merge source commit.
The temporary image lives in the public `mitchross/llama.cpp` GHCR package so
Talos can pull it anonymously. The Deployment also pins its manifest digest.

The wave-0 Sync hook downloads and verifies all four Q4 shards and the public
F16 projector on the existing RWX model share. It resumes `.part` files,
checks byte size and SHA-256, and atomically renames verified artifacts. The
wave-1 Deployment mounts the share read-only and starts after the hook succeeds.

## Runtime profile

- one whole RTX 3090 and one parallel slot
- 131,072-token context with symmetric q8_0 K/V cache
- Flash Attention and native Jinja; reasoning enabled at low effort
- MTP disabled because the merged Flash-Next path does not include final MTP support
- automatic fit disabled; PLE and blocks 10-46 FFN tensors explicitly placed on CPU
- `--load-mode mmap --tensor-read-lazy on`; no mlock, so the PLE/ngram table is
  demand-paged from the model mapping instead of being forced resident
- 24 CPU / 76 GiB requests, no CPU limit, and a 92 GiB memory limit; the 100
  GiB Talos VM keeps roughly 8 GiB outside the pod for Talos and node services
  while allowing useful mmap page cache. The sole GPU remains limit=request=1.

The NFS export reported 728 GiB free before download, so no existing model was
deleted. The PVC's 150 GiB capacity is a static Kubernetes declaration, not an
export quota.

## Rollback

Set llama.cpp to `replicas: 0`, set `my-apps/ai/vllm/deployment.yaml` to
`replicas: 1`, restore the vLLM HTTPRoute resource, and repoint consumers in the
same commit. The scheduler sequences the sole GPU; never scale both to one.
