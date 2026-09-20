# Flash Next on two 3090s

**Not deployed. Not benchmarked. A feasibility study only.**

The serving profile is official Qwen3.8-27B FP8 on dual-card vLLM. See the
[model catalog](model-catalog.md) for what actually runs.

## Answer

**Q4-class Flash Next fits the memory budget, with expert offload.** It cannot
run entirely in 48 GiB of VRAM.

The shape that fits: attention and non-expert compute on the GPUs, CPU-resident
experts distributed across both cards' layer ranges, n-gram embedding table in
host memory with NVMe backing.

This is a memory calculation, not a throughput promise.

## What would have to change first

| Blocker | Detail |
|---|---|
| Node scheduling | other pods already reserve ~35 GiB of the 96 GiB host |
| Container limit | the inference container's 48 GiB memory limit is too small |
| Serving backend | the study assumed llama.cpp, which is **retired** — vLLM is the only GPU backend |

The second card alone solves none of these.

## The memory budget

Q4 routed experts total ~71.73 GiB plus 5.13 GiB of other tensors. Placing ~28
of 48 expert layers on the CPU gives this **illustrative** split:

| Allocation | Estimated GiB |
|---|---:|
| CPU expert weights | 41.94 |
| Host n-gram table | 26.82 |
| **Host model subtotal** | **68.77** |
| Allowance for OS, pods, loader, working memory | 14 |
| **Host total** | **82.77 of 96** |
| **GPU weights, both cards** | **34.91 of 48** |
| Optional BF16 vision projector | 0.85 |
| q8_0 K/V at 131,072 tokens | ~1.59 |

At 26 CPU expert layers the split becomes ~39.01 GiB CPU experts and ~37.84 GiB
GPU weights.

The 14 GiB host allowance is a planning reservation, not a measurement. GPU
figures still need indexer state, DeltaNet state, CUDA graphs, scratch space and
fragmentation headroom. The K/V figure covers 12 attention layers at two KV
heads and dimension 256 — it is **not** total context memory.

**Load logs must show sufficient space on each card separately.** Aggregate free
VRAM hides an OOM on GPU 1.

## Hardware constraints that apply

| Constraint | Value |
|---|---|
| Interconnect | PHB, no NVLink; do not assume P2P performance |
| Power cap | 220 W per card |
| Aggregate VRAM | 48 GiB, as two separate 24 GiB allocations |

## If a trial ever happens

Start text-only, one slot, 65K context, symmetric q8_0 KV, no speculative
decoding, moderate prefill batches. Start with more headroom than the table
suggests and measure before moving experts back onto the GPUs.

Any trial goes through the owning GitOps manifests and the
[scale-swap runbook](gpu-scale-swap.md), since vLLM must be parked to free the
cards.

[Official model configuration](https://huggingface.co/Qwen/Qwen3.8-Flash-Next/blob/main/config.json)
