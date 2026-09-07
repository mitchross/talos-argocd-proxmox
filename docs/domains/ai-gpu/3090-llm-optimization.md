# Dual RTX 3090: context and agent operating guide

Current production audit, **2026-09-06**. This page explains what the two-card
Qwen3.8-27B setup can hold and how to use that context effectively. It replaces
obsolete single-card Qwen3.6/model-bank advice; earlier experiments remain in
Git history and the [historical one-versus-two-card benchmark](single-vs-dual-3090.md).

The recommended baseline remains official Qwen3.8-27B FP8 on stock vLLM 0.28.0,
TP=2, FP8 E4M3 KV, native vision, **262,144 total tokens**, and speculation off.
Exact settings, deployment verification, and rollback belong to the
[vLLM runbook](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/ai/vllm/README.md).
[The model catalog](model-catalog.md) owns app wiring.

## What the live machine actually reports

Read-only inspection of `vllm-server` on the Talos GPU worker found:

| Observation | Result |
|---|---|
| Allocated GPUs | two RTX 3090s, 24,576 MiB each |
| Interconnect | PHB path, no NVLink; NCCL P2P disabled |
| Power cap | 220 W per card |
| Weight kernel | `MarlinFP8ScaledMMLinearKernel` |
| Loaded model memory | 14.46 GiB per GPU |
| Available KV memory | 5.07 GiB per GPU |
| GPU memory in use at inspection | 21,344 MiB per GPU |
| Engine KV pool | **325,717 tokens** |
| Engine concurrency at 262,144 tokens | **1.24×** |
| API-advertised maximum | 262,144 tokens |

The 3090 stores these FP8 weights compactly and uses an Ampere-compatible
weight-only kernel; it does not acquire native FP8 tensor arithmetic. Two cards
provide 48 GiB aggregate VRAM through tensor parallelism, with separate
per-card allocations. The host's roughly 96 GB RAM is useful for loading and
transport but does not enlarge this GPU-resident KV pool.

The configured two sequence slots share the pool. They are not two separate
262K contexts. Near the ceiling, use one long session and watch other consumers.
A second full-length request can cause waiting or preemption/recomputation.

## Why the ceiling stays at 262K

There are three different limits: the model's supported window, the configured
per-request ceiling, and the runtime's allocated memory. Raising a flag changes
only the second. Current model metadata gives a native 262,144-token window;
longer extrapolation would require a separate RoPE/quality evaluation.
[Official model configuration](https://huggingface.co/Qwen/Qwen3.8-27B-FP8/blob/main/config.json).

For this hybrid architecture, only 16 full-attention layers build token-growing
KV. With four KV heads, head dimension 256 and one byte per KV element, the
rough aggregate cost is:

`16 layers × 2 (K,V) × 4 heads × 256 × 1 byte = 32 KiB/token`.

Thus 262,144 tokens need about **8 GiB aggregate KV** (about 4 GiB/card), before
recurrent state, allocation alignment, graphs, activations, and vision overhead.
524,288 tokens would need about **16 GiB aggregate KV**. That exceeds the current
KV allocation and, with 14.46 GiB weights/card, leaves inadequate workspace at
the existing 0.92 memory budget. Host RAM is not a free substitute here.
The measured engine pool is the operational authority, not this approximation.

Keep native 262K as the configured ceiling, with the operating limits below. This is not a claim that no
other quant/runtime could ever go longer; those are separate experiments.
Do not copy 512K/1M settings from four-card or Blackwell recipes into this box.
The [official vLLM recipe](https://recipes.vllm.ai/Qwen/Qwen3.8-27B) and
[club-3090 dual-card guide](https://github.com/noonghunna/club-3090/blob/master/docs/DUAL_CARD.md)
are useful references, but kernel, vision, speculation and memory assumptions
must match before comparing results.

## Live acceptance evidence

The audit exercised explicit low, medium, and xhigh reasoning; each produced
correct arithmetic with a separate reasoning field. Explicit off returned no
reasoning text. A medium request produced a valid JSON tool call, consumed its
tool result in a subsequent turn, and kept the answer coherent. A medium image
request correctly identified the supplied Proxmox screenshot.

Long-context capacity probes use synthetic records with three facts placed at
10%, 50%, and 90% of the input, then request all three facts. They use explicit
non-thinking sampling to isolate fit/retrieval from reasoning length. Inputs
are tokenized before submission and API usage records the actual prompt size.

| Actual prompt tokens | Elapsed seconds | Retrieved all three facts |
|---:|---:|---|
| 59,856 | 66.33 | Yes |
| 119,856 | 146.03 | Yes |
| 239,856 | 352.53 | Yes |
| 261,872 | 410.73 | Yes |

The largest response used 261,872 input tokens plus 36 output tokens and
finished normally. However, the cumulative preemption counter rose from zero
at the initial inspection to five by the end of the audit, and the boundary
probe reached about 99.3% KV usage. The counter was not sampled at every
ladder boundary, so do not assign all five to a particular stage. This is
**successful retrieval with observed cache pressure**, not a zero-preemption
soak or a reason to routinely fill the ceiling. The pod remained Ready with
zero restarts. Keep output/tool headroom and investigate preemption on real
agent sessions before tuning memory utilization or concurrency.

These are fit and simple retrieval checks, not a coding-quality benchmark or
a sustained multi-user soak. Prefixes overlap between probes, so elapsed time
is not a cold-prefill benchmark. A passing short image test does not establish
vision quality at the context ceiling. Measure realistic repository tasks and
multi-turn sessions before claiming workload throughput or universal reliability.

The live server still had its prior low fallback during this audit. Medium was
sent explicitly in the probes. The PR changes the fallback to medium; verify
that running argument and a default request after merge/reconciliation. Offline
checks verify that the proposed default renders as explicit medium and cannot
silently inherit the upstream xhigh default.

## Recommended everyday operation

- Use **medium** for coding, low for light work, and xhigh only deliberately.
  Keep preserved reasoning on for agents; stateless chats can disable it.
- Keep the server's thinking sampler. Thinking off needs Qwen's separate
  non-thinking sampler; the WebUI policy and Pi extension select it by mode.
- Configure Pi for the actual model and 262K window, a 32K output budget, and
  automatic compaction with 49,152 tokens reserved. The
  [Pi setup guide](pi-agent-local-dev.md) contains tested configuration and rollback.
- Keep one image across the submitted history. Prefer browser DOM/text output;
  a second retained screenshot can exceed the one-image limit.
- Keep large tool outputs bounded. Prefix reuse helps unchanged history, but
  dumping unrelated files consumes context and can trigger expensive prefill.
- Keep image-generation workloads parked while vLLM owns both cards. Use the
  [GitOps scale-swap procedure](gpu-scale-swap.md) for a deliberate ownership change.

## Repeat the capacity inspection

Run from a workstation with read-only Kubernetes access:

```bash
kubectl -n vllm get deploy vllm-server
kubectl -n vllm exec deploy/vllm-server -- nvidia-smi
kubectl -n vllm logs deploy/vllm-server --tail=-1 | \
  rg 'Available KV|GPU KV cache size|Maximum concurrency|model loading took|MarlinFP8'
kubectl -n vllm port-forward svc/vllm-service 18000:8080
```

In another terminal:

```bash
curl -fsS http://127.0.0.1:18000/v1/models
curl -fsS http://127.0.0.1:18000/metrics | \
  rg 'cache_config_info|num_requests_running|num_requests_waiting|num_preemptions|kv_cache_usage'
```

Expect two cards, a Ready deployment, the canonical model ID and a pool that
can admit at least one configured maximum-length request. Stop testing on OOM,
CUDA/Xid errors, broken output, or repeated preemption; inspect logs before
changing memory settings. The read-only checks require no rollback. Proposed
configuration changes require a Git PR and the runbook's rollback procedure.
