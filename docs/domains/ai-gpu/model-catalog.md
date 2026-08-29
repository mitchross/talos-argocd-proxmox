# AI model catalog

Current model inventory, runtime ownership, and app wiring for local chat
inference. The GPU swap procedure lives in
[`gpu-scale-swap.md`](gpu-scale-swap.md).

## Current state

| Backend | Replicas | Cards | Served model | Status |
|---|---:|---:|---|---|
| llama.cpp | `1` | **1** | `Qwen3.8-Flash-Next Q4` | Active backend for every app |
| vLLM | `0` | 1 | `qwen3.8-27b` | Parked rollback |
| NInfer | `0` | 1 | `qwen3.8-ninfer` | Parked evaluation |
| ComfyUI / SwarmUI | `0` | 1 | Image generation | Parked |

The chassis has one RTX 3090. Exactly one GPU Deployment may have
`replicas: 1`.

## Active Qwen3.8 backend

llama.cpp serves one canonical id, `Qwen3.8-Flash-Next Q4`:

| Property | Value |
|---|---|
| Engine | mainline llama.cpp `server-cuda-b10666` (`4e97ac86e`) |
| Weights | Unsloth `Qwen3.8-Flash-Next-UD-IQ4_XS`, three shards |
| Vision | `mmproj-BF16.gguf`, CUDA-resident |
| KV | symmetric q8_0 K/V |
| Context allocation | 131,072 tokens |
| Concurrency | one parallel slot |
| Placement | all layers on CUDA; first 45 layers' MoE experts in host RAM |
| N-grams | lazy mmap from node-local NVMe |
| Speculation | disabled |
| Default mode | reasoning low; temp 0.7, top-p 0.8, top-k 20 |

The initial acceptance gate is warm single-stream `tg128 >= 15 tok/s`; no
throughput result is claimed until it is measured after rollout. The 200 W
power cap remains mandatory.

## Storage and staging

The wave -1 Sync hook downloads the GGUF and BF16 projector from pinned
Hugging Face revisions, verifies their SHA-256 digests, and writes them to
`192.168.10.133:/mnt/ai-pool/llama-cpp`. The wave 0 hook hydrates a node-local
NVMe cache; the wave 1 server mounts only that cache read-only so mmap misses
never become NFS round trips.

The vLLM model share and compile cache remain intact for rollback. The retired
syv-ai `qwen38-3090` application was removed; ArgoCD prunes its namespace and
Longhorn compile-cache PVC, while the shared NFS model store remains retained.

### Model acquisition performance

The download hook resumes `.part` files and fetches the two large IQ4_XS
shards concurrently. Each completed artifact is checked against its pinned
byte size and SHA-256 before it becomes the canonical NAS copy; wave 0 then
copies it to the GPU node's local NVMe PVC.

Planned follow-up: replace the public-model curl transfers with authenticated
`huggingface_hub` plus adaptive `hf_xet`, reusing the Hugging Face token in
1Password. Keep normal adaptive mode under the downloader's 4 GiB memory limit;
do not enable Xet high-performance mode until its larger buffers and node
headroom are explicitly sized.

## App wiring

The canonical direct-client configuration is:

- endpoint: `http://llama-cpp-service.llama-cpp.svc.cluster.local:8080/v1`
- model: `Qwen3.8-Flash-Next Q4`

Open WebUI uses the canonical alias. Several legacy direct consumers still
send `qwen3.8-27b`; migrating those request strings is intentionally separate
from this runtime placement trial. The compatibility hostname
`https://vllm.vanillax.me/v1` routes to the same llama.cpp Service.

## Changing the served model

The served id is `--alias` in `my-apps/ai/llama-cpp/deployment.yaml`. Roll every
consumer in the same change if it changes: several background jobs treat LLM
failures as best-effort and otherwise fail silently.
