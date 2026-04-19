# Open WebUI

Self-hosted ChatGPT-style frontend for the cluster's local LLM stack. Wires
Open WebUI up to llama-cpp (OpenAI-compatible API), SearXNG for web search,
ComfyUI for image generation, Kiwix for offline RAG, and an MCP tool proxy
(MCPO) for everything else.

## Architecture

```
                       https://open-webui.vanillax.me
                                   │
                        Gateway (Cilium) → HTTPRoute
                                   │
                           ┌───────┴────────┐
                           │   Open WebUI   │  (this app — Deployment)
                           └───┬───┬──┬──┬──┘
               OpenAI-compat   │   │  │  └── MCPO (tools)
                               │   │  │        ├── mcpo-time (port 8000)
                               │   │  │        ├── mcpo-multi (port 8001, fs/memory/sqlite)
                               │   │  │        └── mcpo-kiwix (port 8002, Kiwix fetch)
                               │   │  └── ComfyUI (image gen) ─→ Z-Image-Turbo / Qwen-Image-Edit
                               │   └── SearXNG (web search)
                               └── llama-cpp-service.llama-cpp:8080/v1  (primary LLM)
```

Open WebUI itself is stateless UI + SQLite (on a PVC). The heavy lifting is
elsewhere: llama-cpp holds the model in VRAM, ComfyUI owns the image-gen GPU,
SearXNG handles search, MCPO exposes tool endpoints as OpenAPI.

## Model & backend

> ⚠️ **Source of truth is `configmap.yaml`.** If you change models, update the
> ConfigMap — don't trust this README over the live config.

Currently wired up (see `configmap.yaml`):

| Role                  | Model / Value                                                  |
|-----------------------|----------------------------------------------------------------|
| Chat backend          | `OPENAI_API_BASE_URL=http://llama-cpp-service.llama-cpp.svc.cluster.local:8080/v1` |
| `DEFAULT_MODELS`      | `qwen3.6 - qwen3.6-35b-a3b` (think — best tool-calling + coding) |
| `VISION_MODELS`       | `qwen3.6 - qwen3.6-35b-a3b` — Qwen 3.6 is multimodal via `mmproj-BF16.gguf` |
| `TASK_MODEL`          | `qwen3.6-nothink - qwen3.6-35b-a3b-nothink` (title gen / tagging — same weights, skips thinking) |
| `TASK_MODEL_EXTERNAL` | `qwen3.6-nothink - qwen3.6-35b-a3b-nothink`                    |
| `CONTEXT_WINDOW`      | `65536` (64K) — **must match** the qwen3.6 preset's `ctx-size` in `my-apps/ai/llama-cpp/configmap.yaml`. If this is smaller, Open WebUI silently trims history / RAG before sending. |
| Sampling              | `TEMPERATURE=0.6`, `TOP_P=0.95`, `MIN_P=0.0` — Qwen 3.6 official "precise" thinking profile. `TOP_K=20` is set by llama-cpp at the preset level. |
| Image generation      | ComfyUI — Z-Image-Turbo (text→img, 9 steps), Qwen-Image-Edit-2511 (edit) |
| Embeddings / STT      | Whisper `medium` (in-pod), OpenAI TTS voice `alloy`            |

Model swap happens server-side (on llama-cpp) and is instant between
think/nothink presets because both point at the same GGUF + mmproj.
Switching between `qwen3.6` and `gemma4` does re-load weights (different
files), so expect a few seconds of dead air on first request after swap.

> Gemma 4 is still served by llama-cpp as a multimodal **fallback** —
> you can select it manually per-chat in the UI. Qwen 3.6 is the default
> for both text and vision routes.

## Performance tuning (ConfigMap)

Non-default env vars that matter, grouped by why they exist:

### FastAPI / HTTP

| Var                                    | Value | Why |
|----------------------------------------|-------|-----|
| `THREAD_POOL_SIZE`                     | `500` | Default (40) chokes under concurrent chat + RAG + tool calls. |
| `AIOHTTP_CLIENT_TIMEOUT`               | `1800` (30 min) | Matches the HTTPRoute timeout so long completions aren't cut off mid-stream. |
| `AIOHTTP_CLIENT_TIMEOUT_MODEL_LIST`    | `30` | Model list probe — llama-cpp can stall briefly when swapping models. |
| `CHAT_RESPONSE_STREAM_DELTA_CHUNK_SIZE`| `5`  | Batch 5 tokens per SSE push. Cuts CPU/network overhead vs per-token flushing. |
| `ENABLE_COMPRESSION_MIDDLEWARE`        | `True` | Gzip HTTP responses — meaningful for large RAG payloads. |
| `MODELS_CACHE_TTL` / `ENABLE_BASE_MODELS_CACHE` | `300` / `True` | Avoid hammering llama-cpp's `/v1/models` on every page nav. |
| `ENABLE_QUERIES_CACHE`                 | `True` | Reuse LLM-generated RAG search queries across similar prompts. |

### RAG

| Var                          | Value  | Why |
|------------------------------|--------|-----|
| `CHUNK_SIZE` / `CHUNK_OVERLAP`| 800 / 150 (~18%) | Smaller chunks improve precision w/ hybrid search; 18% overlap preserves cross-chunk context. |
| `RAG_TOP_K`                  | `10`   | Hybrid search retrieves more; model does the culling. |
| `ENABLE_RAG_HYBRID_SEARCH`   | `True` | BM25 + embedding — better recall on technical content than pure vector. |
| `RAG_SYSTEM_CONTEXT`         | `True` | Inject retrieved chunks into the system message (better for KV cache reuse than stuffing user msg). |
| `USE_CUDA_DOCKER`            | `true` | RAG embeddings run on GPU. |
| `PDF_EXTRACT_IMAGES`         | `True` | Required for vision RAG over PDF diagrams. |

### UX

| Var                                   | Value  | Why |
|---------------------------------------|--------|-----|
| `ENABLE_AUTOCOMPLETE_GENERATION`      | `False` | Fires on every keystroke → massive API load for marginal UX gain. |
| `ENABLE_PERSISTENT_CONFIG`            | `True` | Lets admins edit settings in the UI without losing them on pod restart. |
| `SHOW_THOUGHTS`                       | `True` | Render `<think>` blocks from thinking-capable models. |

## Features

- **Web search** — SearXNG-backed, private. Click `+` in chat to enable per-message. Config: `WEB_SEARCH_*`, `SEARXNG_QUERY_URL`.
- **RAG** — upload PDFs/docs, hybrid (BM25 + embedding) search. See `KIWIX_RAG_INSTRUCTIONS.md` for the offline-encyclopedia RAG setup via `fetch`.
- **Tools via MCPO** — wired through `OPENAPI_API_ENDPOINTS`:
  - `mcpo-time` — current time/date
  - `mcpo-multi` — filesystem, memory, SQLite
  - `mcpo-kiwix` — offline encyclopedia fetch tool
- **Image generation** — ComfyUI backend, 9-step Z-Image-Turbo default, LLM-enhanced prompts (`ENABLE_IMAGE_PROMPT_GENERATION`).
- **Voice** — Whisper `medium` STT in-pod, OpenAI TTS (voice `alloy`).
- **Custom functions** — `function-loader-job.yaml` loads custom functions (e.g., `har-analyzer-function.py`) into the UI.

### What is MCP / MCPO?

**MCP** (Model Context Protocol) is Anthropic's spec for exposing tools to
LLMs (filesystem ops, web fetch, DB queries, etc.). **MCPO** is an OpenAPI
proxy in front of MCP servers, so any OpenAPI-aware client — including Open
WebUI's Tools tab — can call them without speaking MCP natively.

In this cluster, MCPO exposes three tool bundles as OpenAPI endpoints
(`8000/8001/8002`) and Open WebUI auto-registers them via
`OPENAPI_API_ENDPOINTS`. The `Settings → Tools` UI path in the original
README is the *manual* way to register more — the three above are already
wired in via ConfigMap.

## Deployment

Applied by ArgoCD automatically (directory = Application). Files:

| File                      | Purpose                                                          |
|---------------------------|------------------------------------------------------------------|
| `namespace.yaml`          | `open-webui` namespace                                           |
| `configmap.yaml`          | **All** env-based config. Source of truth for behavior.          |
| `deployment.yaml`         | Open WebUI main Deployment (stateful via PVC below)              |
| `pvc.yaml`                | SQLite + uploaded files persist here                             |
| `service.yaml`            | ClusterIP for HTTPRoute                                          |
| `httproute.yaml`          | External HTTPRoute to `open-webui.vanillax.me`                   |
| `mcpo-deployment.yaml`    | MCPO Deployment (three tool bundles, ports 8000/8001/8002)       |
| `mcp-config.yaml`         | Multi-tool server config (filesystem/memory/sqlite)              |
| `mcp-kiwix.yaml`          | Kiwix fetch tool config                                          |
| `function-loader-job.yaml`| One-shot Job — loads `har-analyzer-function.py` into the UI      |
| `kustomization.yaml`      | Ties it all together. **Must list every YAML** under `resources:` |

Force a manual apply (bypassing ArgoCD, for dev):
```bash
kubectl apply -k my-apps/ai/open-webui/
```

## Access

- Public: https://open-webui.vanillax.me (Cloudflare tunnel → gateway-external)

## Troubleshooting

**No models showing up in the UI**
- Check `kubectl logs -n llama-cpp deploy/llama-cpp` — what model name is advertised?
- Compare against `DEFAULT_MODELS` in `configmap.yaml`. They must match exactly, including spaces.

**Tools tab is empty**
- `kubectl logs -n open-webui deploy/mcpo` — MCPO pods crash loudly if the API keys don't match `OPENAPI_API_ENDPOINTS`.
- Test endpoint directly: `kubectl exec -n open-webui deploy/open-webui -- curl -s http://mcpo.open-webui.svc.cluster.local:8000/openapi.json`

**Web search returns nothing**
- Verify SearXNG is alive: `kubectl get pods -n searxng`
- `SEARXNG_QUERY_URL` must include `&format=json` — without JSON format Open WebUI silently drops results.

**Long completions cut off mid-stream**
- `AIOHTTP_CLIENT_TIMEOUT=1800` handles 30-min generations. If you're running longer, bump this *and* the `HTTPRoute` timeout — the shorter of the two wins.

## Gotchas

- **ConfigMap is law.** Changing models/settings in the UI only sticks if
  `ENABLE_PERSISTENT_CONFIG=True` *and* you're editing UI-scoped settings.
  ConfigMap values override on pod restart.
- **MCPO key must match** between the MCPO Deployment env and
  `OPENAPI_API_ENDPOINTS` — format is
  `name:url:api_key;name:url:api_key;…`.
- **PVC is RWO.** Deployment uses `strategy: Recreate` (see
  `my-apps/CLAUDE.md` — RWO + RollingUpdate = Multi-Attach deadlock).
