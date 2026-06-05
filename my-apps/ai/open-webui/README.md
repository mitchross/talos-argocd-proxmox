# Open WebUI

Self-hosted ChatGPT-style frontend for the cluster's local LLM stack. Wires
Open WebUI up to vLLM (OpenAI-compatible API), SearXNG for web search,
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
                               └── vllm-service.vllm:8080/v1  (primary LLM)
```

Open WebUI itself is stateless UI + SQLite (on a PVC). The heavy lifting is
elsewhere: vLLM holds the model in VRAM, ComfyUI owns the image-gen GPU,
SearXNG handles search, MCPO exposes tool endpoints as OpenAPI.

## Model & backend

> ⚠️ **Source of truth is `open-webui-configmap.env`.** If you change models,
> update the env file — don't trust this README over the live config.

Currently wired up (see `open-webui-configmap.env`):

| Role                  | Model / Value                                                  |
|-----------------------|----------------------------------------------------------------|
| Chat backend          | `OPENAI_API_BASE_URL=http://vllm-service.vllm.svc.cluster.local:8080/v1` |
| `DEFAULT_MODELS`      | `qwen3.6-27b` — first `--served-model-name` advertised by vLLM |
| `VISION_MODELS`       | `qwen3.6-27b` |
| `TASK_MODEL`          | `qwen3.6-27b` |
| `TASK_MODEL_EXTERNAL` | `qwen3.6-27b` |
| `CONTEXT_WINDOW`      | `65536` (64K) — keep aligned with vLLM `--max-model-len`. If this is smaller, Open WebUI silently trims history / RAG before sending. |
| Sampling              | `TEMPERATURE=0.6`, `TOP_P=0.95`, `MIN_P=0.0` |
| Image generation      | ComfyUI — Z-Image-Turbo (text→img, 9 steps), Qwen-Image-Edit-2511 (edit) |
| Embeddings / STT      | Whisper `medium` (in-pod), OpenAI TTS voice `alloy`            |

vLLM is served from `my-apps/ai/vllm/deployment.yaml`; the Open WebUI model ID
must match one of that Deployment's `--served-model-name` values. The first
served name, `qwen3.6-27b`, is the canonical UI default. vLLM deliberately
advertises only that one name so Open WebUI's model selector stays clean.

## Performance tuning (env ConfigMap)

Non-default env vars that matter, grouped by why they exist:

### FastAPI / HTTP

| Var                                    | Value | Why |
|----------------------------------------|-------|-----|
| `THREAD_POOL_SIZE`                     | `500` | Default (40) chokes under concurrent chat + RAG + tool calls. |
| `AIOHTTP_CLIENT_TIMEOUT`               | `1800` (30 min) | Matches the HTTPRoute timeout so long completions aren't cut off mid-stream. |
| `AIOHTTP_CLIENT_TIMEOUT_MODEL_LIST`    | `30` | Model list probe timeout. |
| `CHAT_RESPONSE_STREAM_DELTA_CHUNK_SIZE`| `5`  | Batch 5 tokens per SSE push. Cuts CPU/network overhead vs per-token flushing. |
| `ENABLE_COMPRESSION_MIDDLEWARE`        | `True` | Gzip HTTP responses — meaningful for large RAG payloads. |
| `MODELS_CACHE_TTL` / `ENABLE_BASE_MODELS_CACHE` | `300` / `False` | Keep Open WebUI from caching an empty model list if vLLM is down during startup. |
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
| `ENABLE_PERSISTENT_CONFIG`            | `False` | Forces Open WebUI to use GitOps env values instead of stale DB-stored connection settings. |
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
| `open-webui-configmap.env`| **All** env-based config. Source of truth for behavior.          |
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
- Check `curl -s http://vllm-service.vllm.svc.cluster.local:8080/v1/models` from inside the cluster — what model name is advertised?
- Compare against `DEFAULT_MODELS` in `open-webui-configmap.env`. It must match a vLLM `--served-model-name` value exactly.
- If Open WebUI cached an empty model list while vLLM was crashlooping, restart `deploy/open-webui` after vLLM is healthy.

**Tools tab is empty**
- `kubectl logs -n open-webui deploy/mcpo` — MCPO pods crash loudly if the API keys don't match `OPENAPI_API_ENDPOINTS`.
- Test endpoint directly: `kubectl exec -n open-webui deploy/open-webui -- curl -s http://mcpo.open-webui.svc.cluster.local:8000/openapi.json`

**Web search returns nothing**
- Verify SearXNG is alive: `kubectl get pods -n searxng`
- `SEARXNG_QUERY_URL` must include `&format=json` — without JSON format Open WebUI silently drops results.

**Long completions cut off mid-stream**
- `AIOHTTP_CLIENT_TIMEOUT=1800` handles 30-min generations. If you're running longer, bump this *and* the `HTTPRoute` timeout — the shorter of the two wins.

## Gotchas

- **Env ConfigMap is law.** `ENABLE_PERSISTENT_CONFIG=False` forces Open WebUI
  to read these GitOps values on restart; UI edits to connection/model settings
  are session-only.
- **MCPO key must match** between the MCPO Deployment env and
  `OPENAPI_API_ENDPOINTS` — format is
  `name:url:api_key;name:url:api_key;…`.
- **PVC is RWO.** Deployment uses `strategy: Recreate` (see
  `my-apps/CLAUDE.md` — RWO + RollingUpdate = Multi-Attach deadlock).
