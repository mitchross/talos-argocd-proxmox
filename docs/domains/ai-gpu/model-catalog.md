# AI Model Catalog — llama-cpp Preset Bank

> What each model in the cluster is, what it's for, and when to use it. Companion
> to [`3090-llm-optimization.md`](3090-llm-optimization.md) (topology, KV
> math, engine choice). Source of truth for the presets themselves:
> [`my-apps/ai/llama-cpp/presets.ini`](../../../my-apps/ai/llama-cpp/presets.ini).
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
| `whiterabbitneo` | WhiteRabbitNeo-2.5-Qwen2.5-Coder-7B Q8_0 (→ **swap to V3-7B**) | 7B dense | 64K | authorized security learning (isolated) |
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
  CPU-driven attention on the Threadripper 2950X CPU = slow, *and* it's a distinct
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

## WhiteRabbitNeo — `whiterabbitneo` (isolated security model)
- **What:** WhiteRabbitNeo, built on **Qwen2.5-Coder-7B**, trained on offensive +
  defensive security data. Domain-tuned, chosen over an abliterated general model
  because abliteration degrades accuracy and a security-trained model is both more
  accurate AND more willing on this domain.
- **⚠️ Version — use V3, not 2.5:** the currently-deployed file is
  `WhiteRabbitNeo-2.5-Qwen-2.5-Coder-7B-Q8_0.gguf`, but the **latest open release is
  [WhiteRabbitNeo-V3-7B](https://huggingface.co/WhiteRabbitNeo/WhiteRabbitNeo-V3-7B)**
  (GGUF: [bartowski](https://huggingface.co/bartowski/WhiteRabbitNeo_WhiteRabbitNeo-V3-7B-GGUF)).
  **TODO: swap v2.5 → V3-7B** (download to NFS, repoint the `model =` path).
  - WhiteRabbitNeo's open line is **Qwen2.5-Coder-class** (v2.5 confirmed
    Qwen2.5-Coder-7B; V3 is the newest open 7B release in the same lineage). There
    is **no Qwen3-based WhiteRabbitNeo** — so "it's Qwen2.5" is the model family,
    not a sign you're running something stale *within* WRN. 7B is the only current
    open size.
  - Larger 13B/33B exist only on **older v1/v1.5** bases — stale, skip them.
  - The recommended self-hosted target is **V3-7B**; v2.5 still works fine in the
    meantime (it's isolated/occasional-use), so this is a low-priority swap.
  - The 30B-MoE "Deep Hat V2" successor is **proprietary** (Kindo), not self-hostable.
- **For:** authorized security **learning on systems you own or are authorized to
  test** — attack-chain explanation, PoC/CTF code, red/blue concepts.
- **Isolation by design:** security-specific aliases, and it is **NOT** in
  Perplexica's model list — its tuning must never back research/RAG. Swap to it
  deliberately in the UI; swap back when done.

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

As of 2026-06 the chat/inference frontends were consolidated onto the **vLLM**
backend (`vllm-service.vllm.svc.cluster.local:8080/v1`, served model
`qwen3.6-27b` — the dense AWQ build). llama-cpp stays for ComfyUI's
vision→image workflow and as the manual multi-preset playground.

| App | Backend | Model | Notes |
|---|---|---|---|
| OpenWebUI | vLLM | `qwen3.6-27b` (`DEFAULT` / `VISION` / `TASK`) | unified — no preset thrash; RAG embeddings run CPU-local in-pod |
| Perplexica / Vane | vLLM | `qwen3.6-27b` | active model id lives in browser `localStorage["chatModelKey"]` |
| Project NOMAD | vLLM | `qwen3.6-27b` (`AI_BENCHMARK_MODEL`) | embeddings via separate `embeddings.project-nomad` (nomic-embed) |
| Karakeep | vLLM | `qwen3.6-27b` (`INFERENCE_TEXT`/`IMAGE`) | tagging/summarization only. Vector search is **off** (`EMBEDDING_ENABLE_AUTO_INDEXING` unset → `false`); the `EMBEDDING_TEXT_MODEL` line is inert. Full-text search via Meilisearch. Enabling semantic search needs one endpoint serving both chat + embeddings (Karakeep shares `OPENAI_BASE_URL`). |
| ComfyUI | llama-cpp (`ln.svc:8080`) | vision GGUF | vision→image workflow stays on llama-cpp multimodal |

The llama-cpp preset aliases (`qwen3.6`, `qwen3.6-nothink`, `qwen3.6-longctx`,
`gemma4*`, `uncensored`) remain available for manual/interactive use against the
llama-cpp endpoint, but app traffic no longer depends on them.

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

---

## Further reading — club-3090 (and what we learned from it)

[`noonghunna/club-3090`](https://github.com/noonghunna/club-3090) is a community
recipe repo for serving LLMs on RTX 3090/4090/5090 (multi-engine: vLLM,
llama.cpp, ik_llama; model-agnostic — ships Qwen3.6-27B/35B and Gemma 4 26B/31B
configs). Our hardware (2× RTX 3090) matches it directly, so its findings drove a
lot of the decisions here and in [`3090-llm-optimization.md`](3090-llm-optimization.md).

**The docs worth reading there:**
- [`docs/CLIFFS.md`](https://github.com/noonghunna/club-3090/blob/master/docs/CLIFFS.md) — the three memory "cliffs" (FA2 softmax_lse padding; DeltaNet GDN OOM >50–60K; recurrent-state prefix-cache blowup). **All three are vLLM-specific; llama.cpp is immune** — a big reason we stay on llama.cpp for RAG/agentic.
- [`docs/KV_MATH.md`](https://github.com/noonghunna/club-3090/blob/master/docs/KV_MATH.md) — KV-cache memory math. Rule of thumb: each halving of bytes/element ~doubles affordable context. q4_0 KV ≈ 0.28× fp16; **TQ3/TurboQuant ≈ 0.21×**.
- [`docs/SINGLE_CARD.md`](https://github.com/noonghunna/club-3090/blob/master/docs/SINGLE_CARD.md) / [`DUAL_CARD.md`](https://github.com/noonghunna/club-3090/blob/master/docs/DUAL_CARD.md) — single-3090 flag recipes (`-ub`, `-ngl`, `-ckv`) and the TP=2 path.
- [`docs/QUANTIZATION.md`](https://github.com/noonghunna/club-3090/blob/master/docs/QUANTIZATION.md), [`COMPARISONS.md`](https://github.com/noonghunna/club-3090/blob/master/docs/COMPARISONS.md), [`HARDWARE.md`](https://github.com/noonghunna/club-3090/blob/master/docs/HARDWARE.md), [`BENCHMARKS.md`](https://github.com/noonghunna/club-3090/blob/master/BENCHMARKS.md).
- Model recipes for our exact models: [`models/qwen3.6-35b-a3b/`](https://github.com/noonghunna/club-3090/tree/master/models/qwen3.6-35b-a3b) (ik-llama + vllm), [`gemma-4-26b-a4b/`](https://github.com/noonghunna/club-3090/tree/master/models/gemma-4-26b-a4b).

**Interesting findings (with sources) that shaped our setup:**
- **Single-card: llama.cpp ≫ vLLM for this MoE.** Same-hardware benchmark
  ([tfriedel/qwen3.6-rtx3090-lab](https://github.com/tfriedel/qwen3.6-rtx3090-lab)):
  Qwen3.6-35B-A3B on one 3090 → llama.cpp/IQ4_XS **115–133 TPS** vs vLLM/AWQ-INT4
  **18.6 TPS** (~7×; AWQ weights starve the card → `--enforce-eager`). vLLM tp1 is
  "an anti-pattern." vLLM only wins at **TP=2** (149 TPS @ 200K; 264 code TPS w/ MTP-3).
- **MTP/speculative decoding gives NO net speedup on Ampere + A3B under llama.cpp**
  ([thc1006 bench](https://github.com/thc1006/qwen3.6-speculative-decoding-rtx3090) /
  [writeup](https://hackmd.io/@thc1006/SJly6IE6Wx)) — the MoE is already
  memory-bound. It only helps under vLLM TP=2. (We skipped the MTP GGUF for this reason.)
- **`ik_llama.cpp` is the fastest single-card path** (~18–20% faster decode, leaner
  VRAM via IQK quants + Hadamard KV) — the relevant upgrade to try before vLLM.
- **TurboQuant (`turbo3` KV, ≈5× smaller)** is the coming KV win
  ([llama.cpp #20969](https://github.com/ggml-org/llama.cpp/discussions/20969)) —
  not in mainline yet (PR #21089). club-3090 calls it the "TQ3/Genesis" path.
- **Asymmetric KV trap** ([llama.cpp #20866](https://github.com/ggml-org/llama.cpp/issues/20866)):
  `q8`-K + `q4`-V forces the KV cache to CPU, 44× slower. Keep KV symmetric.
- **Docker tag scheme moved cuda12 → cuda13** (CUDA 13;
  [#21429](https://github.com/ggml-org/llama.cpp/issues/21429)) — why the renovate
  regex was frozen and we bumped to `server-cuda13-b9354`.

Full topology / KV / engine analysis lives in
[`docs/domains/ai-gpu/3090-llm-optimization.md`](3090-llm-optimization.md).
