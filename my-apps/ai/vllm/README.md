# vLLM: Qwen3.8-27B INT4/W4A8 on two RTX 3090s

vLLM owns both cards; [Strata](../strata/README.md) is parked. The image comes from
[homelab-images PR 48](https://github.com/mitchross/homelab-images/pull/48): merge it,
wait for publication, then merge this GitOps change. The custom image digest pin
follows publication; the upstream base is already pinned by digest.

The [club-3090 dual-fast recipe](https://github.com/noonghunna/club-3090/blob/def9711c8e6dc8bb3e6d1ecaad795b3bbb4bb665/models/qwen3.8-27b/vllm/compose/dual/autoround-int4/mtp.yml)
is pinned to `def9711c8e6dc8bb3e6d1ecaad795b3bbb4bb665`. W4A8, Mamba block-drop and
FlashInfer decode-pin fixes are baked into the image, never applied at boot.
Budget patches are omitted. The bundled model template supports `reasoning_effort`,
so no template overlay is needed. The existing repetition penalty stays **1.05**,
rather than the recipe's 1.0; thinking defaults and all other sampler values stay unchanged.

The recipe's historical v0.30.0, speculation-off, fp32-SSM reference at 0.90 held
**584,550 KV tokens (2.23 × 262K, two full-length sessions)**. That is a planning
reference, not a measurement of this v0.32.0/bf16-SSM/16-slot deployment. Keep 0.90
unless startup reports fewer than 262,144 KV tokens: raise to 0.92 through Git,
never reduce context to fit. Verify actual pool size, vision and long-context
quality after rollout. Beyond native 262K needs YaRN; planned A/B only.

[Concurrency study #1092](https://github.com/noonghunna/club-3090/discussions/1092)
reported spec-off 1K/512-token throughput on v0.27.1: C1 68, C8 211, C16 254,
C32 308 aggregate tok/s. These are upstream reference numbers, not local results;
the saved FP8 TP2 baseline is about 40 tok/s single-stream.

**Git-declared backend and operating policy.** The
[2026-09-06 capacity and client audit](../../../docs/domains/ai-gpu/3090-llm-optimization.md)
records measurements of the earlier v0.28.0 deployment, with medium sent
explicitly. It does not benchmark the current tunables or the xhigh default below. `deployment.yaml` pins the running version.
Confirm the running arguments and repeat acceptance after merge and Argo reconciliation.

| Setting | Value |
|---|---|
| Model | `Frozenlock/Qwen3.8-27B-int4-AutoRound`, W4A8 int8 activations |
| Revision | `b4c61732c4f2d8af323d75ba5702b5c7f3361539` |
| Runtime | vLLM 0.32.0, patched `ghcr.io/mitchross/vllm-qwen38-dualfast` |
| GPUs | 2 × RTX 3090, tensor parallel 2, multiprocessing executor |
| Interconnect | no custom all-reduce; NCCL P2P disabled; shared host transport |
| Context ceiling | 262,144 tokens, native model limit, no RoPE extrapolation |
| Concurrency | up to 16 sequences sharing one KV pool; the pool, not the slot count, bounds what runs |
| Attention | FlashInfer explicitly selected for Ampere FP8 KV |
| KV / recurrent state | `fp8_e4m3` / bfloat16 |
| GPU utilization budget | 0.90 per GPU |
| Prefill | 8,192-token aggregate budget; at most 4,096 prefill tokens per request per step |
| Vision | native encoder; one image per request, video disabled |
| Reasoning | on, explicit `xhigh` default; `low` and `medium` per request |
| Speculation | **off**; no MTP or external drafter |
| Power | existing 220 W per card |
| Host resources | 8 GiB request, 64 GiB limit; VPA recommendation-only |

The active [AutoRound checkpoint](https://huggingface.co/Frozenlock/Qwen3.8-27B-int4-AutoRound)
is 19.02 GB decimal including tokenizer and vision artifacts. Marlin uses INT4
weights with INT8 activations on Ampere. The official FP8 files and their original
manifest stay intact for rollback; staging never prunes other checkpoints.

The config selects FlashInfer explicitly, because vLLM 0.28.0's Triton backend rejects FP8
KV on SM86. The official checkpoint has no calibrated K/V scales,
so the stock FP8 path uses unit scales. Acceptance therefore includes answer-quality and long-context
checks, not just throughput checks. This runtime does not add the unsupported legacy
`--calculate-kv-scales` flag.
[vLLM FlashInfer support](https://github.com/vllm-project/vllm/blob/v0.28.0/vllm/v1/attention/backends/flashinfer.py),
[Triton architecture guard](https://github.com/vllm-project/vllm/blob/v0.28.0/vllm/v1/attention/backends/triton_attn.py),
[KV scale handling](https://github.com/vllm-project/vllm/blob/v0.28.0/vllm/model_executor/layers/quantization/kv_cache.py).

Speculation stays disabled until the GDN/Mamba long-session
fault fixes are validated (vLLM #50021, #53912, #55533, #62304). The image includes
supporting patches for a planned MTP n=4 A/B, but no `--speculative-config` is passed.
Revisit MTP only with a long-session regression test.
[Upstream fault/fix discussion](https://github.com/vllm-project/vllm/pull/50021)

## Endpoints and client compatibility

- model ID: `qwen3.8-27b`
- direct: `http://vllm-service.vllm.svc.cluster.local:8080/v1`
- LAN: `https://llama.vanillax.me/v1` and `https://vllm.vanillax.me/v1`

Applications call authenticated LiteLLM, not these diagnostic endpoints directly.
The vLLM HTTPRoute owns both LAN hostnames and targets its selector
Service. `llama.vanillax.me` stays for older bookmarks and client configs.
See the [model catalog](../../../docs/domains/ai-gpu/model-catalog.md) for gateway wiring.

## Explicit reasoning and sampling

The server supplies `enable_thinking=true`, `reasoning_effort=xhigh`, and
`preserve_thinking=true` through the checkpoint's native chat template.
The Qwen reasoning parser emits reasoning separately from answer content.
`qwen3_coder` parses tool calls, and automatic tool choice stays enabled.

| Desired behavior | `chat_template_kwargs` |
|---|---|
| No thinking | `{"enable_thinking":false,"preserve_thinking":false}` |
| Brief thinking | `{"enable_thinking":true,"reasoning_effort":"low"}` |
| Less reasoning than the default | `{"enable_thinking":true,"reasoning_effort":"medium"}` |
| Accuracy-first default | `{"enable_thinking":true,"reasoning_effort":"xhigh"}` |

The valid efforts are `low`, `medium`, and `xhigh`. `high` is not a native Qwen
value. WebUI maps generic `high` to `xhigh`, and Pi exposes the valid levels instead.
The server merges its explicit defaults with request kwargs, so an omitted effort
stays `xhigh`. Explicit low, medium and off are still honored. No custom chat
template is needed.

Xhigh is an accuracy-first operating choice, not a measured quality improvement.
Expect more reasoning time and output tokens. It applies to any local
request that omits an effort, including background application tasks and local
`pi-auto` generation. The router's classifier explicitly disables thinking.
DeepSeek high/max, route selection and cloud-failover boundaries are unchanged.
A client that explicitly sends medium still gets medium.

Preservation stays on for coding agents. Keep returned reasoning with the
assistant messages to retain continuity and allow reuse of unchanged prefixes.
For stateless or simple chats, clients may explicitly send `preserve_thinking=false`
to reduce retained history. That option trims older reasoning. It is not a
hard reasoning-token budget or a substitute for `enable_thinking=false`.

| Parameter | Thinking (server default) | Non-thinking (per request) |
|---|---:|---:|
| `temperature` | 1.0 | 0.7 |
| `top_p` | 0.95 | 0.8 |
| `top_k` | 20 | 20 |
| `min_p` | 0.0 | 0.0 |
| `presence_penalty` | 0.0 | 1.5 |
| `repetition_penalty` | 1.05 | 1.0 |

Changing the thinking flag alone does not switch vLLM's sampler. Direct
clients must send all six non-thinking values when opting out. Open WebUI's
Qwen filter applies these mode-specific values to both forwarding forms. Pi's
thinking toggle controls template kwargs, and the repo-owned sampler
extension selects the matching values for direct Qwen requests. See the
[Pi guide](../../../docs/domains/ai-gpu/pi-agent-local-dev.md).
[Official Qwen controls and sampling](https://huggingface.co/Qwen/Qwen3.8-27B-FP8#api-usage)

The checkpoint revision stays pinned. The September 6 source audit found
`017b9c7af6b5689d5dd426a76e0bc077eb5ca20a` (2026-08-14). That historical check
says nothing about future upstream releases. Changing the reasoning default
does not replace weights, and it does not cure thinking loops.
[Official FP8 history](https://huggingface.co/Qwen/Qwen3.8-27B-FP8/commits/main)

## Tuning policy and evidence limits

`--max-num-batched-tokens 8192` is the aggregate scheduling budget;
`--long-prefill-token-threshold 4096` caps the prefill chunk of each request.
That cap is active with 16 sequence slots, so a single long prompt
does not receive 8,192-token chunks. Alignment, available tokens, vision and
other scheduler constraints can reduce chunks further. This is an intentional
8192/4096 profile. It is not four times fewer steps and not a measured speedup.
[Versioned scheduler](https://github.com/vllm-project/vllm/blob/v0.29.0/vllm/v1/core/sched/scheduler.py).

`align` and `prefix-match-unit=16` pin cache behavior. The latter is
matching granularity, not a recurrent-state checkpoint every 16 tokens.
Keep `expandable_segments:True` without a split-size override. Allocator
fragmentation tuning needs measurements, not a copied reference setting.
[PyTorch allocator guidance](https://docs.pytorch.org/docs/stable/notes/cuda.html#optimizing-memory-usage-with-pytorch-cuda-alloc-conf).

Thinking `repetition_penalty=1.05` is a **local mitigation candidate**. It is not the
official Qwen default of 1.0 or an established fix. The author of
[Qwen3.8 issue 216](https://github.com/QwenLM/Qwen3.8/issues/216) corrected earlier
claims. Low and medium are not universally immune, and the reported narrow penalty
band and extraction scores do not establish coding, tool, or vision quality.
The suspected EOS-inside-thinking mechanism is not a confirmed root cause.
Validate all supported modes. The xhigh-default rollout does not change sampling.
The server value is a fallback, not an enforced floor, and explicit client values
win. WebUI and the Pi extension use 1.05 for every thinking effort and 1.0 for
off. When changing that policy, update server, clients, tests and docs together.

## Reasoning acceptance checks

Before live tests, inspect the **running** Deployment args and request payloads.
A short answer alone cannot prove which effort reached the model. The running
`--default-chat-template-kwargs` must contain thinking=true, effort=xhigh and
preservation=true. Keep the stock parser, template and thinking sampler.

```bash
kubectl -n vllm get deploy vllm-server -o json | jq '.spec.template.spec.containers[0].args'
uv run --with pyyaml python -m unittest discover -s scripts/tests -p test_qwen_reasoning.py -v
kubectl -n vllm port-forward svc/vllm-service 18000:8080
```

In another terminal, omit template kwargs to test the fallback.
Repeat with each row's kwargs and record the complete response, including
reasoning, content, tools and usage. This diagnostic bypasses LiteLLM, so also
verify client requests through the authenticated gateway after rollout.

```bash
curl -fsS http://127.0.0.1:18000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3.8-27b","messages":[{"role":"user","content":"What is 37*43? Verify the calculation."}],"max_tokens":32768}'
```

| Case | Request / expected result |
|---|---|
| Default | Omit kwargs; running defaults resolve to enabled/xhigh/preserved; answer 1591 with separate reasoning. |
| Explicit low | `{"enable_thinking":true,"reasoning_effort":"low"}`; payload remains low, coherent answer. |
| Explicit medium | `{"enable_thinking":true,"reasoning_effort":"medium"}`; payload remains medium, coherent answer. |
| Explicit xhigh | `{"enable_thinking":true,"reasoning_effort":"xhigh"}`; same effort as the default, coherent answer. |
| Off | `{"enable_thinking":false,"preserve_thinking":false}` plus the non-thinking sampler; empty/absent reasoning fields and no think tags in content. |
| Tool under xhigh | Supply a `lookup` function with an integer `id` argument and ask to look up id 7; expect a valid `tool_calls` entry with parseable JSON `{"id":7}`. Do not execute external actions. |
| Image under xhigh | Send one known local image as an `image_url` data URI plus a factual question; check visible facts against the actual image. HTTP 200 alone is insufficient. |
| Multi-turn xhigh | Append the full assistant tool-call message, including reasoning, a matching `tool_call_id` result and a follow-up question; expect coherent use of the result, intact roles and separately parsed reasoning/content/tools. |

For off, use the complete request policy, not just the thinking switch:

```json
{
  "chat_template_kwargs": {"enable_thinking": false, "preserve_thinking": false},
  "temperature": 0.7, "top_p": 0.8, "top_k": 20, "min_p": 0.0,
  "presence_penalty": 1.5, "repetition_penalty": 1.0
}
```

Repeat through Open WebUI and Pi. The rollout updates the WebUI function ID
`qwen_non_thinking_default` in place. Verify that its PostSync
function-loader job succeeds and the stored filter contains the xhigh default.
Generic `high` maps to xhigh in WebUI. Saved explicit medium, low, and off settings
stay honored, so test a fresh conversation as well as an existing one.

The companion
[dotfiles PR](https://github.com/mitchross/dotfiles/pull/10) manages Pi's startup preference and local-only alias. After both PRs merge,
pull the updated dotfiles source and follow the scoped apply steps in the
[Pi guide](../../../docs/domains/ai-gpu/pi-agent-local-dev.md#default-reasoning-and-rollout).
Start a fresh session or explicitly select xhigh in a resumed one. This rollout does not change the sampler
extension, and reinstalling it alone does not change
Pi's selected effort. `pi-auto` still delegates effort to the selected backend.

In both clients, inspect the outgoing sampler as well as kwargs. Expect 1.05 for all
thinking modes and 1.0 for off, including through LiteLLM. A successful request
alone does not show which settings reached vLLM.

Offline tests check policy resolution and preservation of tool, image, and history
payloads, not model quality. Actual tool, vision, and multi-turn generation must pass
after merge. The 32K Pi output allowance includes reasoning and final content,
and xhigh does not raise it. Treat `finish_reason=length` as inconclusive, not a
successful quality check. A completed empty final answer without tool calls is
a failure. Empty content with a valid tool call is normal. Stop on
loops, malformed tool output or lost history, and inspect payloads before
changing runtime flags.

## Reproducible staging

`model-manifest-int4.json` pins 17 checkpoint/tokenizer/vision artifacts by
revision, exact byte count and SHA-256 (19,016,926,426 bytes). Kustomize exposes it
as `model-manifest.json` to the unchanged download/sync/wait mechanism.
The original FP8 `model-manifest.json` remains available for rollback.

1. Wave -3 creates the namespace. Wave -2 creates the scripts ConfigMap and
   dedicated NFS writer PV/PVC. The existing archive reader PVC is unchanged.
2. Wave -1 `vllm-download-qwen38-int4` downloads into a revision-named directory
   on `192.168.10.133:/mnt/ai-pool/vllm`. Interrupted downloads keep `.part`
   files. Each completed file is hash and size verified before an atomic rename.
3. Wave 0 `vllm-cache-sync` verifies the archive, copies to local NVMe and
   verifies the destination. Only then does it publish `.verified-manifest`.
   Later syncs skip the full re-hash when `.verified-manifest` matches the
   current manifest and every file size matches, so a routine sync takes seconds.
   A manifest change or a size mismatch re-verifies everything. To force a full
   check, delete `.verified-manifest` and sync.
4. Wave 1 Deployment waits for the matching manifest marker and complete file
   inventory. Serving is offline from the local cache.

Warm syncs trust the verified marker and byte sizes; ZFS checksums protect the archive.
A manifest change invalidates old readiness. Failed copies never
publish readiness, and incomplete artifacts never replace verified files.
The wait container uses a small pinned Python image and does not need CUDA.

Prerequisites: the NFS export permits the download Job to write and has at
least 20 GB additional free; local NVMe has at least that much free as well. The earlier
approximately 123 GiB local free-space check is historical. Re-check storage
and export permissions before restaging. No private model token is required.
Existing FP8, AutoRound, GGUF and compile-cache files stay, and nothing is pruned.

## Verification after the user merges

ArgoCD applies the changed arguments through the existing `Recreate` deployment.
Strata stops and the INT4 model downloads and loads; default/auto LiteLLM routes
overflow to paid DeepSeek meanwhile. `qwen3.8-27b-local` replaces the removed
Flash-Next picker route without adding cloud fallback for private Hermes work.
Hermes restarts to seed its updated picker and local worker model; finish running
agent jobs before merging. Route caps are per deployment/pod, not a shared global
16-request admission budget across aliases; vLLM itself schedules at most 16 sequences.

From the workstation:

```bash
kubectl -n vllm get jobs,pods
kubectl -n vllm logs job/vllm-download-qwen38-int4
kubectl -n vllm logs job/vllm-cache-sync
kubectl -n vllm logs deploy/vllm-server --tail=200
kubectl -n vllm exec deploy/vllm-server -- nvidia-smi
kubectl -n vllm port-forward svc/vllm-service 18000:8080
```

In a second terminal:

```bash
curl -fsS http://127.0.0.1:18000/health
curl -fsS http://127.0.0.1:18000/v1/models
curl -fsS http://127.0.0.1:18000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3.8-27b","messages":[{"role":"user","content":"What is 19 + 23?"}],"max_tokens":64,"temperature":0.7,"top_p":0.8,"top_k":20,"min_p":0.0,"presence_penalty":1.5,"repetition_penalty":1.0,"chat_template_kwargs":{"enable_thinking":false,"preserve_thinking":false}}'
```

Expected: both staging hooks complete, vLLM Ready, two GPUs visible to vLLM,
health OK, the expected model ID and answer 42. Also verify both LAN hostnames,
one image, a tool call, and every reasoning mode.

**Read the allocated KV capacity from startup logs.** 262K is the configured
server ceiling. It does not mean two full 262K requests fit concurrently, and
it does not mean near-ceiling vision is verified. Run the existing
`benchmarks/ai-realworld-load/` harness after smoke checks; record TTFT,
prefill/decode, cache preemptions, GPU peaks, and a sustained multi-turn soak.
Test a context ladder before claiming 262K usability. Prefix caching makes
warm prompts cheaper, so genuine prefill tests need unique prefixes.
Compare the prior 2,048-token budget against the 8,192 aggregate / 4,096
per-request profile using the same prompts, output budgets and sampler. Test
one fresh long prompt, two fresh prompts, and a long prefill arriving during
decode. Record time to first token, inter-token latency, preemptions, available
KV capacity and peak memory. Do not reuse the September 6 pool measurements
as proof of capacity after changing prefill workspace. Prefix-hit counters
alone do not show correctness or a latency improvement.

Stop on a staging or hash failure, an insufficient KV pool, OOM or Xid errors, broken tool or
vision output, or repeated preemptions. Do not enable MTP to rescue a failing
baseline. Preparation checks cover manifests, file integrity behavior and
routing configuration. They do not show new runtime performance.

## Rollback

For an immediate per-request opt-down, select medium, low or off.
To restore the default permanently, revert the paired GitOps and dotfiles PRs,
apply the restored Pi settings and zshrc, and start a fresh session. ArgoCD
reconciles the server and WebUI policy. It cannot update workstation settings.
Do not change model weights, sampler or KV precision to roll back effort.

Revert this GitOps PR to restore Strata, its routes and the parked FP8 vLLM config.
No checkpoint files are deleted. A later FP8-only comparison can switch the
ConfigMap manifest mapping back to `model-manifest.json` and restore FP8 args.
CPU image smoke is not GPU, vision, long-context or concurrent-load acceptance.
