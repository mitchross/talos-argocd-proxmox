# Qwen3.8 Flash Next IQ4_XS Deployment Design

## Goal

Run Unsloth Qwen3.8-Flash-Next UD-IQ4_XS on the cluster's single RTX 3090
at the existing 131,072-token service context, with sustained warm decode of
at least 15 tokens per second. Preserve the OpenAI-compatible service name and
model alias used by existing clients.

## Why the Current Deployment Misses the Target

The current upstream llama.cpp `--fit on` deployment chooses whole-layer
placement for the AtomicChat quant. Live measurements reached only 0.44-0.58
decode tokens per second because significant non-expert work runs on the CPU.
The successful single-3090 recipe uses a different placement boundary: every
layer remains GPU-resident while only MoE expert tensors are kept in host RAM.
Current mainline llama.cpp exposes that boundary through `--n-cpu-moe`.

## Chosen Architecture

Reuse the official prebuilt x86_64 CUDA llama.cpp image already running on the
GPU node: build `10666`, commit `4e97ac86e`, pinned as
`ghcr.io/ggml-org/llama.cpp:server-cuda-b10666@sha256:a2d04d1d1c2b2abe287fef9a22a3700a7fa20aec4c4ab56135e0099f38119848`.
Live inspection confirms this binary supports Qwen3.8, `--n-cpu-moe`, mmap,
lazy tensor reads, and manual fit control. This avoids compiling CUDA on the
Apple Silicon workstation or waiting for a custom GitHub Actions build.

Serve Unsloth `UD-IQ4_XS` from Hugging Face revision
`c8b5954a88c2775c546b92593eda40ea041d3176`. The durable NFS model source and
node-local NVMe hydration pattern remain unchanged. The three model shards and
BF16 projector are downloaded with exact sizes and SHA-256 checksums. Existing
AtomicChat and UD-Q4_K_XL files remain available for rollback; pruning them is
outside this change.

The initial runtime profile is:

- 131,072-token context and one parallel slot
- all model layers eligible for CUDA with `--n-gpu-layers 99`
- automatic fit disabled with `--fit off`
- 45 MoE expert blocks in host RAM with `--n-cpu-moe 45`
- disk-backed n-gram table with `--load-mode mmap`
- lazy tensor reads enabled with `--tensor-read-lazy on`
- flash attention enabled
- symmetric `q8_0` K and V caches
- batch size 4,096 and micro-batch size 2,048
- the BF16 vision projector on CUDA
- MTP and weight prefetch disabled for the baseline measurement

The external model alias remains `Qwen3.8-Flash-Next Q4`. Existing clients do
not need configuration changes.

## Components and Responsibilities

### Inference Image

The Deployment retains the existing official image digest. There is no custom
Dockerfile, emulated build, or new container publication workflow. The image is
already cached on the target node, so this rollout has no image-build or
large-image-pull dependency.

### Model Acquisition

`download-model-job.yaml` adds an `unsloth-ud-iq4-xs` directory and downloads:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf` | 10,946,624 | `5ce89370720f8bf90890f439361282104c1aa1482d4013bb9a50923e758e71a4` |
| `Qwen3.8-Flash-Next-UD-IQ4_XS-00002-of-00003.gguf` | 49,835,229,856 | `577a38a2392b40ca2193cea502e1d92f60b8cd370675d308e0ec21885d9daaa7` |
| `Qwen3.8-Flash-Next-UD-IQ4_XS-00003-of-00003.gguf` | 43,836,407,744 | `d4634e6d84f0ebb0940be15c90d3790bf6464e3dea3a1cddc567dc0e83ad8833` |
| `mmproj-BF16.gguf` | 907,542,944 | `2e788f8c511d8093c7b43cb87b2fd7e14228340318057f8fb20c86df2efe2355` |

The existing resumable download and checksum-stamp behavior stays intact.
`cache-sync-job.yaml` copies the same files from NFS to the GPU worker's local
NVMe before the serving Deployment advances.

### Runtime Deployment

`deployment.yaml` switches the model entrypoint, projector, and placement/cache
flags together while retaining the image digest. The ArgoCD hook waves remain
download `-1`, NVMe hydration `0`, and server `1`, so the pod cannot start
against incomplete model files.

### Documentation

The app README and AI model catalog record the pinned image, quant, tensor
placement, context, expected resource usage, performance acceptance test, and
rollback path. Root and directory guidance are updated only where they state
the old live engine or quant as current truth.

## Build and Rollout Sequence

1. Add the exact IQ4_XS artifacts to both download and cache hydration hooks.
2. Switch the Deployment from auto-fit to explicit expert-only CPU placement.
3. Render and validate the Kustomize application locally.
4. Open a pull request; the user performs the merge.
5. Observe ArgoCD download, hydration, pod startup, and model-load logs.
6. Run controlled prompt-processing and token-generation benchmarks.

## Failure Handling and Rollback

- A model size or checksum mismatch fails the wave `-1` hook and prevents the
  Deployment from advancing.
- A truncated local copy fails the wave `0` hook before the server starts.
- Startup/readiness probes keep an unloaded or crashed server out of service.
- Rollback restores the prior upstream llama.cpp image digest, AtomicChat model
  path, F16 projector, q8 KV cache, and auto-fit arguments. The retained model
  files make this a manifest rollback rather than another large download.

## Verification and Acceptance

Before rollout:

- The pinned image reports build `10666`, commit `4e97ac86e`, and Linux x86_64.
- The image's help exposes `--n-cpu-moe`, mmap, lazy reads, and manual fit.
- `kubectl kustomize my-apps/ai/llama-cpp` renders successfully.
- Repository policy checks and YAML validation pass.

After ArgoCD sync:

- Application is `Synced` and `Healthy`; pod is ready with zero restarts.
- Logs show the full 131,072-token slot, CUDA placement, q8 KV cache, mmap, and
  45 CPU-resident MoE expert blocks.
- The process does not exhaust the 94 GiB container memory limit or 24 GiB GPU.
- A warm controlled decode test produces at least 15 tokens per second.
- Prompt processing is recorded separately; the reference target is roughly
  160 tokens per second, but it is diagnostic rather than a rollout gate.
- Text, tool-call formatting, and one vision request return valid output.

If decode remains below 15 tokens per second, do not enable MTP or change
multiple variables. Capture CPU, GPU, PCIe, memory, and mmap/page-fault data,
then tune only expert placement (`--n-cpu-moe`) in a follow-up trial.

## Non-Goals

- Raising context from 131,072 to 262,144 in the initial rollout
- Enabling MTP, n-gram speculative decoding, or weight prefetch
- Building or maintaining a custom Beellama container
- Adopting KVarN cache before a Qwen3.8-capable prebuilt Beellama image exists
- Removing rollback model files
- Raising the RTX 3090's 200 W power cap
- Changing client endpoints, aliases, or Open WebUI configuration

## Source References

- Exact runtime preset: <https://github.com/crusaderky/pixi-llm-recipes/blob/26ed50ace2a40772aa2b45d1358aaf0993fd5596/models.ini#L3-L94>
- Pinned llama.cpp source: <https://github.com/ggml-org/llama.cpp/tree/4e97ac86e>
- Pinned Unsloth artifacts: <https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF/tree/c8b5954a88c2775c546b92593eda40ea041d3176/UD-IQ4_XS>
