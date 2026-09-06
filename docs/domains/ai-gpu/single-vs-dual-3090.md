# One 3090 vs two for Qwen3.8-27B

The declared backend is official Qwen3.8-27B FP8 on vLLM with both 3090s.
This page preserves a historical benchmark, not validation of the new profile.
For the larger model, see [Flash Next feasibility](flash-next-dual-3090.md).

The swap procedure lives in [`gpu-scale-swap.md`](gpu-scale-swap.md); model
inventory and app wiring live in [`model-catalog.md`](model-catalog.md).

## The result

A single card was measured against the two-card configuration using the same
two real workloads (a Perplexica research query and an agentic coding session
over a real repository), with identical verbatim prompts.

| | 2× RTX 3090, TP=2 | **1× RTX 3090, TP=1** |
|---|---:|---:|
| KV cache pool | 313,367 tok | **200,826 tok** |
| Peak resident context | 160,468 (51.2%) | **152,867 (76.1%)** |
| Preemptions | 0 | **0** |
| Prefix-cache hit rate | 97.5% | **96.3%** |
| Truncation / abort / error | 0 / 0 / 0 | **0 / 0 / 0** |
| TTFT mean | 3.808 s | 4.564 s |
| Prefill mean | 3.012 s | 4.242 s |
| Decode (TPOT) mean | 0.036 s | 0.038 s |
| Power, mean | ~236 W total | **196 W** |

**The penalty is prefill and TTFT latency, not usable context.** Dropping a card
removes 36% of the KV pool but the workload still fits, because the pool is only
ever ~76% full at peak. Decode barely moves; generation was never the bottleneck.

Thinking depth is a separate per-request control, not a one-vs-two-card tuning
knob. Qwen3.8 defaults a thinking request with no explicit effort to `xhigh`,
which can waste context regardless of GPU count. Keep vLLM non-thinking by
default; Pi should use `medium` for normal coding, `off` for trivial work, and
`xhigh` only for genuinely hard reasoning. See
[`pi-agent-local-dev.md`](pi-agent-local-dev.md).

## Why the pool is large enough

Qwen3.8 is a hybrid-attention model. `full_attention_interval: 4` means only
**16 of its 64 layers** build a real KV cache; the other 48 are Gated DeltaNet
with a fixed-size recurrent state per sequence, not per token. KV therefore
costs roughly **32 KiB/token**, which is why 200K+ tokens fit in 6.5 GiB.

Two consequences worth internalising:

- Raising `--max-model-len` does **not** add capacity. The pool is one shared
  token budget; the flag only raises the per-request ceiling.
- Each `--max-num-seqs` slot reserves a GDN recurrent-state set out of that same
  pool, which must still admit one full-length request.

## Rules

**Read the pool from the engine, never predict it.** The boot log line
`GPU KV cache size: N tokens` is the only trustworthy source. Capacity does not
scale the way arithmetic suggests — the same card reported 198,529 tokens at
`--max-model-len 150000` and 200,826 at `180000`, with identical KV bytes.

**Boot small, then set the ceiling.** To discover capacity on a new
quantization or card layout, boot deliberately low (150000 works), read the
pool, then set the real ceiling. `--max-model-len` acts as an assertion: if the
pool cannot admit one full-length request the engine refuses to start with an
explicit `ValueError` rather than serving a silently degraded cache.

**Keep `--max-num-batched-tokens` at 2048 on a single card.** Larger prefill
chunks inflate the profiled activation peak, which shrinks the cache pool. 8192
measurably costs capacity here.

**`PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` is not optional** above
~0.975 utilisation. The DeltaNet prefill kernels allocate transient workspace
and fragment the allocator without it. Do not also set `max_split_size_mb`;
it works against expandable segments.

**Never drop `--enable-auto-tool-choice` or `--tool-call-parser qwen3_coder`.**
Perplexica sends `tool_choice=auto` and fails silently without them.

**Watch prefix-cache hit rate, not just peak context.** Cache retention is what
keeps TTFT low on 100K+ prompts — the vast majority of prompt tokens are served
from cache rather than re-prefilled. A capacity change that preserves peak
context but collapses the hit rate is a regression, and it will present as
multi-minute stalls rather than a gentle slowdown.

## Scope of the historical result

The measurement used the former **text-only** profile and covers two concurrent
text workloads at `--max-num-seqs 3`. The active production profile now enables
vision and conservatively caps requests at 65,536 tokens; re-measure its cache
pool rather than applying the values below to it. This benchmark did not cover:

- **Vision.** The single-card configuration runs `--language-model-only`, which
  drops the vision tower (~2.7 GB). Image input is unavailable in this mode.
- **Sustained peaks above ~76% pool utilisation.** The agent workload converged
  around 146K tokens of context; behaviour nearer the 180,000 ceiling is
  extrapolated, not measured.
- **Higher concurrency.** Three sequence slots were enough for the apps in this
  cluster; more consumers would need re-measuring.

## Using the second card

Adding PCI passthrough does not change a pod's GPU allocation or engine flags.
The [model catalog](model-catalog.md) owns current serving settings; use the
[scale-swap runbook](gpu-scale-swap.md) for a GitOps model change. Do not apply
this historical vLLM profile to Flash Next.

## Reproducing

The harness lives in `benchmarks/ai-realworld-load/`. Its README holds the
verbatim workload prompts, which must be reused unchanged for any comparison to
be valid. `tools/collect.sh` reads cluster telemetry only and deploys nothing.

Two things to get right when re-running:

- **Restart vLLM first and verify the cache is genuinely cold**
  (`prefix_cache_queries_total` and `hits` both zero). A warm cache invalidates
  exactly the metric under test.
- **Drive long-running HTTP workloads from inside the cluster.** The external
  gateway terminates connections at 300 s, which kills a research query
  mid-flight. `kubectl port-forward` does not work for Perplexica — it binds the
  pod IP, so forwarding to localhost is refused. A detached Job that calls the
  service DNS is immune to both.
