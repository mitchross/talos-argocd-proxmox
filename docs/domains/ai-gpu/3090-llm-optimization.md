# 3090 LLM optimization

**262,144 tokens, shared by two sequence slots.** That is the whole budget.
It is not two separate 262K contexts.

Baseline: official Qwen3.8-27B FP8, stock vLLM, TP=2, FP8 E4M3 KV, native
vision, speculation off. Exact flags and rollback live in the
[vLLM runbook](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/ai/vllm/README.md).

## What the machine reports

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

524K exceeds the current allocation and, with 14.46 GiB of weights per card,
leaves inadequate workspace at the 0.92 memory budget. The measured engine pool
is the authority, not this arithmetic.

Going past the native window needs a separate RoPE and quality evaluation.

## Everyday operation

| Do | Why |
|---|---|
| Use **medium** reasoning for coding | low for light work, xhigh only deliberately |
| Keep one image in submitted history | a second retained screenshot exceeds the one-image limit |
| Keep tool outputs bounded | dumping unrelated files burns context and triggers expensive prefill |
| Run one long session near the ceiling | a second full-length request causes waiting or preemption |
| Leave image generation parked | vLLM owns both cards; use [scale-swap](gpu-scale-swap.md) to change that |

Prefer browser DOM/text output over screenshots. Keep preserved reasoning on for
agents; stateless chats can disable it. Thinking-off needs Qwen's separate
non-thinking sampler, which the WebUI policy and the Pi hook select by mode.

Pi is configured for the 262K window, a 32K output budget, and automatic
compaction reserving 49,152 tokens. See the
[Pi agent guide](pi-agent-local-dev.md).

## Re-check capacity

Read-only, about 5 minutes.

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
