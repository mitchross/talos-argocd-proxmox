# AI Model Catalog — llama-cpp Preset Bank

> What each model in the cluster is, what it's for, and when to use it. Companion
> to [`docs/3090-llm-optimization.md`](3090-llm-optimization.md) (topology, KV
> math, engine choice). Source of truth for the presets themselves:
> [`my-apps/ai/llama-cpp/presets.ini`](../my-apps/ai/llama-cpp/presets.ini).
>
> Last updated: 2026-05-30.

## How the bank works (read this first)

All local LLMs are served by **one `llama-server`** (GPU0) using its built-in
router: `--models-preset /config/presets.ini`. Each `[section]` is a **preset**;
the text **before** the ` - ` is the OpenAI-API model ID clients send in their
`model` field. Clients hit `http://llama-cpp-service.llama-cpp.svc.cluster.local:8080/v1`.

**Critical operational fact — the router runs one child process per *preset*,
not per GGUF file, and `--models-max 1` keeps only ONE resident.** Switching
presets unloads one child and loads the next — a ~22GB `--no-mmap` read off NFS
(~16s warm, 30–90s cold). Even presets that share the same GGUF and `--ctx-size`
(e.g. `qwen3.6` think vs `qwen3.6-nothink`) are **separate instances** and force
a full reload when you alternate. If a load is still in-flight when a different
preset is requested, the LRU evictor force-kills it → the caller gets
`500 "model … failed to load"`. That reload window *is* the "stall."

**Consequence:** keep day-to-day traffic on ONE shared preset. That preset is the
**daily driver, `qwen3.6-nothink`** (aliased `default` / `daily`). Reserve other
presets for deliberate, occasional, serialized use. This is why Perplexica and
OpenWebUI were repointed off `longctx`/`think` onto `nothink` (PR #1312).

## Quick reference

| Preset (model ID) | GGUF | Params | Ctx | Use it for |
|---|---|---|---|---|
| **`qwen3.6-nothink`** ⭐ | Qwen3.6-35B-A3B UD-Q4_K_XL | 35B MoE / 3B active | 64K | **DAILY DRIVER** — tools, agents, JSON, RAG, chat |
| `qwen3.6` | (same GGUF) | 35B / 3B | 64K | reasoning chat (think mode) |
| `qwen3.6-longctx` | (same GGUF) | 35B / 3B | 256K | deep research — **dual-card only** |
| `coder` | Qwen3-Coder-30B-A3B UD-Q4_K_XL | 30B MoE / 3.3B active | 64K | local coding agent (OpenCode/Cline/Aider) |
| `tool-fast` | Qwen3-4B-Instruct-2507 UD-Q4_K_XL | 4B dense | 32K | high-volume n8n / triage tool calls |
| `whiterabbitneo` | WhiteRabbitNeo-2.5-Qwen2.5-Coder-7B Q8_0 | 7B dense | 64K | authorized security learning (isolated) |
| `gemma4` / `gemma4-nothink` | gemma-4-26B-A4B UD-Q4_K_XL | 26B MoE / 3.8B active | 128K | multimodal fallback / bulk vision captioning |
| `gemma4-31b` / `-nothink` | gemma-4-31B UD-Q4_K_XL | 31B dense | 64K | top-quality second opinion (slow) |
| `uncensored` / `nothink-uncensored` | Qwen3.5-35B-A3B-Uncensored-HauhauCS Q4_K_M | 35B MoE / 3B | 32K | creative / RP toy **only** |

⭐ = the model everything should default to. `think`/`nothink` variants of a model
share one GGUF and switch sampling + `enable_thinking` only — but are still
separate router instances, so don't split daily traffic across them.

---

## Qwen 3.6-35B-A3B — the primary model (3 presets)

Unsloth Dynamic Q4_K_XL (~22GB), MoE 35B total / ~3B active per token. Native
256K context (1M via YaRN). Multimodal via `mmproj-BF16.gguf`. The best
self-hostable research/agentic/tool-calling model for a 24GB card as of May 2026
(Qwen 3.7 is API-only; see optimization doc). One set of weights covers text,
coding, tool calls, and vision.

### `qwen3.6-nothink` ⭐ — DAILY DRIVER (`default` / `daily`)
- **For:** everything day-to-day — n8n, Karakeep tagger, K8sGPT, Perplexica,
  OpenWebUI chat + tasks, NOMAD, agent loops, RAG, JSON/tool calls.
- **Why nothink:** `<think>` tokens break strict JSON tool parsing and inflate
  context. Sampling tuned for clean structured output: `temp 0.7, top_p 0.8,
  top_k 20, presence-penalty 1.5` (the penalty stops agent loops re-issuing the
  same tool). 64K ctx.
- **Point any new tool at model `default`** so it shares this resident instance.
  To re-point the whole cluster to a different daily driver later, move the
  `daily, default` aliases to another preset — one edit, everything follows.

### `qwen3.6` — reasoning chat (think mode)
- **For:** interactive chat where you want visible reasoning. Same GGUF/ctx as
  nothink; differs only in `temp 1.0` + `enable_thinking:true`.
- **Caution:** separate router instance from nothink → using it alongside the
  daily driver causes a reload. Fine for deliberate "I want thinking now" use;
  don't wire automated/utility traffic to it.

### `qwen3.6-longctx` — deep research, DUAL-CARD ONLY
- **For:** the occasional very long research dig or full-repo context, when both
  3090s are pooled (layer-split, 48GB → 256K KV resident).
- **On a single 3090 it's a trap:** 256K KV (~14GB) spills ~7GB to host RAM →
  CPU-driven attention on the Broadwell CPU = slow, *and* it's a distinct
  instance that thrashes against the daily driver. Perplexica's embedding filter
  keeps prompts <64K anyway, so it does **not** default here. Select manually
  only when you've pooled both cards (scale ComfyUI→0). See optimization doc.

---

## Qwen3-Coder-30B-A3B — `coder`
- **What:** "Coder-Flash", MoE 30B total / 3.3B active, 256K native, purpose-built
  for agentic / repo-scale coding. Unsloth UD-Q4_K_XL (~17.7GB).
- **For:** a local coding agent — point OpenCode / Cline / Aider / Continue at the
  llama-cpp `/v1` endpoint and select `coder`. Free, unlimited *volume*; per-request
  window is `min(model, VRAM)` (~64K single-card; full 256K only if both cards
  pooled). Sampling: Qwen coding profile `temp 0.7, top_p 0.8, top_k 20`.
- **Use it for** the "free for small stuff" tier — boilerplate, refactors, quick
  questions. Hard architecture work still goes to paid APIs.

## Qwen3-4B-Instruct-2507 — `tool-fast`
- **What:** small 4B dense, UD-Q4_K_XL (~2.5GB). Punches far above its size on
  function-calling evals.
- **For:** high-volume, low-complexity n8n triggers / triage where swap latency on
  the 35B would dominate. Tiering: `tool-fast` for simple triggers, `default`
  (35B) for complex agent chains.
- **Note:** small enough to potentially co-reside with the daily driver if
  `--models-max` is raised to 2 *after* verifying the VRAM budget (a 35B + 4B fit;
  two 35B presets do not). Currently `--models-max 1`.

## WhiteRabbitNeo 2.5 — `whiterabbitneo` (isolated security model)
- **What:** official WhiteRabbitNeo v2.5, built on **Qwen2.5-Coder-7B**, trained on
  ~1.7M offensive+defensive security samples. Q8_0 (~8.1GB, near-lossless on a 7B).
- **For:** authorized security **learning on systems you own or are authorized to
  test** — explaining attack chains, PoC/CTF code, red/blue concepts. A
  *domain-tuned* model, chosen over an abliterated general model because
  abliteration degrades accuracy and a security-trained model is both more accurate
  AND more willing on this domain.
- **Isolation by design:** its aliases are security-specific and it is **NOT** in
  Perplexica's model list — its tuning must never become the backend for
  research/RAG, where it would skew results. Swap to it deliberately in the UI; swap
  back when done.

## Gemma 4 — multimodal fallback (4 presets)
- **`gemma4` / `gemma4-nothink`** (26B-A4B MoE, ~3.8B active, ~17GB + mmproj, 128K
  ctx): kept as a **multimodal fallback** in case Qwen 3.6's vision regresses on
  something, and for bulk vision captioning (e.g. ComfyUI's caption node). Google
  sampling: `temp 1.0, top_p 0.95, top_k 64`.
- **`gemma4-31b` / `-nothink`** (31B **dense**, ~18.8GB + mmproj, 64K ctx): strongest
  Gemma, but **all 31B are active per token** → markedly slower than every MoE
  preset. Use only when quality matters more than latency, never for agent loops.
- Qwen 3.6 beats Gemma 4 on coding/agent/tool-calling; Gemma wins on some
  multimodal — hence "fallback / second opinion," not default.

## Qwen 3.5 Uncensored (HauhauCS) — `uncensored` / `nothink-uncensored`
- **What:** unfiltered fine-tune of the older Qwen 3.5 base, Q4_K_M, 32K ctx.
  Creative/RP sampling (`temp 0.9, min_p 0.05, top_k 40, presence-penalty 0.6`).
- **For:** creative / RP / jailbreak experimentation **only**.
- **Keep OUT of accuracy work:** abliteration/uncensoring degrades benchmarks
  (esp. reasoning/JSON). It is deliberately **not** the default anywhere and must
  not back Perplexica/RAG/tool-calling. For security *learning*, use
  `whiterabbitneo` (domain-tuned, accurate) instead of this.

---

## Which model should I use?

| I want to… | Use |
|---|---|
| Anything automated / tools / RAG / default chat | `default` (= `qwen3.6-nothink`) |
| Chat with visible reasoning | `qwen3.6` (think) |
| Code with a local agent | `coder` |
| Fire lots of tiny n8n tool calls fast | `tool-fast` |
| Learn security on my own gear | `whiterabbitneo` |
| Caption images in bulk / vision fallback | `gemma4-nothink` |
| Squeeze max single-shot quality (slow) | `gemma4-31b` |
| Deep 256K research (both cards pooled) | `qwen3.6-longctx` |
| Creative/RP play | `uncensored` |

## Who points at what (cluster apps)

| App | Model | Notes |
|---|---|---|
| Perplexica / Vane | `qwen3.6-nothink` (default) | longctx demoted to "dual-card only"; active model lives in browser `localStorage["chatModelKey"]` |
| OpenWebUI | `DEFAULT_MODELS` + `TASK_MODEL` = `qwen3.6-nothink` | ⚠️ `VISION_MODELS` still `qwen3.6` (think) → image input reloads a separate instance; repoint to `qwen3.6-nothink` for zero thrash |
| Project NOMAD | `AI_BENCHMARK_MODEL` = `qwen3.6` (think) | ⚠️ residual think reference; low impact (benchmark feature) |
| n8n / Karakeep / K8sGPT | `nothink` / `default` | tool/JSON workloads |

**Residual thrash cleanup (optional):** the two ⚠️ rows above still point at the
`think` instance and will force a reload when exercised. Repoint both to
`qwen3.6-nothink` for a single resident instance across all traffic.

## Operating rules (don't break these)
- **KV cache stays symmetric** `q8_0/q8_0` — never mix `q8/q4` (llama.cpp #20866 →
  KV falls to CPU, 44× slower).
- **Don't split daily traffic across presets** — every alternation is a ~16–90s
  reload. Consolidate on `default`.
- **`--models-max 1`** is intentional; raising it only helps co-residing a *small*
  model with the daily driver, and only after checking VRAM (two 22GB presets
  won't fit one 24GB card).
- **Adding a model:** drop the GGUF on NFS (`192.168.10.133:/mnt/ai-pool/llama-cpp`),
  add a `[id - alias]` section in `presets.ini` with a UNIQUE alias set
  (llama-server rejects the whole file on any duplicate), confirm the `model =`
  path, commit. The hash-suffixed configMap auto-rolls llama-cpp.
