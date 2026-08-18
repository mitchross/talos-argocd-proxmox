# AI model catalog

Current model inventory, runtime ownership, and app wiring for the local
chat-model paths. The GPU swap procedure lives in
[`gpu-scale-swap.md`](gpu-scale-swap.md); the single-card capacity result lives
in [`single-vs-dual-3090.md`](single-vs-dual-3090.md).

## Current state

| Backend | Replicas | Cards | Served model | Status |
|---|---:|---:|---|---|
| vLLM | `1` | **1** | `qwen3.8-27b` | Active backend for every app |
| llama.cpp | `0` | 1 | Qwen 3.8-27B GGUF | Parked |
| ComfyUI / SwarmUI | `0` | 1 | Image-generation models on SMB | Parked |

vLLM holds **one** RTX 3090. The second card is unallocated and available for
another whole-card workload.

## vLLM

Serves a single canonical model id, `qwen3.8-27b`, from
`Qwen3.8-27B-W4A16-AutoRound-3090-int8lmhead` on the read-only
`192.168.10.133:/mnt/ai-pool/vllm` share at `/models`.

The checkpoint is W4A16 AutoRound with `lm_head` requantized to INT8 group-128
and `embed_tokens` left BF16. That combination loads on **stock** vLLM:
`qwen3_5.py` already passes `quant_config` to `ParallelLMHead`, and
`ParallelLMHead` is routed to the linear WNA16 path, which supports 8 bits.
Only quantizing `embed_tokens` would require a patched image.

Text-only. The deployment runs `--language-model-only`, so the vision tower is
not loaded and image input is unavailable.

> A patched image that also wires the quantized-embedding path exists at
> `ghcr.io/mitchross/vllm-qwen38` and is **parked**. It buys roughly 7K more
> cache tokens. Use it only if a workload demonstrably needs that margin.

## Storage boundaries

The model stores are intentionally separate:

- vLLM mounts `192.168.10.133:/mnt/ai-pool/vllm` **read-only** at `/models`.
  Writing to it requires a separate read-write mount; the share is exported to
  the cluster subnet.
- llama.cpp mounts `192.168.10.133:/mnt/ai-pool/llama-cpp` at `/models`.
- SMB `//192.168.10.133/comfyui` is image-generation storage, unrelated to the
  chat-model catalog.

Do not delete unused NAS files as part of API-catalog cleanup. A llama.cpp model
is selectable only when it has a preset in `my-apps/ai/llama-cpp/presets.ini`.

## llama.cpp API catalog (parked)

When scaled up, llama.cpp advertises two presets over one GGUF and projector:

| API model | Thinking | Sampling | Use |
|---|---|---|---|
| `qwen3.8` | Enabled | `temp=1.0`, `top_p=0.95`, `top_k=20` | Chat and vision |
| `qwen3.8-nothink` | Disabled | `temp=0.7`, `top_p=0.8`, `top_k=20`, `presence_penalty=1.5` | Title/tag tasks |

`--models-max 1` keeps one preset process resident. Switching between the two
can reload the same weights even though both point at one file, so keep
interactive traffic on `qwen3.8`.

## App wiring

`my-apps/ai/open-webui/open-webui-configmap.env` is authoritative for Open WebUI
and points at `vllm-service` with `qwen3.8-27b` for default, vision and task
models. `ENABLE_PERSISTENT_CONFIG=False` prevents stale database settings from
overriding GitOps configuration.

Because vLLM is text-only in the current configuration, `VISION_MODELS` will not
produce image understanding until either the vision tower is re-enabled or
llama.cpp is scaled up for that purpose.

> **Known gap:** several consumers still request the retired id `qwen3.6-27b`
> and will 404 — including LiteLLM, Presenton, Hindsight, WorldMonitor,
> Karakeep, Project NOMAD, the news-reader Temporal worker, and some n8n
> workflows. Grep for `qwen3.6-27b` under `my-apps/` before assuming an app
> works. Rolling these to `qwen3.8-27b` is outstanding.

## Changing the served model

The served id is `--served-model-name` in `my-apps/ai/vllm/deployment.yaml`.
Keep it to a single canonical id so model selectors are not cluttered with
aliases, and roll every consumer in the same change — a renamed id silently
404s for anything left behind.
