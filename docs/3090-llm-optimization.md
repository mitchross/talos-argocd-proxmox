# 3090 LLM Optimization — Topology, Models, and Context Strategy

> **Status:** design + staged config. Authoritative for local-LLM serving
> decisions on the dual-RTX-3090 GPU node. Cross-references the community
> [`noonghunna/club-3090`](https://github.com/noonghunna/club-3090) recipe repo,
> which this cluster's hardware (2× RTX 3090) directly matches.
>
> Last updated: 2026-05-28.

## TL;DR

- **Keep both 3090s in the cluster, split** — GPU0 = llama-cpp model bank
  (native swap), GPU1 = ComfyUI/SwarmUI. **Pool both on-demand** (layer-split)
  only for the occasional 256K research / full-context coding burst. Do **not**
  redistribute a card to the gaming PC.
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
- **MTP (multi-token prediction): recommended download.** An MTP-enabled GGUF of
  Qwen3.6-35B-A3B gives **1.4–2.2× decode** with no accuracy change (club-3090's
  single-card recipes all use the MTP GGUFs). Biggest *free* speedup and it needs
  no hardware — especially valuable given the slow CPU. **Action:** download the
  MTP GGUF to NFS, then point the `qwen3.6*` presets' `model =` at it. Not done
  here because it requires the file to be present (changing the primary model
  path to a missing file would break the default model).
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

## Dual-card on-demand (deferred work)

Not yet implemented — requires hardware testing. To run 256K **resident, no
offload, no spill**:

1. A second llama-cpp Deployment requesting `nvidia.com/gpu: 2` (whole-card
   layer-split), serving the `longctx` + `coder` presets at full 256K.
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

- [ ] **MTP Qwen3.6-35B-A3B** GGUF → repoint the `qwen3.6*` presets (decode speedup)
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

## References

- club-3090 recipe repo: <https://github.com/noonghunna/club-3090> —
  `docs/KV_MATH.md`, `docs/SINGLE_CARD.md`, `docs/CLIFFS.md`.
- llama.cpp asymmetric-KV CPU-offload bug: <https://github.com/ggml-org/llama.cpp/issues/20866>
- llama.cpp TurboQuant / `turbo3` KV: <https://github.com/ggml-org/llama.cpp/discussions/20969>
- WhiteRabbitNeo (security model): <https://taico.ca/posts/run-whiterabbitneo-locally/>
