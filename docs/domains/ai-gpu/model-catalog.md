# AI model catalog

Current model inventory, runtime ownership, and app wiring for local chat
inference. The GPU swap procedure lives in
[`gpu-scale-swap.md`](gpu-scale-swap.md).

## Current state

| Backend | Replicas | Cards | Served model | Status |
|---|---:|---:|---|---|
| llama.cpp | `1` | **1** | `qwen3.8-27b` | Active backend for every app |
| vLLM | `0` | 1 | `qwen3.8-27b` | Parked rollback |
| NInfer | `0` | 1 | `qwen3.8-ninfer` | Parked evaluation |
| ComfyUI / SwarmUI | `0` | 1 | Image generation | Parked |

The chassis has one RTX 3090. Exactly one GPU Deployment may have
`replicas: 1`.

## Active Qwen3.8 backend

llama.cpp follows `club-3090/docs/SINGLE_CARD.md` at commit `4e6c3363` and
serves one canonical id, `qwen3.8-27b`:

| Property | Value |
|---|---|
| Engine | mainline llama.cpp `server-cuda-b10236` |
| Weights | Unsloth `Qwen3.8-27B-UD-IQ4_XS.gguf` |
| Vision | `mmproj-F16.gguf` |
| KV | symmetric q8_0 K/V |
| Context allocation | 131,072 tokens |
| Concurrency | one parallel slot |
| Speculation | embedded MTP head, depth 2 |
| Default mode | reasoning off; temp 0.7, top-p 0.8, top-k 20 |

The club-3090 slug defaults to q4_0 KV at 262K as a maximum-context exhibit.
This cluster uses the guide's serving-grade q8_0 / 131K override. The 200 W
power cap remains mandatory.

## Storage and staging

The wave-0 Sync hook downloads the GGUF and F16 projector from the pinned
Hugging Face revision, verifies their SHA-256 digests, and writes them to
`192.168.10.133:/mnt/ai-pool/llama-cpp`. The wave-1 server mounts that share
read-only.

The vLLM model share and compile cache remain intact for rollback. The retired
syv-ai `qwen38-3090` application was removed; ArgoCD prunes its namespace and
Longhorn compile-cache PVC, while the shared NFS model store remains retained.

## App wiring

All deployed consumers use:

- endpoint: `http://llama-cpp-service.llama-cpp.svc.cluster.local:8080/v1`
- model: `qwen3.8-27b`

This includes Open WebUI, Perplexica, LiteLLM, Hindsight, Presenton, HolmesGPT,
Keep, Karakeep, World Monitor, Project NOMAD, News Reader, Deal Scout, and the
n8n Qwen workflows. The compatibility hostname `https://vllm.vanillax.me/v1`
now routes to the same llama.cpp Service so external clients do not need an
immediate endpoint migration.

## Changing the served model

The served id is `--alias` in `my-apps/ai/llama-cpp/deployment.yaml`. Roll every
consumer in the same change if it changes: several background jobs treat LLM
failures as best-effort and otherwise fail silently.
