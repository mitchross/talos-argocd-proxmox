# Open WebUI

Self-hosted ChatGPT-style frontend for the cluster's local AI stack.

## Active wiring

```text
https://open-webui.vanillax.me
        |
        v
Open WebUI
  |-- vLLM     -> qwen3.8-27b (chat / reasoning / tools / vision)
  |-- SearXNG   -> web search
  |-- MCPO      -> MCP-backed tools
  |-- ComfyUI   -> image generation
  `-- local CPU SentenceTransformer / Whisper -> RAG + STT
```

The canonical LLM connection is:

- endpoint: `http://llama-cpp-service.llama-cpp.svc.cluster.local:8080/v1`
- model: `qwen3.8-27b`
- effective server context ceiling: `262144`, shared with reasoning/output

`open-webui-configmap.env` is the source of truth. Persistent Open WebUI model
configuration is disabled so GitOps values win over stale DB-stored connection
settings.

## Current model profile

| Role | Value |
|---|---|
| Chat/default | `qwen3.8-27b` |
| Vision | `qwen3.8-27b` |
| Task/title model | `qwen3.8-27b` |
| Backend | stock vLLM `0.28.0` |
| Target | official Qwen3.8-27B FP8 |
| Server context ceiling | 262,144 |
| Speculation / MTP | Off |
| KV | FP8 E4M3 |
| Vision | Native encoder |

The production server and this client's default are **medium reasoning**.
`qwen-no-think-filter.py` now honors explicit off/low/medium/xhigh. A client's
generic high maps to medium; unsupported efforts fail instead of falling back
to implicit xhigh. Preservation defaults to true for thinking and false for
off; stateless chats may explicitly disable preservation.

The filter normalizes both top-level and `extra_body` forwarding shapes to
matching chat-template kwargs and top-level effort (null for off). Keeping
the top-level key prevents later WebUI model defaults from restoring stale
effort; vLLM gives that top-level value precedence. Canonical
kwargs take precedence over nested kwargs when both exist. For Qwen only, it
applies all six recommended mode-specific sampling values, including overriding
stale per-chat sampler values. Other models and messages/tools/images/history
are untouched. See [the canonical policy and acceptance matrix](../vllm/README.md#reasoning-acceptance-checks)
for exact samplers and runtime tests.

The stored function ID `qwen_non_thinking_default` is deliberately retained:
the PostSync loader updates that existing global function in place under the
new display name **Qwen3.8 Reasoning Policy**. Renaming the ID would leave the
old global non-thinking filter active beside the new one. Verify the loaded
function after sync, then test a fresh conversation and an existing one.

## Historical llama.cpp performance baseline

After the 2026-09-03 cutover, ordinary Open WebUI responses measured roughly
42-43 generated tok/s on the single RTX 3090. Under generation the card showed
about 22.7 GiB VRAM used and high GPU utilization at the 220 W cap.

## Date/time grounding

`DEFAULT_SYSTEM_PROMPT` injects `{{CURRENT_DATE}}`, `{{CURRENT_WEEKDAY}}`, and
`{{CURRENT_TIMEZONE}}` so Qwen is not forced to guess the current date. Exact
current time, timezone conversion, and calendar arithmetic should use the
`mcpo-time` tool.

Do not add `{{CURRENT_TIME}}` or `{{CURRENT_DATETIME}}` to the persistent system
prompt: Open WebUI resolves them on every request, changing the prompt prefix
and hurting KV/prefix reuse on long conversations. The date-only variable
changes once per day.

## Features

- **Web search**: SearXNG (`WEB_SEARCH_*`, `SEARXNG_QUERY_URL`).
- **RAG**: local CPU embeddings, hybrid BM25/vector retrieval.
- **Tools**: MCPO endpoints from `OPENAPI_API_ENDPOINTS`.
- **Vision**: the same `qwen3.8-27b` model; no separate vision LLM.
- **Image generation**: ComfyUI, separate from the chat model.
- **Voice**: local Whisper STT; configured TTS remains OpenAI-compatible.

## Important env settings

- `ENABLE_PERSISTENT_CONFIG=False`: GitOps model/backend settings stay authoritative.
- The obsolete `CONTEXT_WINDOW=65536` environment variable was removed: the
  audited installed Open WebUI Python backend does not read it. It was not a
  reliable client cap and did not change vLLM's 262144-token limit. Per-chat
  history and output budgets still need to fit that server ceiling.
- `DEFAULT_MODELS`, `VISION_MODELS`, `TASK_MODEL`, `TASK_MODEL_EXTERNAL`: all `qwen3.8-27b`.
- `AIOHTTP_CLIENT_TIMEOUT=1800`: matches long-generation Gateway timeouts.
- `ENABLE_AUTOCOMPLETE_GENERATION=False`: avoids constant background LLM traffic.
- `USE_CUDA_DOCKER=false`: Open WebUI stays CPU-only; vLLM owns both RTX 3090s.

## Debugging

Check the backend directly before blaming the UI:

```bash
kubectl -n vllm get pods
kubectl -n vllm logs deploy/vllm-server --tail=200
kubectl -n vllm exec deploy/vllm-server -- nvidia-smi
curl -s https://llama.vanillax.me/v1/models
```

Then confirm the UI pod received the rendered ConfigMap:

```bash
kubectl -n open-webui get pods
kubectl -n open-webui describe deploy/open-webui
```

## GPU ownership

Open WebUI itself does not request a GPU. vLLM requests both RTX 3090s;
llama.cpp and image generation remain parked. Use the GPU scale-swap runbook
before changing ownership.
