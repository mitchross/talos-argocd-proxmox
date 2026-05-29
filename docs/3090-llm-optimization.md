# 3090 LLM Optimization — Topology, Models, and Context Strategy

> **Status:** design + staged config. Authoritative for local-LLM serving
> decisions on the dual-RTX-3090 GPU node. Cross-references the community
> [`noonghunna/club-3090`](https://github.com/noonghunna/club-3090) recipe repo,
> which this cluster's hardware (2× RTX 3090) directly matches.
>
> Last updated: 2026-05-28.

## TL;DR

- **Daily driver = Qwen3.6-35B-A3B (nothink), single card.** Aliased
  `daily`/`default`; everything points at it, swap to WhiteRabbitNeo/coder on
  demand in the UI. Already the best self-hostable research model in May 2026.
- **Single card is the steady state, NOT dual.** GPU0 = daily driver + swaps,
  GPU1 = ComfyUI. **Pool both on-demand** (layer-split) only for the occasional
  256K research / full-context coding burst. Keep both 3090s in the box; do
  **not** redistribute a card to the gaming PC.
- **Why not single-card + CPU offload:** the node is a **Xeon E5 v4 (Broadwell)
  DL360 Gen9, DDR4-2400, no AVX-512, PCIe 3.0, under Proxmox**. MoE expert
  offload is memory-bandwidth-bound and would land ~8–12 TPS on this CPU. The
  second 3090 is what keeps the long-context path on-GPU and fast — on this box
  48GB is close to essential, not a nice-to-have.
- **Local = free *volume*, not infinite *window*.** Self-hosting gives unlimited
  tokens over time (run agents all day for the cost of electricity). Each single
  request is still capped by `min(model max, VRAM-affordable KV)`.
- **All accuracy-sensitive work runs unabliterated models.** Abliteration
  measurably degrades benchmarks; it stays out of Perplexica / RAG / tool-calling.
  Offensive-security capability comes from a *domain-tuned* model
  (WhiteRabbitNeo), not a lobotomized general one.
- **Engine: stay on llama.cpp.** Same-hardware benchmarks show vLLM is ~7× slower
  on a single 3090 for this MoE (weights starve the card → eager mode), and our
  whole library is GGUF. vLLM only wins at **TP=2** (dual-card pooled), which is
  the one optional endpoint where it's worth it. `ik_llama.cpp` is the more
  relevant single-card speedup to try.

## Context: is the limit the model or the VRAM?

Two separate ceilings; the effective window is the lower one.

| Ceiling | Set by | For Qwen3.6-35B-A3B | Cost |
|---------|--------|---------------------|------|
| **Model max** | training / architecture | 256K native (1M via YaRN) | free until tokens are used |
| **VRAM (KV cache)** | how much KV fits after weights | see table below | grows linearly with tokens |

> **Effective usable context = min( model trained max, what VRAM can afford )**

On this hardware, with ~20GB of Q4 weights resident:

| Setup | KV budget | Usable tokens | Model could do |
|-------|-----------|---------------|----------------|
| Single 3090 (24GB) | ~3–4GB | **~50–64K** (current default `-c 65536`) | 256K |
| Dual 3090 (48GB, layer-split) | ~26GB | **full 256K, resident, no spill** | 256K |

So "Perplexica runs out of context" is a **VRAM** limit, not a model limit. The
three ways to buy more usable context, in priority order **on this CPU**:

1. **More VRAM** — pool the second 3090 (cleanest here).
2. **Smaller KV** — quantize KV (q8→q4 ≈ half; TurboQuant `turbo3` ≈ ⅕, see below).
3. **CPU expert offload** — *last resort* on Broadwell; avoid.

This ordering is **inverted** from a modern DDR5 / AVX-512 box, where single-card
+ offload is fine.

## Hardware topology decision

```
GPU0 (24GB)  ── llama-cpp model bank (native --models-preset swap)
GPU1 (24GB)  ── ComfyUI / SwarmUI (bursty image/video gen)
both, on-demand ── pool layer-split for 256K research / full-context coding
                   (scale ComfyUI → 0 for the burst, scale back after)
```

- Image generation is **rarely needed concurrently** with the LLM (interactive /
  at-the-desk), so time-sharing the pool for occasional big-context bursts costs
  almost nothing.
- The 256K ceiling is the **model's native max** either way — dual doesn't raise
  it, it makes it *resident and fast* (no CPU offload, no unified-memory spill).
- **Rejected: redistribute** (single 3090 + AMD 6800 in cluster + 3090 →
  gaming PC). The 6800 is RDNA2/ROCm and much of the stack is CUDA-locked
  (faster-whisper = CTranslate2, many ComfyUI nodes), and a single cluster 3090
  would be stuck on the slow Broadwell offload path. Only revisit if the LLM
  workload moves off this node.

## Daily driver + single-vs-dual (decision)

**Daily driver = Qwen3.6-35B-A3B (nothink), single card.** Everything in the
cluster points at it; swap to WhiteRabbitNeo (or any preset) on demand in the UI.

- Aliased `daily` / `default` on the `qwen3.6-nothink` preset — point any tool at
  model `default` and it gets the daily driver. Re-point the whole cluster later
  by moving those two aliases to another preset (one edit).
- **nothink** is the universal choice (tool-safe JSON, fast); interactive chat
  that wants reasoning requests `qwen3.6` (think).
- **Single card is the steady state**: GPU0 = daily driver + on-demand swaps
  (WhiteRabbitNeo, coder, etc.), GPU1 = ComfyUI. llama.cpp single-card is the
  MoE sweet spot (115–133 TPS) — no dual needed for daily use, and WRN/coder
  also fit one 3090.
- **Dual = on-demand booster only**: pool both cards (scale ComfyUI→0) *just* for
  the occasional 256K Perplexica/full-repo-coding burst. Not full-time dual TP,
  not vLLM, unless a fast resident-256K coding endpoint later proves worth pinning
  both cards (see "vLLM vs llama.cpp").

## llama.cpp image bump (CUDA-13 caution)

Current: `ghcr.io/ggml-org/llama.cpp:server-cuda12-b9070`. Latest published
`server-cuda13` build is **b9354** (verified on ghcr 2026-05-28; the earlier
`b9384` named here never existed upstream), BUT the Docker tag scheme moved to
**`server-cuda13` (CUDA 13)** around
b93xx, and `server-cuda` now requires **CUDA ≥12.9**
([#21429](https://github.com/ggml-org/llama.cpp/issues/21429)). Bumping a
`Recreate` + auto-synced always-on service onto a CUDA it can't run = hard down.

**Before bumping, read the node's driver** (Talos NVIDIA extension
`nonfree-kmod-nvidia-production`, set at the Omni image level — not in this repo):

```
talosctl read /proc/driver/nvidia/version
# or: kubectl exec <llama-cpp pod> -n llama-cpp -- nvidia-smi   # see "CUDA Version"
```

| Driver | Max CUDA | Tag |
|--------|----------|-----|
| 580.x+ | 13.0 | `server-cuda13-b9354` (newest verified) |
| 575–579.x | 12.9 | latest `server-cuda` / `server-cuda12` build available |
| < 575 | ≤12.8 | stay `server-cuda12-bXXXX` (cuda12 line ended ~b93xx) |

**Renovate is why it's stuck.** `.github/renovate.json5` pins llama.cpp to the
CUDA-12 tag line:
```json5
matchPackageNames: ['ghcr.io/ggml-org/llama.cpp'],
versioning: 'regex:^server-cuda12-b(?<major>\\d+)$',
```
Upstream stopped publishing `server-cuda12` tags (~b93xx → moved to
`server-cuda13`), so this regex matches nothing newer — Renovate can no longer
generate bump PRs, which is why it's frozen at b9070. **The fix is two edits made
together**, only after confirming the driver is CUDA-13-capable (580.x+):
1. `deployment.yaml` image → `server-cuda13-b9354`
2. `renovate.json5` regex → `^server-cuda13-b(?<major>\\d+)$`
Doing one without the other = no bumps or a broken pod. If the driver is < 580,
leave both on cuda12. **Always verify the exact tag resolves on ghcr before
bumping** — `b9384` was a documented guess that 404'd; `b9354` is the real
newest cuda13 server build.

## Model bank (per job)

All models are **unabliterated** except the isolated security preset. Served via
`llama-server`'s built-in router (`--models-preset presets.ini`); switching
models is a swap, no external `llama-swap` needed.

| Preset alias | Model | Job | Status |
|--------------|-------|-----|--------|
| `qwen3.6` / `-nothink` | Qwen3.6-35B-A3B (UD-Q4_K_XL) | chat, agentic, tool-calling, vision | **live** |
| `qwen3.6-longctx` | Qwen3.6-35B-A3B @ 256K | Perplexica / heavy research (pool both cards) | **live** |
| `gemma4*` / `gemma4-31b*` | Gemma 4 26B-A4B / 31B | multimodal fallback | **live** |
| `coder` | Qwen3-Coder-30B-A3B | local coding agent (OpenCode / Cline / Aider) | **staged — needs GGUF download** |
| `whiterabbitneo` | WhiteRabbitNeo v2.5 (Qwen-based) | authorized security learning (own devices) | **staged — needs GGUF download** |
| `tool-fast` | Qwen3-4B/8B (FC) | high-volume n8n triggers, instant | **staged — needs GGUF download** |
| `uncensored` / `-nothink` | Qwen3.5-35B-A3B-Uncensored | creative / RP / jailbreak toy | **live — keep OFF accuracy work** |

### Notes per job

- **Perplexica / n8n / agents:** Qwen3.6-35B-A3B is the strongest local
  tool-caller (nested JSON, missing-param handling, "don't call a tool"
  decisions). Already wired — Perplexica defaults to the `longctx` preset.
- **High-volume n8n:** a small **Qwen3-4B/8B-FC** is the surprise win — 4B ties
  for #1 on tool-calling evals (~0.880). Co-resident (see `--models-max` below)
  it answers instantly with no swap latency. Tier: small model for simple
  triggers, 35B for complex chains.
- **Coding agent:** **Qwen3-Coder-30B-A3B** ("Coder-Flash", 30B/3.3B-active MoE,
  256K native) → point OpenCode/Cline/Aider at `llama-cpp:8080/v1`. Free
  unlimited *volume*; per-request window is the usual `min(model, VRAM)`. This is
  the use case that most justifies pooling both cards.
- **Security learning:** **WhiteRabbitNeo v2.5** (built on Qwen, trained on
  ~1.7M offensive+defensive samples). A *domain-tuned* model — more accurate AND
  more willing on security than a blunt abliteration. **Keep it on its own
  preset, never in Perplexica's model list**, so its tuning can't skew research.
  Use only for systems you own / are authorized to test.
- **Abliteration is retired from accuracy work.** Benchmarks show measurable
  degradation (math/reasoning most sensitive). The existing `uncensored` preset
  stays as a creative toy only.

## Best self-hostable model (May 2026) — no swap needed

For a 24GB card doing research / RAG / agentic / tool-calling,
**Qwen3.6-35B-A3B** (Unsloth Dynamic Q4, ~20.9GB, Apache-2.0, vision, 262K
native) is the most capable self-hostable model as of late May 2026. We're
already on it.

- **Qwen 3.7** — API-only (Alibaba Cloud), no open weights. Not an upgrade path.
- **Gemma 4 26B-A4B** — lighter / strong multimodal, but loses to Qwen on
  research + tool-calling. Kept as fallback.
- **Kimi K2.6 / Qwen3-235B etc.** — stronger but far beyond 24/48GB.
- **Quant** — UD-Q4_K_XL is already the best-quality practical Q4; no change.

The "update to the best model" task resolves to: **stay put, and invest in
retrieval (Perplexica embeddings) + resident context (dual-card)** instead.

## Engine decision: llama.cpp today

Committed: **llama.cpp is the engine.** It's ~7× faster than vLLM on a single
3090 for this MoE, our library is all GGUF, it swaps models natively in seconds,
and it's the simplest fit for **Talos** (immutable OS, everything is a k8s
manifest — one container + GGUFs on the NFS PVC, no host-level anything). vLLM
stays a *documented optional* dual-card endpoint only (see below); not pursued
today.

**Talos note:** there's no SSH-ing GGUFs onto a node. Get models onto the NFS
share either from a workstation that can mount it, or via a one-shot k8s
**download Job** (`huggingface-cli download` → NFS PVC, ArgoCD `Sync` hook).
The Job is the Talos-native pattern.

## Serving / KV settings

Current live flags (see `my-apps/ai/llama-cpp/deployment.yaml`):
`-ngl 99`, `-fa on`, `--cache-type-k q8_0 --cache-type-v q8_0`, `-b 4096`,
`-ub 512`, `--parallel 1`, `--models-max 1`, `GGML_CUDA_ENABLE_UNIFIED_MEMORY=1`.

### Rules and rationale

- **KV cache must be SYMMETRIC.** `--cache-type-k q8_0 --cache-type-v q8_0` (or
  both `q4_0`). **Never** mix `q8_0`/`q4_0` (the "K8V4" combo): llama.cpp
  [issue #20866](https://github.com/ggml-org/llama.cpp/issues/20866) forces an
  asymmetric KV cache onto the **CPU** — measured **1340 → 30 tok/s (44× slower)**.
  ⚠️ This overrides the Qwen3-Coder docs, which *recommend* q8 K + q4 V — do not
  follow that advice on this engine.
- **`--models-max 1` (current) = pure swap.** Safe with the all-large bank.
  **Bump to 3 only after** small models (e.g. Qwen3-4B) are downloaded *and* the
  co-resident VRAM budget is verified — three ~20GB models co-resident would OOM
  a single 24GB card. The bump is what enables an always-on small-model bank
  alongside on-demand heavies.
- **MTP / speculative decoding: do NOT assume a speedup on this hardware.**
  The general claim is 1.4–2.2×, but the *only public same-hardware benchmark*
  (Qwen3.6-35B-A3B on a single RTX 3090, llama.cpp post-PR#19493,
  [thc1006](https://github.com/thc1006/qwen3.6-speculative-decoding-rtx3090) /
  [writeup](https://hackmd.io/@thc1006/SJly6IE6Wx)) found **no variant achieves a
  net speedup on Ampere + A3B MoE** under llama.cpp — the MoE is already
  memory-bound and the draft overhead cancels the win. MTP-3 *does* pay off, but
  only under **vLLM TP=2** (149 → 264 code TPS, dual-card). So: skip the MTP GGUF
  for the single-card llama.cpp path; only revisit it if you build the dual-card
  vLLM endpoint (see "vLLM vs llama.cpp" below). This corrects an earlier note in
  this doc that listed MTP as a free single-card win.
- **`GGML_CUDA_ENABLE_UNIFIED_MEMORY=1` stays for now.** It's the safety net that
  lets the single-card `longctx` preset spill at 256K instead of OOMing. Remove
  it **only** once the dual-card pooled path is the longctx backend (so a failed
  fit is loud, not silently slow). Tracked as dual-card work below.
- **`-ub 512`** prioritizes context-fit over prefill speed. Once dual-pooled
  (VRAM headroom), raising to `-ub 1024` speeds prefill ~10% (matters for
  Perplexica's large prompts). club-3090 single-card default is `-ub 1024`.

### TurboQuant — the KV win to adopt later

[TurboQuant](https://github.com/ggml-org/llama.cpp/discussions/20969) (Google
Research, Mar 2026; club-3090's "TQ3/Genesis" path) gives 3-bit KV without
retraining — `turbo3` ≈ 4.9× vs FP16, *"output identical to f16 on the 35B model
at temp 0."* **Not in mainline llama.cpp yet** (forks only; PR #21089 pending).
**Track PR #21089**; when it lands, `--cache-type-k turbo3` drops the 256K KV
from ~14GB to ~6GB — making big context cheap even single-card. Our image is
stock `ghcr.io/ggml-org/llama.cpp` so wait for mainline rather than a fork.

## Getting the most out of Perplexica (Vane)

The model is **not** the bottleneck — Qwen3.6-35B-A3B is already the best
self-hostable research model (see "Best model" below). For RAG, retrieval
quality beats model size. Levers, in impact order:

1. **Real 256K context (dual-card).** Perplexica already selects the
   `qwen3.6-longctx` (256K) preset, but on a single 3090 only ~64K of that is
   *affordable*. The v1.12.2 embedding filter keeps prompts under the ceiling, so
   this isn't breaking — but research depth is capped. Pooling both 3090s makes
   the full 256K resident (see dual-card work below).
2. **Faster / better embeddings (the retrieval lever).** Vane runs
   `@xenova/transformers` **in-process on CPU** for result reranking — slow over
   50+ scraped results and the main latency source. Two improvements:
   - **Resources bumped** to 4 CPU / 4Gi (done) so the rerank isn't starved.
   - **Point Vane at an external embedding endpoint** instead of in-process
     xenova. The cluster already runs a nomic-embed service
     (`embeddings.project-nomad.svc.cluster.local:8080/v1`,
     `nomic-ai/nomic-embed-text-v1.5`). Wiring Vane's `embeddingModels` to it
     offloads rerank to a real service. **Verify Vane's embedding-provider config
     schema before editing `config.json`** (don't guess — a bad schema breaks the
     seed merge). This is the biggest retrieval-quality + speed win.
3. **More sources / search depth.** Tune SearXNG engines + Vane's result count /
   optimization mode (speed vs balanced vs quality) for deeper research.

## vLLM vs llama.cpp — verdict for this cluster

**Keep llama.cpp as the primary engine.** vLLM is *not* better for this setup,
and there's now same-hardware data
([tfriedel/qwen3.6-rtx3090-lab](https://github.com/tfriedel/qwen3.6-rtx3090-lab))
to back it:

- **Single card (our GPU0 = LLM bank): llama.cpp wins ~7×.** Qwen3.6-35B-A3B on
  one 3090 → **llama.cpp/IQ4_XS ≈ 115–133 TPS** vs **vLLM/AWQ-INT4 ≈ 18.6 TPS**.
  vLLM's AWQ weights eat 21.56GB of the 24GB card, leaving ~0.7GB → forces
  `--enforce-eager` (no CUDA graphs) → kernel-launch overhead dominates, 22% GPU
  util. llama.cpp's GGUF (~17GB) leaves 5GB headroom → 96% SM util. The lab calls
  vLLM tp1 *"an anti-pattern."* Our split topology is single-card-per-purpose, so
  this is the deciding fact.
- **GGUF is our entire library** (Unsloth UD quants, the uncensored HauhauCS
  finetune, WhiteRabbitNeo). vLLM wants AWQ/GPTQ/FP8; we'd have to re-acquire or
  re-quantize everything, and niche uncensored/security finetunes frequently have
  **no AWQ build at all**.
- **Cliffs:** vLLM single-card hits the long-context/RAG/multi-turn cliffs
  (club-3090 `docs/CLIFFS.md`) we care about; llama.cpp is immune.
- **Ampere friction:** no NVLink → TP all-reduce traverses host memory; FP8 e4m3
  unsupported on sm_86. Both nick vLLM specifically.
- **Swapping is no longer the argument.** vLLM added
  [Sleep Mode](https://blog.vllm.ai/2025/10/26/sleep-mode.html) (18–200× faster
  model switches), so "vLLM can't swap" is outdated — but the 7× single-card
  throughput gap means swapping doesn't rescue the case.

**The one place vLLM wins: the dual-card pooled endpoint.** At **TP=2** vLLM/AWQ
hits **149 TPS @ 200K (vision+tools)**, and **179 narr / 264 code TPS with MTP-3**
— genuinely faster than llama.cpp dual layer-split. So *if* we build the on-demand
big-context endpoint (below) for the coding agent / heavy research, **vLLM TP=2 is
the better engine for that one endpoint** — at the cost of an AWQ build of that
model and pinning both cards (no ComfyUI during the burst). TP=4 is pointless here
(bandwidth-bound all-reduce, no NVLink; only unlocks ~500K context).

**More relevant single-card upgrade than vLLM: `ik_llama.cpp`** — club-3090's
fastest single-card path (~18–20% faster decode, leaner VRAM, IQK quants +
Hadamard KV), keeps GGUF + swapping. It has a recipe for our exact 35B-A3B model.
Evaluate this before vLLM for the default engine.

## Dual-card on-demand (deferred work)

Not yet implemented — requires hardware testing. To run 256K **resident, no
offload, no spill**:

1. A second Deployment requesting `nvidia.com/gpu: 2` (whole-card), serving the
   `longctx` + `coder` workload at full context. **Engine choice for this
   endpoint:** llama.cpp layer-split (keeps GGUF, simple) *or* **vLLM TP=2** —
   the one place vLLM wins (149–264 TPS @ 200K, vision+tools), at the cost of an
   AWQ build of that model and pinning both cards. See "vLLM vs llama.cpp".
2. A scale toggle: scale ComfyUI/SwarmUI → 0 to free GPU1, scale the 2-GPU
   llama-cpp up for the research/coding burst, reverse after. (Pattern already
   used by `my-apps/ai/llmfit/` dual-GPU jobs.)
3. On that 2-GPU deployment: drop `GGML_CUDA_ENABLE_UNIFIED_MEMORY`, keep KV
   symmetric q8/q8, optionally raise `-ub 1024`.
4. **Proxmox/DL360 checks:** NUMA-pin the VM to one socket with both 3090s on
   that socket's PCIe lanes; confirm both cards are x16 Gen3; NVLink optional
   (helps spec-decode, not layer-split much).

## Model download checklist (NFS: `192.168.10.133:/mnt/ai-pool/llama-cpp`)

Staged presets are inert until their GGUF exists on the share. Verify the exact
current HF repo/filename (Unsloth / bartowski / mradermacher), download to NFS,
then confirm the `model =` path in `presets.ini` matches:

- [ ] ~~MTP Qwen3.6-35B-A3B GGUF~~ — **skip for single-card llama.cpp** (no net
      speedup on Ampere + A3B per same-hw benchmark; only helps under vLLM TP=2)
- [ ] **Qwen3-Coder-30B-A3B-Instruct** GGUF (UD-Q4_K_XL) → `coder` preset
- [ ] **WhiteRabbitNeo v2.5** (Qwen-based) GGUF → `whiterabbitneo` preset
- [ ] **Qwen3-4B/8B (FC)** GGUF → `tool-fast` preset
- [ ] (optional) **Gemma 4 26B-A4B MXFP4** (15.5GB, tiny KV) — single-card long-context multimodal

After downloading + editing `presets.ini`, the hash-suffixed `configMapGenerator`
forces a llama-cpp rollout automatically.

## Already done (no action needed)

- **Project NOMAD** (`my-apps/home/project-nomad/`) is fully deployed and already
  uses llama-cpp as its `LLM_HOST`, with its own nomic embeddings + Qdrant +
  Kiwix. Optionally point its chat at a smaller/faster model for snappier RAG.
- **Perplexica** already defaults to the `longctx` preset (label corrected to
  256K).
- **KV cache is already symmetric q8/q8** — the #20866 trap was never introduced.

## Hand-off: local PR session checklist

To be run by Claude Code on a machine that can reach the NFS share. Goal:
download models, apply the model-dependent edits, open a PR.

1. **Download GGUFs** to `192.168.10.133:/mnt/ai-pool/llama-cpp` (verify exact
   current HF repo + filename per model):
   - [ ] `Qwen3-Coder-30B-A3B-Instruct` (UD-Q4_K_XL) → `coder` preset
   - [ ] `WhiteRabbitNeo v2.5` (Qwen-based, 14B or 32B Q4) → `whiterabbitneo` preset
   - [ ] `Qwen3-4B/8B` (FC) → `tool-fast` preset
   - [ ] (optional) `Gemma 4 26B-A4B MXFP4` — small, tiny-KV multimodal
   - **Skip MTP** — no net speedup on Ampere + A3B under llama.cpp.
2. **Confirm each preset's `model =` path matches the downloaded filename** in
   `my-apps/ai/llama-cpp/presets.ini` (the `[STAGED]` sections).
3. **llama.cpp image bump (currently frozen by Renovate):** read the driver
   (`talosctl read /proc/driver/nvidia/version`). If 580.x+ (CUDA 13), make BOTH
   edits together: tag → `server-cuda13-b9354` in
   `my-apps/ai/llama-cpp/deployment.yaml`, AND the regex in
   `.github/renovate.json5` → `^server-cuda13-b(?<major>\d+)$`. If < 580, leave
   both on cuda12. See the "llama.cpp image bump" section for why.
4. **(Optional, biggest Perplexica win)** verify Vane's embedding-provider schema,
   then wire `embeddingModels` to `embeddings.project-nomad.svc.cluster.local:8080/v1`
   (`nomic-embed-text-v1.5`) in `my-apps/ai/perplexica/config.json`.
5. **(Optional)** bump `--models-max` 1→2-3 once a small model is present AND the
   co-resident VRAM budget is verified (don't OOM the card).
6. Editing `presets.ini` auto-rolls llama-cpp (hash-suffixed configMap). Open the PR.

Already merged on `claude/3090-cluster-optimization-cybYD` (no models needed):
staged presets, symmetric-KV guard, daily-driver `default` alias, Perplexica
resource bump + longctx label fix, `ai/CLAUDE.md` refresh, this doc.

## References

- club-3090 recipe repo: <https://github.com/noonghunna/club-3090> —
  `docs/KV_MATH.md`, `docs/SINGLE_CARD.md`, `docs/CLIFFS.md`.
- llama.cpp asymmetric-KV CPU-offload bug: <https://github.com/ggml-org/llama.cpp/issues/20866>
- llama.cpp TurboQuant / `turbo3` KV: <https://github.com/ggml-org/llama.cpp/discussions/20969>
- WhiteRabbitNeo (security model): <https://taico.ca/posts/run-whiterabbitneo-locally/>
