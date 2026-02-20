# AI Stack Guide

Local AI infrastructure running on dual RTX 3090s (48GB VRAM) + 400GB system RAM.

## Architecture

```
                        Open WebUI (chat UI)
                       /        |         \
                      /         |          \
           llama-server    ComfyUI      SearXNG
           (LLM inference) (image gen)  (web search)
           port 8080       port 8188
           ┌──────────┐   ┌──────────────────────┐
           │ 4 models │   │ Z-Image-Turbo (t2i)  │
           │ via       │   │ Qwen-Image-Edit (i2i)│
           │ presets   │   │ Florence-2 (i2t)     │
           └──────────┘   │ WD14 Tagger (tags)   │
           2x RTX 3090    └──────────────────────┘
           (48GB VRAM)    1x RTX 3090 (24GB VRAM)
```

## LLM Models (llama-cpp)

All models served via a single `llama-server` with multi-model routing (`--models-max 8`).
Models load on-demand and swap in/out of VRAM.

| Preset | Model | Active Params | VRAM | Context | Use Case |
|--------|-------|--------------|------|---------|----------|
| `reasoning - nemotron3-nano` | Nemotron-3-Nano-30B-A3B Q4_K_XL | 3B (MoE) | ~15GB | 32K | Chat, background tasks (title gen, tagging) |
| `coder - qwen3-coder-next` | Qwen3-Coder-Next-80B-A3B Q3_K_XL | 3B (MoE) | ~37GB | 256K | Coding, tool calling, Claude Code CLI |
| `vision - qwen3-vl-thinking` | Qwen3-VL-30B-A3B-Thinking Q8_0 | 3B (MoE) | ~48GB | 32K | Image understanding, OCR |
| `general - qwen3.5` | Qwen3.5-397B-A17B Q4_K_XL | 17B (MoE) | 48GB+RAM | 128K | General reasoning (slow, uses cpu-moe) |

### Key llama-server Optimizations

| Setting | Value | Why |
|---------|-------|-----|
| `cache-type-k = q8_0` | All models | Halves KV key cache VRAM (~0.002 perplexity cost) |
| `cache-type-v = q4_0` | All models | Thirds KV value cache VRAM (values tolerate aggressive quant) |
| `cpu-moe = 1` | Qwen3.5 only | Keeps attention on GPU, offloads MoE experts to CPU. Much faster than unified memory swapping |
| `--no-mmap` | Global | Prevents page fault stalls during inference (we have 400GB RAM) |
| `-b 4096 -ub 1024` | Global | Larger batch sizes for faster prompt processing |
| `--parallel 1` | Global | Single-user — maximize VRAM for context, not concurrent slots |
| `CUDA_SCALE_LAUNCH_QUEUES=4x` | Env var | Larger CUDA command buffer for dual-GPU kernel launches |

### Using with Claude Code CLI

llama-server natively supports the Anthropic Messages API at `/v1/messages`. No proxy needed:

```bash
export ANTHROPIC_BASE_URL="http://llama.vanillax.me"
export ANTHROPIC_AUTH_TOKEN="no-key-required"
export ANTHROPIC_API_KEY=""
claude --model "coder - qwen3-coder-next"
```

### Using with OpenClaw / Other Tools

llama-server also exposes the OpenAI-compatible API at `/v1/chat/completions`:

```bash
export OPENAI_BASE_URL="http://llama.vanillax.me/v1"
export OPENAI_API_KEY="any-value"
```

Works with: OpenClaw, Aider, Continue.dev, OpenCode, or any OpenAI-compatible client.

## Image Models (ComfyUI)

ComfyUI runs on a dedicated RTX 3090. Models swap in/out of VRAM as workflows require.

| Model | Type | VRAM | Speed (3090) | Use Case |
|-------|------|------|-------------|----------|
| **Z-Image-Turbo** (6B) | Text-to-image | 12-16GB BF16, 6GB GGUF | ~8-9 sec | Primary image generation |
| **Qwen-Image-Edit-2511** (20B) | Image editing | ~10GB GGUF Q4 | ~30-60 sec w/ Lightning | Style transfer, object removal, text editing |
| **Florence-2** (0.77B) | Image-to-text | ~6GB | ~2 sec | Captioning, OCR, object detection |
| **WD14 Tagger** | Image-to-tags | ~2GB | ~1 sec | Tag extraction for prompt recreation |

### Z-Image-Turbo

Alibaba's S3-DiT architecture. #1 ranked open-source image model (Artificial Analysis). Better fine detail
and more natural "filmic" look than FLUX. Excellent bilingual text rendering (EN/CN). Apache 2.0.

- **Inference**: 9 steps (8 DiT forwards), `guidance_scale = 0.0`
- **Resolution**: 512x512 to 2048x2048
- **ComfyUI**: Native official workflow support

### Qwen-Image-Edit-2511

Instruction-based image editing. Handles style transfer, object insertion/removal, text editing in images,
pose manipulation, portrait consistency, and multi-person group photo fusion. Apache 2.0.

- **Lightning LoRA**: Reduces 50 steps to 4 steps (12-25x speedup)
- **ComfyUI**: Native workflow support

### Image-to-Text (Reverse Prompt)

Two options, both pre-installed in the megapak Docker image:

1. **Florence-2** (`ComfyUI-Florence2` node) — Structured captions at 3 detail levels + object detection + OCR
2. **WD14 Tagger** (`ComfyUI-WD14-Tagger` node) — Booru-style tags optimized for recreating images in diffusion models

For deeper image analysis (visual Q&A, reasoning), use **Qwen3-VL** via Open WebUI chat
(upload image → ask questions). This goes through llama-server, not ComfyUI.

### Downloading Models

A one-time Kubernetes Job downloads all required models from HuggingFace into the ComfyUI NFS share:

```bash
kubectl apply -f my-apps/ai/comfyui/download-models-job.yaml

# Monitor progress
kubectl logs -f -n comfyui job/comfyui-download-models

# Verify files
kubectl exec -n comfyui deploy/comfyui -- ls -lh /root/ComfyUI/models/diffusion_models/
```

The job downloads:
- `z_image_turbo_aio_fp8.safetensors` — Z-Image-Turbo (AIO FP8, ~10GB)
- `ae.safetensors` — FLUX VAE (shared, ~300MB)
- `Qwen-Image-Edit-2511-UD-Q4_K_XL.gguf` — Qwen-Image-Edit GGUF
- `Qwen-Image-Edit-2511-Lightning.safetensors` — Lightning LoRA
- `clip_l.safetensors` — CLIP-L text encoder
- `t5xxl_fp8_e4m3fn.safetensors` — T5-XXL FP8 text encoder (~5GB)

After downloading, export a ComfyUI workflow in API format and upload it in
Open WebUI Admin > Settings > Images.

## Open WebUI Configuration

### Performance Tuning

| Setting | Value | Why |
|---------|-------|-----|
| `K8S_FLAG` | `True` | Kubernetes-specific optimizations |
| `THREAD_POOL_SIZE` | `500` | Default 40 causes freezes under load |
| `CHAT_RESPONSE_STREAM_DELTA_CHUNK_SIZE` | `5` | Batch 5 tokens per SSE push — less overhead |
| `MODELS_CACHE_TTL` | `300` | Cache model list 5 min — stops hammering llama-server |
| `ENABLE_BASE_MODELS_CACHE` | `True` | Faster startup, fewer API calls |
| `AIOHTTP_CLIENT_TIMEOUT` | `1800` | 30 min to match HTTPRoute timeout |
| `ENABLE_AUTOCOMPLETE_GENERATION` | `False` | Was firing on every keystroke — high load, low value |

### Task Model

Background tasks (title generation, chat tagging, follow-up suggestions) use
`reasoning - nemotron3-nano` — fast 3B active MoE model. Previously this was set to
`coder - qwen3-coder-next` which was overkill for generating chat titles.

### RAG Tuning

| Setting | Value | Why |
|---------|-------|-----|
| `CHUNK_SIZE` | `800` | Smaller chunks improve precision with hybrid search |
| `CHUNK_OVERLAP` | `150` | 18% overlap preserves cross-chunk context |
| `RAG_SYSTEM_CONTEXT` | `True` | RAG injected into system message for KV cache reuse |
| `ENABLE_QUERIES_CACHE` | `True` | Reuse LLM-generated search queries |

### Image Generation

Connected to ComfyUI backend:
```
IMAGE_GENERATION_ENGINE: comfyui
COMFYUI_BASE_URL: http://comfyui-service.comfyui.svc.cluster.local:8188
IMAGE_STEPS: 9  (Z-Image-Turbo optimal)
```

## Network Layout

| Service | Internal URL | External URL |
|---------|-------------|-------------|
| llama-server | `llama-cpp-service.llama-cpp.svc:8080` | `llama.vanillax.me` |
| Open WebUI | `open-webui-service.open-webui.svc:8080` | `open-webui.vanillax.me` |
| ComfyUI | `comfyui-service.comfyui.svc:8188` | `comfyui.vanillax.me` |
| SearXNG | `searxng.searxng.svc:8080` | — |

All routes use `gateway-internal` (Cilium Gateway API). LLM and Open WebUI routes have 30-minute timeouts.

## Storage

| Service | Type | Size | Path |
|---------|------|------|------|
| llama-cpp | NFS (static PV, CSI) | 150Gi | `192.168.10.133:/mnt/BigTank/k8s/llama-cpp` |
| ComfyUI | NFS (static PV, CSI) | 250Gi | `192.168.10.133:/mnt/BigTank/k8s/comfyui` |
| Open WebUI | Longhorn | 5Gi | Dynamic PVC |

NFS mounts use `nconnect=16` over 10G for fast model loading.

## Caveats

### KV Cache Quantization Requires Build Flag

The `cache-type-k = q8_0` / `cache-type-v = q4_0` settings require the llama.cpp Docker image
to be compiled with `-DGGML_CUDA_FA_ALL_QUANTS=ON`. If the pre-built `b8006` image doesn't
have this, flash attention silently falls back to f16 KV cache. Test by checking VRAM usage —
if 262K context still uses ~40GB of KV cache, the flag is missing and you need a newer build.

### Qwen3.5-397B is Slow

Even with `cpu-moe = 1`, the 397B model will be significantly slower than the 3B-active models
because the 17B active parameters still require substantial compute, and expert weights shuttle
between CPU and GPU. Expect ~5-15 tok/s vs ~70 tok/s for the coder. It's the "quality over speed"
option for complex reasoning.

### ComfyUI Model Swapping

ComfyUI loads one model at a time into VRAM. Switching between Z-Image-Turbo and
Qwen-Image-Edit requires unloading one and loading the other (~10-15 sec). This is fine
for single-user interactive use but won't work for concurrent generation + editing.

### Qwen-Image-2.0 (Coming Soon)

Alibaba announced Qwen-Image-2.0 (Feb 10, 2026) — a unified 7B model that does both
generation AND editing. Currently API-only, weights expected Q1 2026. When released,
it could replace both Z-Image-Turbo and Qwen-Image-Edit with a single smaller model.
