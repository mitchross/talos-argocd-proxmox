# Context and speed on RTX 3090s

**262,144 tokens is the per-request ceiling.** Up to eight sequence slots share
the engine's allocated KV pool; they do not each receive an independent 262K pool.

In plain words: the *KV cache* is GPU memory that holds the tokens of requests
in progress. All running requests share it, so one huge request leaves less
room for the others.

New to the stack? Read [Local AI starter kit](index.md) first.

Baseline: official Qwen3.8-27B FP8, stock vLLM, TP=2, FP8 E4M3 KV, native
vision, speculation off. Exact flags and rollback live in the
[vLLM runbook](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/ai/vllm/README.md).

## Historical capacity observations

The September 6 audit measured an earlier vLLM release with medium
reasoning explicitly requested. These values are not a measurement of the
current prefill settings or the xhigh default. Re-check the running engine after
rollout; do not relabel the historical pool as current capacity.

| Observation | Value |
|---|---|
| GPUs | two RTX 3090s, 24,576 MiB each |
| Interconnect | PHB, no NVLink; NCCL P2P disabled |
| Power cap | 220 W per card |
| Weight kernel | `MarlinFP8ScaledMMLinearKernel` |
| Model memory | 14.46 GiB per GPU |
| Available KV | 5.07 GiB per GPU |
| Engine KV pool | **325,717 tokens** |
| Concurrency at 262,144 tokens | **1.24×** |

Two cards give 48 GiB aggregate through tensor parallelism, as separate per-card
allocations. Host RAM helps loading and transport; it does **not** enlarge the
GPU-resident KV pool.

The 3090 stores FP8 weights compactly using an Ampere-compatible weight-only
kernel. It does not gain native FP8 tensor arithmetic.

## Why 262K is the ceiling

Three different limits exist: the model's supported window, the configured
per-request ceiling, and the runtime's allocated memory. **Raising a flag moves
only the second one.**

Only 16 full-attention layers build token-growing KV. With four KV heads, head
dimension 256, one byte per element:

```
16 layers × 2 (K,V) × 4 heads × 256 × 1 byte = 32 KiB/token
```

| Window | Aggregate KV needed |
|---|---|
| 262,144 | ~8 GiB (~4 GiB/card) |
| 524,288 | ~16 GiB |

Raising `--max-model-len` therefore adds **no** capacity: the pool is one shared
token budget, and the flag only raises the per-request ceiling. Each
`--max-num-seqs` slot also reserves a fixed recurrent-state set from that pool.

524K exceeds the historical allocation and, with 14.46 GiB of weights per card,
leaves inadequate workspace at the 0.92 memory budget. The measured engine pool
is the authority, not this arithmetic.

Going past the native window needs a separate RoPE and quality evaluation.

## One card or two

**Production uses two cards.** One card also works; the cost is prefill
latency, not usable context. *Prefill* is the model reading the prompt;
*decode* is it writing the answer.

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
the pool reached only ~76% at peak. Decode barely moves.

This used a text-only profile at `--max-num-seqs 3`. It does not cover vision
(the single-card run dropped the ~2.7 GB vision tower), sustained load above
~76% of the pool, or more than three slots. The harness lives in
`benchmarks/ai-realworld-load/`. To change card count, use the
[scale-swap runbook](gpu-scale-swap.md); passthrough alone changes nothing.

## Capacity rules

| Rule | Why |
|---|---|
| Read the pool from the boot log line `GPU KV cache size: N tokens` | It is the only trustworthy number; predictions drift |
| On a new quantization or card layout, boot at `--max-model-len 150000` first | Read the pool, then set the real ceiling. Too high a ceiling fails start with a `ValueError` |
| Keep `--max-num-batched-tokens` at 2048 on a single card | Larger prefill chunks shrink the pool; 8192 measurably costs capacity |
| Set `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` above ~0.975 utilisation | DeltaNet prefill fragments the allocator without it. Do not add `max_split_size_mb` |
| Never drop `--enable-auto-tool-choice` or `--tool-call-parser qwen3_coder` | Perplexica sends `tool_choice=auto` and fails silently without them |
| Watch prefix-cache hit rate, not only peak context | A collapsed hit rate shows up as multi-minute stalls on 100K+ prompts |

## Everyday operation

| Do | Why |
|---|---|
| Use **xhigh** reasoning by default | accuracy-first policy; choose medium/low explicitly for less reasoning |
| Keep one image in submitted history | a second retained screenshot exceeds the one-image limit |
| Keep tool outputs bounded | dumping unrelated files burns context and triggers expensive prefill |
| Run one long session near the ceiling | a second full-length request causes waiting or preemption |
| Leave image generation parked | vLLM owns both cards; use [scale-swap](gpu-scale-swap.md) to change that |

Prefer browser DOM/text output over screenshots. Keep preserved reasoning on for
agents; stateless chats can disable it. Thinking-off needs Qwen's separate
non-thinking sampler, which the WebUI policy and the Pi hook select by mode.

Pi is configured for the 262K window, a 32K output budget, and automatic
compaction reserving 49,152 tokens. Xhigh can use more of that output allowance;
it does not expand context or guarantee better answers. See the
[Pi and Hermes guide](pi-agent-local-dev.md).

## Re-check capacity

These commands inspect the cluster and establish a local diagnostic tunnel;
they do not change the deployment.

```bash
kubectl -n vllm get deploy vllm-server
kubectl -n vllm exec deploy/vllm-server -- nvidia-smi
kubectl -n vllm logs deploy/vllm-server --tail=-1 | \
  rg 'Available KV|GPU KV cache size|Maximum concurrency|model loading took|MarlinFP8'
kubectl -n vllm port-forward svc/vllm-service 18000:8080
```

Then:

```bash
curl -fsS http://127.0.0.1:18000/v1/models
curl -fsS http://127.0.0.1:18000/metrics | \
  rg 'cache_config_info|num_requests_running|num_requests_waiting|num_preemptions|kv_cache_usage'
```

Expect two cards, a Ready deployment, the canonical model id, and a pool that
admits at least one maximum-length request.

**Stop** on OOM, CUDA/Xid errors, broken output or repeated preemption. Read the
logs before changing memory settings. These checks need no rollback; a config
change needs a PR.
