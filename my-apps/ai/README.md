# AI Stack Guide

Local AI infrastructure running on dual RTX 3090s (48GB VRAM) + 400GB system RAM.

## Architecture

```
                        Open WebUI (chat UI)
                       /        |         \
                      /         |          \
           llama-server    ComfyUI      SearXNG
           (LLM inference) (image+video) (web search)
           port 8080       port 8188
           ┌──────────┐   ┌──────────────────────┐
           │ 4 models │   │ Z-Image-Turbo (t2i)  │
           │ via       │   │ Qwen-Image-Edit (i2i)│
           │ presets   │   │ Wan 2.2 T2V (video)  │
           └──────────┘   │ Wan 2.2 I2V (video)  │
           2x RTX 3090    │ Florence-2 (caption)  │
           (48GB VRAM)    │ WD14 Tagger (tags)   │
                          └──────────────────────┘
                          1x RTX 3090 (24GB VRAM)
```

## LLM Models (llama-cpp)

All models served via a single `llama-server` with multi-model routing (`--models-max 8`).
Models load on-demand and swap in/out of VRAM.

| Preset | Model | Active Params | VRAM | Context | Use Case |
|--------|-------|--------------|------|---------|----------|
| `reasoning - nemotron3-nano` | Nemotron-3-Nano-30B-A3B Q4_K_XL | 3B (MoE) | ~15GB | 32K | Chat, background tasks (title gen, tagging) |
| `coder - qwen3-coder-next` | Qwen3-Coder-Next-80B-A3B Q3_K_XL | 3B (MoE) | ~37GB | 256K | Coding, tool calling, Claude Code CLI |
| `vision - qwen3-vl-thinking` | Qwen3-VL-30B-A3B-Thinking Q8_0 | 3B (MoE) | ~48GB | 32K | Image understanding, OCR |
| `experimental slow - qwen3.5` | Qwen3.5-397B-A17B Q4_K_XL | 17B (MoE) | 48GB+RAM | 128K | General reasoning (~5-15 tok/s, uses cpu-moe) |

### Key llama-server Optimizations

| Setting | Value | Why |
|---------|-------|-----|
| `cache-type-k = q8_0` | All models | Halves KV key cache VRAM (~0.002 perplexity cost) |
| `cache-type-v = q4_0` | All models | Thirds KV value cache VRAM (values tolerate aggressive quant) |
| `cpu-moe = 1` | Qwen3.5 only | Keeps attention on GPU, offloads MoE experts to CPU. Much faster than unified memory swapping |
| `--no-mmap` | Global | Prevents page fault stalls during inference (we have 400GB RAM) |
| `-b 4096 -ub 1024` | Global | Larger batch sizes for faster prompt processing |
| `--parallel 1` | Global | Single-user -- maximize VRAM for context, not concurrent slots |
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

## Image Generation (ComfyUI)

ComfyUI runs on a dedicated RTX 3090. Models swap in/out of VRAM as workflows require.

### Text-to-Image: Z-Image-Turbo

Alibaba's S3-DiT architecture. #1 ranked open-source image model (Artificial Analysis). Better fine detail
and more natural "filmic" look than FLUX. Excellent bilingual text rendering (EN/CN). Apache 2.0.

| Property | Value |
|----------|-------|
| Model | `z_image_turbo_bf16.safetensors` (~12GB BF16, auto-cast to FP8 at inference) |
| Text encoders | `clip_l.safetensors` + `t5xxl_fp8_e4m3fn.safetensors` (separate) |
| VAE | `ae.safetensors` (FLUX VAE) |
| VRAM | ~12-16GB (model + encoders + VAE swap in/out) |
| Speed | ~8-9 sec on RTX 3090 |
| Steps | 9 (8 DiT forwards), `cfg = 1.0` |
| Resolution | 512x512 to 2048x2048 |

**Workflow**: `workflows/z-image-turbo-t2i.json`

Upload this workflow in **Open WebUI Admin > Settings > Images** for chat-based image generation.

### Image Editing: Qwen-Image-Edit-2511

Instruction-based image editing. Handles style transfer, object insertion/removal, text editing in images,
pose manipulation, portrait consistency, and multi-person group photo fusion. Apache 2.0.

| Property | Value |
|----------|-------|
| Model | `qwen_image_edit_2511_bf16.safetensors` (~39GB BF16) or `qwen_image_2512_fp8_e4m3fn.safetensors` (~20GB FP8) |
| VRAM | ~20-39GB depending on variant |

### Image-to-Text (Reverse Prompt)

Two options, both pre-installed in the megapak Docker image:

1. **Florence-2** (`ComfyUI-Florence2` node) -- Structured captions at 3 detail levels + object detection + OCR
2. **WD14 Tagger** (`ComfyUI-WD14-Tagger` node) -- Booru-style tags optimized for recreating images in diffusion models

**Workflows**: `workflows/florence2-caption.json`, `workflows/wd14-tagger.json`

For deeper image analysis (visual Q&A, reasoning), use **Qwen3-VL** via Open WebUI chat
(upload image -> ask questions). This goes through llama-server, not ComfyUI.

## Video Generation (ComfyUI)

Video generation uses **Wan 2.2** -- #1 open-source video model (86.22% VBench, beats Sora).
Apache 2.0, MoE architecture (27B total / 14B active per step).

### How Wan 2.2 MoE Works

Each generation uses TWO expert models that run at different noise levels:
- **High noise expert** -- Handles early denoising (layout, structure, composition)
- **Low noise expert** -- Handles late denoising (fine detail, textures, sharpness)

Both expert files are required for proper generation.

### Text-to-Video (T2V)

| Property | Value |
|----------|-------|
| High noise model | `wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors` (~14GB) |
| Low noise model | `wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors` (~14GB) |
| Text encoder | `umt5_xxl_fp8_e4m3fn_scaled.safetensors` (~6.7GB) |
| VAE | `wan_2.1_vae.safetensors` (~254MB) |
| Resolution | 832x480 (recommended for 24GB VRAM) |
| Frames | 81 (~5 seconds at 16fps) |
| Steps | 30 |
| Speed | ~3-6 min per clip on RTX 3090 |

**Starter workflow**: `workflows/wan22-t2v.json` (loads high-noise expert only)

### Image-to-Video (I2V)

Same as T2V but takes a reference image as the first frame and animates it.

| Property | Value |
|----------|-------|
| High noise model | `wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors` (~14GB) |
| Low noise model | `wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors` (~14GB) |
| CLIP Vision | `clip_vision_h.safetensors` (~1.3GB, I2V only) |
| + same text encoder & VAE as T2V | |

**Starter workflow**: `workflows/wan22-i2v.json` (loads high-noise expert only)

### Video Workflow Notes

- **Open WebUI cannot display video** -- use ComfyUI directly at `comfyui.vanillax.me`
- Video workflows are powered by [kijai/ComfyUI-WanVideoWrapper](https://github.com/kijai/ComfyUI-WanVideoWrapper)
- The wrapper handles MoE expert switching automatically during sampling
- **Use the wrapper's example workflows** -- they are auto-copied to ComfyUI's workflow browser
  on startup and correctly load BOTH expert models (high noise + low noise). The included
  `workflows/wan22-*.json` files are starter templates that may need adjusting for full MoE support.
- The wrapper's `example_workflows/` directory is the authoritative source for correct node wiring

## ComfyUI Extensions

### Gallery & Prompt Management

| Extension | Purpose | Source |
|-----------|---------|--------|
| **ComfyUI-Gallery** | Real-time output gallery with filtering and search | [PanicTitan/ComfyUI-Gallery](https://github.com/PanicTitan/ComfyUI-Gallery) |
| **ComfyUI-Prompt-Manager** | Prompt templates, ratings, reuse, analytics | [FranckyB/ComfyUI-Prompt-Manager](https://github.com/FranckyB/ComfyUI-Prompt-Manager) |
| **ComfyUI-WanVideoWrapper** | Wan 2.2 MoE video workflows with GGUF support | [kijai/ComfyUI-WanVideoWrapper](https://github.com/kijai/ComfyUI-WanVideoWrapper) |

All installed automatically via init containers on pod startup. The megapak image also includes
40+ pre-installed nodes (ComfyUI-GGUF, Florence-2, WD14 Tagger, ComfyUI Manager, etc.).

### Downloading Models

Main diffusion models (Z-Image-Turbo, Wan 2.2, Qwen-Image-Edit) are pre-loaded on the NFS share.
A one-time Kubernetes Job downloads auxiliary files (text encoders, VAEs, CLIP vision) if missing (~15GB):

```bash
kubectl apply -f my-apps/ai/comfyui/download-models-job.yaml

# Monitor progress
kubectl logs -f -n comfyui job/comfyui-download-models

# Verify files
kubectl exec -n comfyui deploy/comfyui -- ls -lh /root/ComfyUI/models/diffusion_models/
```

The job downloads (skips existing):

- `clip_l.safetensors` -- CLIP-L text encoder for Z-Image-Turbo (~400MB)
- `t5xxl_fp8_e4m3fn.safetensors` -- T5-XXL FP8 text encoder for Z-Image-Turbo (~5GB)
- `ae.safetensors` -- FLUX VAE for Z-Image-Turbo (~300MB)
- `umt5_xxl_fp8_e4m3fn_scaled.safetensors` -- UMT5-XXL FP8 for Wan 2.2 video (~6.7GB)
- `wan_2.1_vae.safetensors` -- Wan 2.2 video VAE (~254MB)
- `clip_vision_h.safetensors` -- CLIP Vision H for I2V (~1.3GB)

### Using Pre-made Workflows

**Text-to-Image (Open WebUI):**
1. Go to Open WebUI Admin > Settings > Images
2. Set engine to ComfyUI, URL to `http://comfyui-service.comfyui.svc.cluster.local:8188`
3. Upload `workflows/z-image-turbo-t2i.json` as the workflow
4. Users can now generate images in chat

**Text-to-Video / Image-to-Video (ComfyUI direct):**
1. Open `comfyui.vanillax.me`
2. Load workflow from file: `workflows/wan22-t2v.json` or `workflows/wan22-i2v.json`
3. Or browse the workflow menu -- example workflows from WanVideoWrapper are auto-copied on startup
4. Edit the prompt and click Queue

**Image-to-Text / Reverse Prompt (ComfyUI direct):**
1. Load `workflows/florence2-caption.json` for detailed captions
2. Load `workflows/wd14-tagger.json` for diffusion-optimized tags
3. Drag-and-drop your image onto the LoadImage node

## Open WebUI Configuration

### Performance Tuning

| Setting | Value | Why |
|---------|-------|-----|
| `K8S_FLAG` | `True` | Kubernetes-specific optimizations |
| `THREAD_POOL_SIZE` | `500` | Default 40 causes freezes under load |
| `CHAT_RESPONSE_STREAM_DELTA_CHUNK_SIZE` | `5` | Batch 5 tokens per SSE push -- less overhead |
| `MODELS_CACHE_TTL` | `300` | Cache model list 5 min -- stops hammering llama-server |
| `ENABLE_BASE_MODELS_CACHE` | `True` | Faster startup, fewer API calls |
| `AIOHTTP_CLIENT_TIMEOUT` | `1800` | 30 min to match HTTPRoute timeout |
| `ENABLE_AUTOCOMPLETE_GENERATION` | `False` | Was firing on every keystroke -- high load, low value |

### Task Model

Background tasks (title generation, chat tagging, follow-up suggestions) use
`reasoning - nemotron3-nano` -- fast 3B active MoE model. Previously this was set to
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
| SearXNG | `searxng.searxng.svc:8080` | -- |

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
have this, flash attention silently falls back to f16 KV cache. Test by checking VRAM usage --
if 262K context still uses ~40GB of KV cache, the flag is missing and you need a newer build.

### Experimental Slow Model (Qwen3.5-397B)

Even with `cpu-moe = 1`, the 397B model will be significantly slower than the 3B-active models
because the 17B active parameters still require substantial compute, and expert weights shuttle
between CPU and GPU. Expect ~5-15 tok/s vs ~70 tok/s for the coder. It's the "quality over speed"
option for complex reasoning. Named "experimental slow" in the model list to set expectations.

### ComfyUI Model Swapping

ComfyUI loads one model at a time into VRAM. Switching between image and video models
requires unloading one and loading the other (~10-15 sec). This is fine for single-user
interactive use but won't work for concurrent generation.

### Video Generation Limitations

- **Open WebUI cannot display video** -- video workflows must be run directly in ComfyUI
- Wan 2.2 video clips are ~5 seconds per generation at 832x480 on 24GB VRAM
- Higher resolutions need more VRAM -- fp8_scaled models are ~14GB each
- Two expert files (~28GB pair) exceed single GPU VRAM -- `force_offload: true` swaps between experts
