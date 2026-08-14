# AI model catalog

Current model inventory, runtime ownership, and app wiring for the two local
chat-model paths. The GPU swap procedure lives in
[`gpu-scale-swap.md`](gpu-scale-swap.md).

## Current evaluation state

| Backend | Replicas | Stored model | Runtime status |
|---|---:|---|---|
| vLLM | `0` | Qwen 3.6-27B AWQ BF16-INT4 | Parked and unchanged |
| llama.cpp | `1` | Qwen 3.8-27B UD-Q4_K_XL GGUF | Active OpenWebUI backend |
| ComfyUI / SwarmUI | `0` | Image-generation models on SMB | Parked |

Qwen 3.8 does not yet have the AWQ quant needed by this cluster's Ampere vLLM
path. The evaluation therefore uses the existing GGUF on llama.cpp while the
proven Qwen 3.6 vLLM deployment remains available to restore later.

## Storage boundaries

The model stores are intentionally separate:

- vLLM mounts `192.168.10.133:/mnt/ai-pool/vllm` read-only at `/models`.
  Its selected directory is `Qwen3.6-27B-AWQ-BF16-INT4`.
- llama.cpp mounts `192.168.10.133:/mnt/ai-pool/llama-cpp` at `/models`.
  The active files are `Qwen3.8-27B-UD-Q4_K_XL.gguf` and
  `mmproj-qwen3.8-BF16.gguf`.
- SMB `//192.168.10.133/comfyui` is ComfyUI/image-generation storage. Qwen
  image models or helper LLMs there are unrelated to OpenWebUI's chat-model
  catalog.

Do not delete unused NAS files as part of API-catalog cleanup. A model is
selectable only when it has a preset in `my-apps/ai/llama-cpp/presets.ini`.

## llama.cpp API catalog

llama.cpp advertises exactly two presets over one GGUF and projector:

| API model | Thinking | Sampling | Consumer |
|---|---|---|---|
| `qwen3.8` | Enabled | `temp=1.0`, `top_p=0.95`, `top_k=20` | OpenWebUI chat and vision |
| `qwen3.8-nothink` | Disabled | `temp=0.7`, `top_p=0.8`, `top_k=20`, `presence_penalty=1.5` | OpenWebUI title/tag tasks |

`--models-max 1` means only one preset process is resident. Switching between
the two can reload the same weights even though both point at one file, so keep
interactive traffic on `qwen3.8` and reserve `qwen3.8-nothink` for short
background work.

## OpenWebUI wiring

`my-apps/ai/open-webui/open-webui-configmap.env` is authoritative:

- `OPENAI_API_BASE_URL(S)` → llama.cpp service
- `DEFAULT_MODELS=qwen3.8`
- `VISION_MODELS=qwen3.8`
- `TASK_MODEL=qwen3.8-nothink`
- `TASK_MODEL_EXTERNAL=qwen3.8-nothink`
- `CONTEXT_WINDOW=65536`
- `ENABLE_PERSISTENT_CONFIG=False`, preventing stale database settings from
  overriding GitOps configuration

OpenWebUI is the only app moved to llama.cpp for this evaluation. Perplexica,
Project NOMAD, Karakeep, LiteLLM, Presenton, and other normal consumers remain
wired to `vllm-service` / `qwen3.6-27b`; they are unavailable while vLLM is at
zero replicas.

## Ending the evaluation

Restore the normal backend in one GitOps change:

1. Set llama.cpp to `replicas: 0` and vLLM to `replicas: 1`.
2. Point OpenWebUI's base URL back to vLLM.
3. Restore its default/vision/task model IDs to `qwen3.6-27b` and the validated
   Qwen 3.6 sampling values.
4. Verify `/v1/models` before relying on dependent applications.

Never scale vLLM up while llama.cpp plus another GPU workload would make the
requested card total exceed two.
