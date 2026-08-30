# AI model catalog

Current model inventory, runtime ownership, and app wiring for local chat
inference. The GPU swap procedure lives in
[`gpu-scale-swap.md`](gpu-scale-swap.md).

## Current state

| Backend | Replicas | Cards | Served model | Status |
|---|---:|---:|---|---|
| vLLM | `1` | **1** | `qwen3.8-27b` | Active backend for every app |
| llama.cpp | `0` | 1 | `Qwen3.8-Flash-Next Q4` | Parked GGUF rollback |
| NInfer | `0` | 1 | `qwen3.8-ninfer` | Parked evaluation |
| ComfyUI / SwarmUI | `0` | 1 | Image generation | Parked |

The chassis has one RTX 3090. Exactly one GPU Deployment may have
`replicas: 1`.

## Active Qwen3.8 backend

vLLM serves one canonical id, `qwen3.8-27b`:

| Property | Value |
|---|---|
| Engine | stock `vllm/vllm-openai:v0.28.0`, unpatched |
| Weights | `Qwen3.8-27B-W4A16-AutoRound-3090-int8lmhead` (dense 27B, ~17 GB) |
| Vision | native `Qwen3_5ForConditionalGeneration` tower, one image per prompt |
| KV | `fp8_e4m3`, uncalibrated scales; fp16 DeltaNet recurrent state |
| Context allocation | 65,536 tokens |
| Concurrency | three sequence slots, 2,048-token chunked prefill |
| Placement | whole card, `gpu-memory-utilization=0.93` |
| Speculation | stock MTP, 2 draft tokens |
| Default mode | thinking OFF; temp 0.7, top-p 0.8, top-k 20, presence-penalty 1.5 |

The 200 W power cap remains mandatory.

### Why not an Unsloth quant here

Unsloth's only vLLM-servable Qwen3.8-27B checkpoint is
[`unsloth/Qwen3.8-27B-NVFP4`](https://huggingface.co/unsloth/Qwen3.8-27B-NVFP4),
and NVFP4 needs Blackwell tensor cores (sm_120) — the 3090 is Ampere sm_86.
Unsloth's Q4 line for this model is GGUF, i.e. llama.cpp only. AutoRound W4A16
is the 4-bit vLLM path on this card.

## Storage and staging

vLLM mounts `192.168.10.133:/mnt/ai-pool/vllm` read-only over the NFS CSI
driver; the checkpoint is already staged there and needs no download Job. The
torch.compile and Triton caches persist on a Longhorn PVC — without them the
engine recompiles every boot.

The llama.cpp GGUF share, its download/cache-sync hooks, and its node-local
NVMe cache all remain intact so the rollback is a replica flip plus a rewire.

## App wiring

The canonical direct-client configuration is:

- endpoint: `http://vllm-service.vllm.svc.cluster.local:8080/v1`
- model: `qwen3.8-27b`

Every in-cluster consumer uses this pair, and `https://vllm.vanillax.me/v1`
routes to the same Service. `llama.vanillax.me` stays on the parked llama.cpp
route.

## Changing the served model

The served id is `--served-model-name` in `my-apps/ai/vllm/deployment.yaml`.
Roll every consumer in the same change if it changes: several background jobs
treat LLM failures as best-effort and otherwise fail silently.
