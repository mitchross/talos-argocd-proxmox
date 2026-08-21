# qwen38-3090 — candidate backend (parked, scale-swap)

Candidate serving stack from
[syv-ai/qwen38-27b-rtx3090](https://github.com/syv-ai/qwen38-27b-rtx3090):
**vLLM 0.27.1 — the same engine version as production** — plus its `patches/`
applied into site-packages, the KVarN KV cache, requantized model artifacts,
and tuned single-user/batch launch profiles for one RTX 3090. Evaluated
**sequentially on the single card** by scale-swapping with `vllm-server`
(`gpu-scale-swap.md`); committed default here is `replicas: 0`.
**Rollback = revert/delete this directory.**

## Pinned versions

| What | Value |
|---|---|
| Upstream commit | `e00bc1b7301faed3737783379cace5fa37416e8a` (no release tags; repo moves daily — bumps are deliberate, via `build.sh` + the image tag together) |
| Image | `ghcr.io/mitchross/qwen38-27b-3090:e00bc1b7` (built by `build.sh` from the repo's Dockerfile: CUDA 13.0.1-base, vLLM 0.27.1/torch 2.13 cu130, patches applied at build) |
| Base model | `dbirks/Qwen3.8-27B-W4A16-AutoRound` (~19.5 GB) — same checkpoint lineage as production; the CPU-only `prepare` step requantizes lm_head/embed/MTP to int8, builds the 40k draft vocab, and fetches the int4 `-fast` variant + the W4A16 DFlash2 drafter (~1 GB each) |

## Verified facts (read from the pinned commit, not the README hype)

- `prepare` is **CPU-only and idempotent** — it runs as an initContainer here;
  no GPU window needed to stage the model.
- The serve command hardcodes **`--language-model-only`: this candidate is
  text-only.** Vision comparisons vs the control are N/A — state that in every
  result.
- `--served-model-name` is hardcoded **`qwen3.8-27b`** — same id as production.
  The endpoint is the identity: `https://qwen38.vanillax.me/v1` (LAN) /
  `http://qwen38-3090-service.qwen38-3090.svc.cluster.local:8080/v1`.
- It exposes normal vLLM Prometheus `/metrics` on the serve port, so the
  benchmark harness's **control tooling works on it** (`collect.sh` with
  `BENCH_NS/BENCH_APP/BENCH_PORT` overrides).
- Upstream documents the trap for exactly our topology: **under VM GPU
  passthrough, uncaptured (PIECEWISE) verify steps cost 2–3×** (launch-bound).
  The initial profile below stays on captured paths. Also their gotcha 37:
  `CUDAGRAPH_MODE=FULL_AND_PIECEWISE` corrupts one prompt length in 128 —
  never set it.
- Upstream numbers were measured at **250 W**; our card is capped at **200 W**
  (house circuit — do not raise it). Expect proportionally lower numbers and
  record the cap with every run.

## Initial runtime profile (correctness-first, control parity)

`single` mode, upstream defaults: **SPEC=mtp** (Qwen's own MTP head,
probabilistic drafts — speculation is exact), **CTX=fast** (bf16 KV,
`max-model-len` 64k ≈ the control's 65,536), **PREFIX_CACHE=1** (control also
runs prefix caching), GPU_UTIL 0.93, 8 slots, port 18020. `verify.sh` gates
startup. The `-fast` model variant (int4 lm_head/MTP + own-output draft vocab)
is auto-selected once `prepare` has staged it.

Later ladder steps (one git change at a time, measured before the next):
`CTX=long` (fp8 KV, 150k — the Pi working-set test), `SPEC=dflash2`
(+`DFLASH_TOKENS=15`), `CTX=huge` (KVarN, 200k+). The upstream claims for these
are their Windows/bare-metal-Linux numbers, not ours, until measured here.
