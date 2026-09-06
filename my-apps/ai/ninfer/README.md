# NInfer-3090 — experimental candidate backend (parked, scale-swap)

Evaluation of [Don-Chad/ninfer-3090](https://github.com/Don-Chad/ninfer-3090)
against the production vLLM control on **the single RTX 3090** (one card is a
permanent decision). Both engines are measured **sequentially on the identical
card** by scale-swapping per
[`gpu-scale-swap.md`](../../../docs/domains/ai-gpu/gpu-scale-swap.md): for a
test window set this Deployment to `replicas: 1` and `vllm-server` to `0` in
one commit; reverse it to end the window. Committed default here is `0`.
**Rollback = revert/delete this directory.** Nothing else references it.

## Pinned versions

| What | Value |
|---|---|
| Fork tag / commit | `v0.6.0-rtx3090` / `2ae51915225d393e299a9d01b099e2c7103cd322` |
| Image | `ghcr.io/mitchross/ninfer-3090:v0.6.0-rtx3090` (built by `build.sh` from the repo's own Dockerfile, CUDA 13.1.2 / Ubuntu 24.04; the LAN registry rejects the multi-GB CUDA layers on RustFS) |
| Model artifact | `neroued/Qwen3.8-27B-NInfer` → `qwen3_8_27b.ninfer`, 18,210,531,328 bytes |
| Artifact SHA-256 | `eec39564993d6e9c7d5e383382a760f093465c9d163ec9a1bd6b80199514bf3e` (verified by the download Job every sync) |

## Verified facts vs README claims (checked at tag v0.6.0-rtx3090)

Provenance labels: **[W]** measured on Windows RTX 3090 by the fork's release gate ·
**[cap]** implementation capability documented, not benchmarked · **[unv]** unverified.

- Fork targets `sm_86`; CMake **fails hard** on any other arch, so the Docker build
  cannot produce the upstream sm_120a binary. Upstream (`Neroued/ninfer`) targets
  RTX 5090/`sm_120a` and its `docs/performance.md` numbers are 5090 numbers.
- Release binaries are **Windows-only**; Linux is source-build via the checked-in
  Dockerfile. **No upstream Linux/RTX 3090 validation exists — this deployment is
  the first Linux validation. [unv]**
- Qwen3.8-27B text: C1–C8 with INT8 paged KV, CUDA graphs, MTP3+ReplaySSM. **[W]**
  (C1: 70.19 tok/s e2e, 149 ms TTFT, 19,641 MiB peak — 29–34-token prompts,
  1,024-token outputs; a decode benchmark, not a long-prefill test.)
- Qwen3.8 vision: **one** tested profile — C1, 32K context, INT8 KV, MTP3,
  ReplaySSM; 2,074-token image prompt read correctly, 98.1 tok/s decode, 2.16 GiB
  free at startup. **[W]** The artifact embeds the vision tower and chat template
  (single self-contained file); it *declares* multi-image and video. **[cap]**
- 65,536-token KV pool fits at C8/MTP3: 23,745 MiB peak. **[W]** Larger pools
  (128K–160K INT8) are **[unv]** — no 3090 measurement exists in the fork docs.
  The earlier "long-context KV modes" (int4/k8v4/rk8v4 rotated KV, v0.3.1) are a
  **legacy non-paged path not ported** to paged append/prefix reuse/MTP — not used here.
- OpenAI Chat Completions: streaming, `stream_options.include_usage` (final
  empty-choices usage chunk, OpenAI semantics — no continuous-usage flood),
  function tools + `tool_choice` + tool history, `reasoning_effort`
  (`none|low|medium|xhigh`), `reasoning_content`, image_url/base64 + video parts.
  Also OpenAI Responses Core and Anthropic Messages. `strict:true`,
  `tool_choice:required`, named tool choice are rejected; no constrained decoding. **[cap]**
- `GET /health` exists. **No Prometheus metrics** — measurement source is the
  schema-v8 `--request-log-jsonl` (per-request ttft/prefill/decode/total seconds,
  cache tokens, prefix-reuse path, full speculative counters).
- Scheduling: FIFO admission reserves the full prompt+output KV entitlement.
  **There is no preemption concept** — overload returns 429/503 instead.
- Sampling defaults are per-mode presets identical to our vLLM override for
  non-thinking Qwen3.8 (0.7/0.80/20/0/1.5). `--no-thinking` here matches the
  historical control's `enable_thinking=false`; production vLLM now defaults to medium.

## Initial runtime profile (correctness-first)

Exactly the fork's tested vision profile: C1, 32K context/KV, INT8 KV, vision on,
MTP3+ReplaySSM, CUDA graphs on (default), prefix reuse on (default), no RotorQuant.
Public model id: **`qwen3.8-ninfer`** at `https://ninfer.vanillax.me/v1` (LAN) /
`http://ninfer-service.ninfer.svc.cluster.local:8080/v1` (cluster).

## Context ladder (deliberate, not automatic)

Change `--max-context`/`--kv-capacity` together through git, one step at a time,
watching `nvidia-smi` VRAM and the server's startup KV ledger:

`32768 → 65536 → 131072 → 153600 → 163840`

`--kv-capacity auto` exists (maximizes from free VRAM with 1 GiB headroom) — use it
once to learn the actual INT8 ceiling with vision+MTP3 loaded, then pin the number.
The pass criterion is the harness's real Perplexica+Pi workload sustained at the
~150K Pi working set — not startup allocation. See
`benchmarks/ai-realworld-load/README.md` § Engine A/B.
