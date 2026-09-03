# Open WebUI

Self-hosted ChatGPT-style frontend for the cluster's local AI stack.

## Active wiring

```text
https://open-webui.vanillax.me
        |
        v
Open WebUI
  |-- llama.cpp -> qwen3.8-27b (chat / reasoning / tools / vision)
  |-- SearXNG   -> web search
  |-- MCPO      -> MCP-backed tools
  |-- ComfyUI   -> image generation
  `-- local CPU SentenceTransformer / Whisper -> RAG + STT
```

The canonical LLM connection is:

- endpoint: `http://llama-cpp-service.llama-cpp.svc.cluster.local:8080/v1`
- model: `qwen3.8-27b`
- context: `65536`

`open-webui-configmap.env` is the source of truth. Persistent Open WebUI model
configuration is disabled so GitOps values win over stale DB-stored connection
settings.

## Current model profile

| Role | Value |
|---|---|
| Chat/default | `qwen3.8-27b` |
| Vision | `qwen3.8-27b` |
| Task/title model | `qwen3.8-27b` |
| Backend | stock llama.cpp `b10752` |
| Target | Qwen3.8-27B `UD-Q4_K_XL` |
| Context | 65,536 |
| MTP | Q4_0 draft, `n-max=2` |
| KV | q8_0 target + draft |
| Sampling | temp 0.7, top-p 0.8, min-p 0; server also owns top-k 20 and presence penalty 1.5 |
| Vision projector | BF16 |

The production backend defaults to low reasoning. Open WebUI can request more
reasoning per conversation, but do not make xhigh the everyday default.

## Performance baseline

After the 2026-09-03 cutover, ordinary Open WebUI responses measured roughly
42-43 generated tok/s on the single RTX 3090. Under generation the card showed
about 22.7 GiB VRAM used and high GPU utilization at the 220 W cap.

## Features

- **Web search**: SearXNG (`WEB_SEARCH_*`, `SEARXNG_QUERY_URL`).
- **RAG**: local CPU embeddings, hybrid BM25/vector retrieval.
- **Tools**: MCPO endpoints from `OPENAPI_API_ENDPOINTS`.
- **Vision**: the same `qwen3.8-27b` model; no separate vision LLM.
- **Image generation**: ComfyUI, separate from the chat model.
- **Voice**: local Whisper STT; configured TTS remains OpenAI-compatible.

## Important env settings

- `ENABLE_PERSISTENT_CONFIG=False`: GitOps model/backend settings stay authoritative.
- `CONTEXT_WINDOW=65536`: keep aligned with llama.cpp `--ctx-size`.
- `DEFAULT_MODELS`, `VISION_MODELS`, `TASK_MODEL`, `TASK_MODEL_EXTERNAL`: all `qwen3.8-27b`.
- `AIOHTTP_CLIENT_TIMEOUT=1800`: matches long-generation Gateway timeouts.
- `ENABLE_AUTOCOMPLETE_GENERATION=False`: avoids constant background LLM traffic.
- `USE_CUDA_DOCKER=false`: Open WebUI stays CPU-only; llama.cpp owns the RTX 3090.

## Debugging

Check the backend directly before blaming the UI:

```bash
kubectl -n llama-cpp get pods
kubectl -n llama-cpp logs deploy/llama-cpp-server --tail=200
kubectl -n llama-cpp exec deploy/llama-cpp-server -- nvidia-smi
curl -s https://llama.vanillax.me/v1/models
```

Then confirm the UI pod received the rendered ConfigMap:

```bash
kubectl -n open-webui get pods
kubectl -n open-webui describe deploy/open-webui
```

## GPU ownership

Open WebUI itself does not request a GPU. The single RTX 3090 belongs to the
active llama.cpp Deployment. ComfyUI/SwarmUI/vLLM are mutually exclusive
whole-card workloads and remain parked unless a GitOps scale-swap is performed.
