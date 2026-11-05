# AI stack guide

Local AI inference uses official Qwen3.8-27B FP8 on stock vLLM (version pinned in `vllm/deployment.yaml`) with
both RTX 3090s (TP=2), FP8 KV and native vision. GPU allocations are whole-card
with time-slicing off. The server ceiling is 262,144 tokens; speculation is off.

Local Qwen defaults to explicit xhigh reasoning with preservation enabled.
Low and medium remain available for less reasoning, and explicit off requests
use their separate sampler. More reasoning can take longer and is not a
measured accuracy improvement. See [the vLLM runbook](vllm/README.md) for the
canonical runtime, source references and reasoning acceptance checks.

ComfyUI and SwarmUI are parked while vLLM owns both cards. The API model is
`qwen3.8-27b`.

Strata test (temporary): vLLM is parked and [Strata](strata/README.md) runs
`qwen3.8-flash-next` on both cards; `qwen3.8-27b` falls back to `deepseek-flash`
(paid) in LiteLLM. Revert the test PR to end it.

For coding, follow the [Pi.dev setup guide](../../docs/domains/ai-gpu/pi-agent-local-dev.md).
Pi's local defaults and launcher also need the companion dotfiles update.
ArgoCD does not update workstation settings. The
[dual-3090 capacity audit](../../docs/domains/ai-gpu/3090-llm-optimization.md)
separates historical memory measurements from current operating guidance.

### Using with OpenClaw / other tools

Applications use the authenticated LiteLLM gateway's OpenAI-compatible API at
`/v1/chat/completions`. On a workstation with `LITELLM_API_KEY` provisioned
outside Git:

```bash
export OPENAI_BASE_URL="https://litellm.vanillax.me/v1"
export OPENAI_API_KEY="${LITELLM_API_KEY:?Set the gateway key outside Git first}"
```

Select `qwen3.8-27b` for local-only requests. Direct vLLM endpoints are for
diagnostics and bypass gateway telemetry. See the
[model catalog](../../docs/domains/ai-gpu/model-catalog.md) for route boundaries.

## Image generation (ComfyUI)

ComfyUI is parked while vLLM owns both cards. The workflows below are retained
for a deliberate [GPU scale-swap](../../docs/domains/ai-gpu/gpu-scale-swap.md).

### Text-to-image: Z-Image-Turbo

Alibaba's S3-DiT architecture. Artificial Analysis ranks it #1 among open-source image models. It renders
finer detail and a more filmic look than FLUX, and renders English and Chinese text. Apache 2.0.

| Property | Value |
|----------|-------|
| Model | `z_image_turbo_bf16.safetensors` (~12GB BF16, auto-cast to FP8 at inference) |
| Text encoders | `clip_l.safetensors` + `t5xxl_fp8_e4m3fn.safetensors` (separate) |
| VAE | `ae.safetensors` (FLUX VAE) |
| VRAM | ~12-16GB (model + encoders + VAE swap in/out) |
| Speed | ~8-9 sec on RTX 3090 |
| Steps | 9 (8 DiT forwards), `cfg = 1.0` |
| Resolution | 512x512 to 2048x2048 |

Workflow: `workflows/z-image-turbo-t2i.json`

Upload this workflow in Open WebUI Admin > Settings > Images to generate images in chat.

### Image editing: Qwen-Image-Edit-2511

Instruction-based image editing. It handles style transfer, object insertion and removal, text editing in images,
pose changes, portrait consistency, and multi-person group photo fusion. Apache 2.0.

| Property | Value |
|----------|-------|
| Model | `qwen_image_edit_2511_bf16.safetensors` (~39GB BF16) or `qwen_image_2512_fp8_e4m3fn.safetensors` (~20GB FP8) |
| VRAM | ~20-39GB depending on variant |

### Image-to-text (reverse prompt)

Two options, both preinstalled in the megapak Docker image:

1. Florence-2 (`ComfyUI-Florence2` node) gives structured captions at 3 detail levels, object detection, and OCR.
2. WD14 Tagger (`ComfyUI-WD14-Tagger` node) gives Booru-style tags for recreating images in diffusion models.

Workflows: `workflows/florence2-caption.json`, `workflows/wd14-tagger.json`

For deeper image analysis (visual Q&A, reasoning), use Qwen 3.8 in Open WebUI chat.
Upload an image, then ask questions. This goes through the active vLLM backend, not ComfyUI.
ComfyUI can also call the chat backend's vision API directly via the
`comfyui-llamacpp-client` node (URL:
`http://vllm-service.vllm.svc.cluster.local:8080`). That workflow is parked with
ComfyUI and requests `qwen3.8-27b`, which the active backend serves.

## Video generation (ComfyUI)

Video generation uses Wan 2.2, the #1 open-source video model (86.22% VBench, beats Sora).
It is Apache 2.0 with an MoE architecture (27B total, 14B active per step).

### How Wan 2.2 MoE works

Each generation uses two expert models that run at different noise levels:
- The high noise expert handles early denoising (layout, structure, composition).
- The low noise expert handles late denoising (fine detail, textures, sharpness).

Generation needs both expert files.

### Text-to-video (T2V)

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

Starter workflow: `workflows/wan22-t2v.json` (loads high-noise expert only)

### Image-to-video (I2V)

Same as T2V, but it takes a reference image as the first frame and animates it.

| Property | Value |
|----------|-------|
| High noise model | `wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors` (~14GB) |
| Low noise model | `wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors` (~14GB) |
| CLIP Vision | `clip_vision_h.safetensors` (~1.3GB, I2V only) |
| + same text encoder & VAE as T2V | |

Starter workflow: `workflows/wan22-i2v.json` (loads high-noise expert only)

### Video workflow notes

- **Open WebUI cannot display video.** Use ComfyUI directly at `comfyui.vanillax.me`.
- [kijai/ComfyUI-WanVideoWrapper](https://github.com/kijai/ComfyUI-WanVideoWrapper) powers the video workflows.
- The wrapper switches MoE experts automatically during sampling.
- Use the wrapper's example workflows. ComfyUI copies them to its workflow browser
  on startup, and they load both expert models (high noise and low noise). The included
  `workflows/wan22-*.json` files are starter templates that may need adjusting for full MoE support.
- The wrapper's `example_workflows/` directory is the authoritative source for correct node wiring.

## ComfyUI Extensions

### Gallery and prompt management

| Extension | Purpose | Source |
|-----------|---------|--------|
| **ComfyUI-Gallery** | Real-time output gallery with filtering and search | [PanicTitan/ComfyUI-Gallery](https://github.com/PanicTitan/ComfyUI-Gallery) |
| **ComfyUI-Prompt-Manager** | Prompt templates, ratings, reuse, analytics | [FranckyB/ComfyUI-Prompt-Manager](https://github.com/FranckyB/ComfyUI-Prompt-Manager) |
| **ComfyUI-WanVideoWrapper** | Wan 2.2 MoE video workflows with GGUF support | [kijai/ComfyUI-WanVideoWrapper](https://github.com/kijai/ComfyUI-WanVideoWrapper) |

Init containers install all of these on pod startup. The megapak image also includes
40+ pre-installed nodes (ComfyUI-GGUF, Florence-2, WD14 Tagger, ComfyUI Manager, etc.).

### Downloading models

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

- `clip_l.safetensors`: CLIP-L text encoder for Z-Image-Turbo (~400MB)
- `t5xxl_fp8_e4m3fn_scaled.safetensors`: T5-XXL FP8 text encoder for Z-Image-Turbo (~5GB)
- `ae.safetensors`: FLUX VAE for Z-Image-Turbo (~300MB)
- `umt5_xxl_fp8_e4m3fn_scaled.safetensors`: UMT5-XXL FP8 for Wan 2.2 video (~6.7GB)
- `wan_2.1_vae.safetensors`: Wan 2.2 video VAE (~254MB)
- `clip_vision_h.safetensors`: CLIP Vision H for I2V (~1.3GB)

### Using pre-made workflows

Text-to-image (Open WebUI):
1. Go to Open WebUI Admin > Settings > Images
2. Set engine to ComfyUI, URL to `http://comfyui-service.comfyui.svc.cluster.local:8188`
3. Upload `workflows/z-image-turbo-t2i.json` as the workflow
4. Users can now generate images in chat.

Text-to-video and image-to-video (ComfyUI direct):
1. Open `comfyui.vanillax.me`
2. Load workflow from file: `workflows/wan22-t2v.json` or `workflows/wan22-i2v.json`
3. Or browse the workflow menu. ComfyUI copies the WanVideoWrapper example workflows there on startup.
4. Edit the prompt and click Queue

Image-to-text and reverse prompt (ComfyUI direct):
1. Load `workflows/florence2-caption.json` for detailed captions
2. Load `workflows/wd14-tagger.json` for diffusion-optimized tags
3. Drag and drop your image onto the LoadImage node

## Open WebUI configuration

### Performance tuning

| Setting | Value | Why |
|---------|-------|-----|
| `K8S_FLAG` | `True` | Kubernetes-specific tuning |
| `THREAD_POOL_SIZE` | `500` | Default 40 causes freezes under load |
| `CHAT_RESPONSE_STREAM_DELTA_CHUNK_SIZE` | `5` | Batches 5 tokens per SSE push to cut overhead |
| `MODELS_CACHE_TTL` | `300` | Caches the model list for 5 min so the backend gets fewer requests |
| `ENABLE_BASE_MODELS_CACHE` | `False` | Avoid retaining a stale model catalog during the evaluation |
| `AIOHTTP_CLIENT_TIMEOUT` | `1800` | 30 min, matching the HTTPRoute timeout |
| `ENABLE_AUTOCOMPLETE_GENERATION` | `False` | Fired on every keystroke: high load, low value |

### Task model

Background tasks (title generation, chat tagging, follow-up suggestions) use
`qwen3.8-27b`. Open WebUI defaults to xhigh reasoning; lightweight tasks
may opt down or out explicitly, following the policy in the vLLM runbook.

### RAG tuning

| Setting | Value | Why |
|---------|-------|-----|
| `CHUNK_SIZE` | `800` | Smaller chunks improve precision with hybrid search |
| `CHUNK_OVERLAP` | `150` | 18% overlap preserves cross-chunk context |
| `RAG_SYSTEM_CONTEXT` | `True` | Injects RAG into the system message for KV cache reuse |
| `ENABLE_QUERIES_CACHE` | `True` | Reuse LLM-generated search queries |

### Image generation

Open WebUI connects to the ComfyUI backend:
```
IMAGE_GENERATION_ENGINE: comfyui
COMFYUI_BASE_URL: http://comfyui-service.comfyui.svc.cluster.local:8188
IMAGE_STEPS: 9  (Z-Image-Turbo optimal)
```

## Network layout

| Service | Internal URL | External URL |
|---------|-------------|-------------|
| vLLM (LLM backend) | `vllm-service.vllm.svc:8080` | `vllm.vanillax.me`, `llama.vanillax.me` |
| Open WebUI | `open-webui-service.open-webui.svc:8080` | `open-webui.vanillax.me` |
| ComfyUI | `comfyui-service.comfyui.svc:8188` | `comfyui.vanillax.me` |
| SearXNG | `searxng.searxng.svc:8080` | -- |

Routes attach to `gateway-internal-technitium` (LAN only). LLM and Open WebUI routes have 30-minute timeouts.

## Storage

| Service | Type | Size | Path |
|---------|------|------|------|
| vLLM | NFS (static PV, CSI) | 1Ti | `192.168.10.133:/mnt/ai-pool/vllm` |
| ComfyUI | NFS (static PV, CSI) | 250Gi | `192.168.10.133:/mnt/BigTank/k8s/comfyui` |
| Open WebUI | Longhorn | 10Gi | Dynamic PVC |

NFS mounts use `nconnect=16` over 10G for fast model loading. Performance depends on Talos kernel tuning. `read_ahead_kb` must be 16384+ (set by a udev rule in the cluster template). `sunrpc.tcp_slot_table_entries` must be 128+ (set by sysctl). Without these, NFS caps at ~140 MB/s regardless of link speed.

## Caveats

### ComfyUI model swapping

ComfyUI loads one model at a time into VRAM. Switching between image and video models
requires unloading one and loading the other (~10-15 sec). That works for single-user
interactive use but not for concurrent generation.

### Video generation limitations

- **Open WebUI cannot display video.** Run video workflows directly in ComfyUI.
- Wan 2.2 video clips are ~5 seconds per generation at 832x480 on 24GB VRAM
- Higher resolutions need more VRAM. fp8_scaled models are ~14GB each.
- Two expert files (~28GB pair) exceed single GPU VRAM. `force_offload: true` swaps between experts.
