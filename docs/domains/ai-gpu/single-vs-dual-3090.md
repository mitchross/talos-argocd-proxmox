# One 3090 vs two for Qwen3.8-27B

**Production uses two cards.** One card also works — the cost is prefill
latency, not usable context.

| | 2× RTX 3090 (TP=2) | 1× RTX 3090 (TP=1) |
|---|---:|---:|
| KV cache pool | 313,367 tok | 200,826 tok |
| Peak context reached | 160,468 (51%) | 152,867 (76%) |
| Preemptions | 0 | 0 |
| Prefix-cache hits | 97.5% | 96.3% |
| TTFT mean | 3.81 s | 4.56 s |
| Prefill mean | 3.01 s | 4.24 s |
| Decode mean | 0.036 s | 0.038 s |
| Power | ~236 W | 196 W |

Dropping a card removes 36% of the KV pool, but the workload still fits because
the pool only reaches ~76% at peak. Decode barely moves — generation was never
the bottleneck.

## Why the pool is bigger than it looks

Qwen3.8 is hybrid-attention. `full_attention_interval: 4` means only **16 of 64
layers** build a real KV cache; the other 48 are Gated DeltaNet with a
fixed-size recurrent state per sequence, not per token. KV costs ~32 KiB/token,
which is why 200K+ tokens fit in 6.5 GiB.

Two consequences:

- Raising `--max-model-len` adds **no** capacity. The pool is one shared token
  budget; the flag only raises the per-request ceiling.
- Each `--max-num-seqs` slot reserves a recurrent-state set from that same pool,
  which must still admit one full-length request.

## Capacity rules

**Read the pool from the engine, never predict it.** The boot log line
`GPU KV cache size: N tokens` is the only trustworthy source. The same card
reported 198,529 tokens at `--max-model-len 150000` and 200,826 at `180000`,
with identical KV bytes.

**Boot small, then set the ceiling.** On a new quantization or card layout, boot
deliberately low (150000 works), read the pool, then set the real ceiling.
`--max-model-len` acts as an assertion: if the pool cannot admit one full-length
request, the engine refuses to start with an explicit `ValueError` instead of
serving a silently degraded cache.

**Keep `--max-num-batched-tokens` at 2048 on a single card.** Larger prefill
chunks inflate the profiled activation peak, which shrinks the pool. 8192
measurably costs capacity.

**`PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` is mandatory** above ~0.975
utilisation. DeltaNet prefill kernels allocate transient workspace and fragment
the allocator without it. Do not also set `max_split_size_mb` — it works against
expandable segments.

**Never drop `--enable-auto-tool-choice` or `--tool-call-parser qwen3_coder`.**
Perplexica sends `tool_choice=auto` and fails silently without them.

**Watch prefix-cache hit rate, not just peak context.** Retention is what keeps
TTFT low on 100K+ prompts. A change that preserves peak context but collapses
the hit rate is a regression, and it shows up as multi-minute stalls rather than
a gentle slowdown.

## What these numbers do not cover

The measurement used a text-only profile at `--max-num-seqs 3`. Production uses
FP8, TP=2, native vision, two slots and a 262,144-token ceiling — see the
[current capacity audit](3090-llm-optimization.md).

Not covered: vision (single-card ran `--language-model-only`, dropping the
~2.7 GB vision tower), sustained load above ~76% pool utilisation, and
concurrency beyond three slots.

## Changing card count

Adding PCI passthrough does not change a pod's GPU allocation or engine flags.
Use the [scale-swap runbook](gpu-scale-swap.md).

The harness lives in `benchmarks/ai-realworld-load/`.
