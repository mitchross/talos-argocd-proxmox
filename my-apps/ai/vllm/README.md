# vLLM — official Qwen3.8-27B FP8 on two RTX 3090s

**Git-declared backend and operating policy.** The
[2026-09-06 capacity and client audit](../../../docs/domains/ai-gpu/3090-llm-optimization.md)
records measurements of the earlier v0.28.0 deployment, with medium sent
explicitly. It is not a benchmark of the v0.29.0 tunables or xhigh default below.
Confirm the running arguments and repeat acceptance after merge and Argo reconciliation.

| Setting | Value |
|---|---|
| Model | Official `Qwen/Qwen3.8-27B-FP8`, no Unsloth/GGUF conversion |
| Revision | `017b9c7af6b5689d5dd426a76e0bc077eb5ca20a` |
| Runtime | stock vLLM `v0.29.0`, existing immutable image digest |
| GPUs | 2 × RTX 3090, tensor parallel 2, multiprocessing executor |
| Interconnect | no custom all-reduce; NCCL P2P disabled; shared host transport |
| Context ceiling | 262,144 tokens, native model limit, no RoPE extrapolation |
| Concurrency | at most two sequences sharing one KV pool |
| Attention | FlashInfer explicitly selected for Ampere FP8 KV |
| KV / recurrent state | `fp8_e4m3` / float16 |
| GPU utilization budget | 0.92 per GPU |
| Prefill | 8,192-token aggregate budget; at most 4,096 prefill tokens per request per step |
| Vision | native encoder; one image per request, video disabled |
| Reasoning | on, explicit `xhigh` default; `low` and `medium` per request |
| Speculation | **off**; no MTP or external drafter |
| Power | existing 220 W per card |
| Host resources | 8 GiB request, 64 GiB limit; VPA recommendation-only |

FP8 weights use an Ampere-compatible weight-only path; a 3090 does not gain
native FP8 arithmetic. The official checkpoint is roughly 30.89 GB (28.77
GiB), shared across both cards. The retained AutoRound INT4 checkpoint is for
a later controlled speed comparison, not the active choice.
[Official checkpoint](https://huggingface.co/Qwen/Qwen3.8-27B-FP8)

FlashInfer is explicitly selected: vLLM 0.28.0's Triton backend rejects FP8
KV on SM86. The official checkpoint does not contain calibrated K/V scales;
the stock FP8 path uses unit scales. This makes answer-quality and long-context
checks part of acceptance, not just throughput checks. No unsupported legacy
`--calculate-kv-scales` flag is added to this runtime.
[vLLM FlashInfer support](https://github.com/vllm-project/vllm/blob/v0.28.0/vllm/v1/attention/backends/flashinfer.py),
[Triton architecture guard](https://github.com/vllm-project/vllm/blob/v0.28.0/vllm/v1/attention/backends/triton_attn.py),
[KV scale handling](https://github.com/vllm-project/vllm/blob/v0.28.0/vllm/model_executor/layers/quantization/kv_cache.py).

Speculation remains disabled pending validation of the GDN/Mamba long-session
fault fixes. No community kernel patches, W4A8 overlays, or experimental
speculative backports are installed. Revisit MTP only against a fixed runtime
and a long-session regression test.
[Upstream fault/fix discussion](https://github.com/vllm-project/vllm/pull/50021)

## Endpoints and client compatibility

- model ID: `qwen3.8-27b`
- direct: `http://vllm-service.vllm.svc.cluster.local:8080/v1`
- LAN: `https://llama.vanillax.me/v1` and `https://vllm.vanillax.me/v1`

Applications call authenticated LiteLLM, not these diagnostic endpoints directly.
Both LAN hostnames are owned by the vLLM HTTPRoute and target its selector
Service; `llama.vanillax.me` is kept for older bookmarks and client configs.
See the [model catalog](../../../docs/domains/ai-gpu/model-catalog.md) for gateway wiring.

## Explicit reasoning and sampling

The server supplies `enable_thinking=true`, `reasoning_effort=xhigh`, and
`preserve_thinking=true` through the checkpoint's native chat template.
The Qwen reasoning parser emits reasoning separately from answer content;
`qwen3_coder` parses tool calls and automatic tool choice remains enabled.

| Desired behavior | `chat_template_kwargs` |
|---|---|
| No thinking | `{"enable_thinking":false,"preserve_thinking":false}` |
| Brief thinking | `{"enable_thinking":true,"reasoning_effort":"low"}` |
| Less reasoning than the default | `{"enable_thinking":true,"reasoning_effort":"medium"}` |
| Accuracy-first default | `{"enable_thinking":true,"reasoning_effort":"xhigh"}` |

The valid efforts are `low`, `medium`, and `xhigh`; `high` is not a native Qwen
value. WebUI maps generic `high` to `xhigh`; Pi exposes the valid levels instead.
The server merges its explicit defaults with request kwargs, so omitted effort
stays `xhigh`. Explicit low, medium and off are still honored. No custom chat
template is needed.

Xhigh is an accuracy-first operating choice, not a measured quality improvement.
Expect more reasoning time and output-token use. It applies to any local
request that omits an effort, including background application tasks and local
`pi-auto` generation. The router's classifier explicitly disables thinking;
DeepSeek high/max, route selection and cloud-failover boundaries are unchanged.
A client that explicitly sends medium continues to get medium.

Preservation stays on for coding agents: keep returned reasoning with the
assistant messages to retain continuity and allow reuse of unchanged prefixes.
For stateless/simple chats, clients may explicitly send `preserve_thinking=false`
to reduce retained history. That option trims older reasoning; it is not a
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
Qwen filter applies these mode-specific values to both forwarding forms; Pi's
thinking toggle controls template kwargs, with the repo-owned sampler
extension selecting the matching values for direct Qwen requests. See the
[Pi guide](../../../docs/domains/ai-gpu/pi-agent-local-dev.md).
[Official Qwen controls and sampling](https://huggingface.co/Qwen/Qwen3.8-27B-FP8#api-usage)

The checkpoint revision remains pinned. The September 6 source audit found
`017b9c7af6b5689d5dd426a76e0bc077eb5ca20a` (2026-08-14); that historical check is
not a claim about future upstream releases. Changing the reasoning default
does not replace weights or claim a universal cure for thinking loops.
[Official FP8 history](https://huggingface.co/Qwen/Qwen3.8-27B-FP8/commits/main)

## Tuning policy and evidence limits

`--max-num-batched-tokens 8192` is the aggregate scheduling budget;
`--long-prefill-token-threshold 4096` caps the prefill chunk of each request.
That cap is active even at two sequence slots. A single long prompt therefore
does not receive 8,192-token chunks. Alignment, available tokens, vision and
other scheduler constraints can reduce chunks further. This is an intentional
8192/4096 profile, not a claim of four times fewer steps or a measured speedup.
[Versioned scheduler](https://github.com/vllm-project/vllm/blob/v0.29.0/vllm/v1/core/sched/scheduler.py).

`align` and `prefix-match-unit=16` explicitly pin cache behavior; the latter is
matching granularity, not a recurrent-state checkpoint every 16 tokens.
Retain `expandable_segments:True` without a split-size override. Allocator
fragmentation tuning needs measurements, not just a copied reference setting.
[PyTorch allocator guidance](https://docs.pytorch.org/docs/stable/notes/cuda.html#optimizing-memory-usage-with-pytorch-cuda-alloc-conf).

Thinking `repetition_penalty=1.05` is a **local mitigation candidate**, not the
official Qwen default of 1.0 or an established fix. The author of
[Qwen3.8 issue 216](https://github.com/QwenLM/Qwen3.8/issues/216) corrected earlier
claims: low/medium are not universally immune, and the reported narrow penalty
band and extraction scores do not establish coding/tool/vision quality.
The suspected EOS-inside-thinking mechanism is not a confirmed root cause.
Validate all supported modes; the xhigh-default rollout does not change sampling.
The server value is a fallback, not an enforced floor: explicit client values
win. WebUI and the Pi extension use 1.05 for every thinking effort and 1.0 for
off. Update server, clients, tests and docs together when changing that policy.

## Reasoning acceptance checks

Before live tests, inspect the **running** Deployment args and request payloads.
A short answer alone cannot prove which effort reached the model. The running
`--default-chat-template-kwargs` must contain thinking=true, effort=xhigh and
preservation=true. Keep the stock parser/template and thinking sampler.

```bash
kubectl -n vllm get deploy vllm-server -o json | jq '.spec.template.spec.containers[0].args'
uv run --with pyyaml python -m unittest discover -s scripts/tests -p test_qwen_reasoning.py -v
kubectl -n vllm port-forward svc/vllm-service 18000:8080
```

In another terminal, deliberately omit template kwargs to test the fallback.
Repeat with each row's kwargs and record the complete response, including
reasoning, content, tools and usage. This diagnostic bypasses LiteLLM; also
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

Repeat through Open WebUI and Pi. The WebUI function ID
`qwen_non_thinking_default` is updated in place; verify its PostSync
function-loader job succeeds and the stored filter contains the xhigh default.
Generic `high` maps to xhigh in WebUI. Saved explicit medium/low/off settings
remain honored, so test a fresh conversation as well as an existing one.

Pi's startup preference and local-only alias are managed in the companion
[dotfiles PR](https://github.com/mitchross/dotfiles/pull/10). After both PRs merge,
pull the updated dotfiles source and follow the scoped apply steps in the
[Pi guide](../../../docs/domains/ai-gpu/pi-agent-local-dev.md#default-reasoning-and-rollout).
Start a fresh session or explicitly select xhigh in a resumed one. The sampler
extension is unchanged by this rollout; reinstalling it alone does not change
Pi's selected effort. `pi-auto` still delegates effort to the selected backend.

In both clients inspect the outgoing sampler as well as kwargs: 1.05 for all
thinking modes, 1.0 for off, including through LiteLLM. A successful request
alone does not show which settings reached vLLM.

Offline tests check policy resolution and preservation of tool/image/history
payloads, not model quality. Actual tool/vision/multi-turn generation must pass
after merge. The 32K Pi output allowance includes reasoning and final content;
xhigh does not raise it. Treat `finish_reason=length` as inconclusive, not a
successful quality check. A completed empty final answer without tool calls is
a failure; empty content accompanying a valid tool call is normal. Stop on
loops, malformed tool output or lost history and inspect payloads before
changing runtime flags.

## Reproducible staging

`model-manifest.json` pins 77 necessary checkpoint/tokenizer/vision files by
revision, exact byte count and SHA-256 (30,889,980,352 bytes total, including
the checkpoint's MTP file even though speculation is disabled).

1. Wave -3 creates the namespace; wave -2 creates the scripts ConfigMap and
   dedicated NFS writer PV/PVC. The existing archive reader PVC is unchanged.
2. Wave -1 `vllm-download-qwen38-fp8` downloads into a revision-named directory
   on `192.168.10.133:/mnt/ai-pool/vllm`. Interrupted downloads retain `.part`
   files; every completed file is hash/size verified before atomic rename.
3. Wave 0 `vllm-cache-sync` verifies the archive, copies to local NVMe and
   verifies the destination. Only then does it publish `.verified-manifest`.
4. Wave 1 Deployment waits for the matching manifest marker and complete file
   inventory. Serving is offline from the local cache.

Warm syncs hash files again; same-size corruption must not be mistaken for a
valid cache. A manifest change invalidates old readiness. Failed copies never
publish readiness, and incomplete artifacts never replace verified files.
The wait container uses a small pinned Python image; it does not need CUDA.

Prerequisites: the NFS export permits the download Job to write and has at
least 31 GB free; local NVMe has at least that much free as well. The earlier
approximately 123 GiB local free-space check is historical; re-check storage
and export permissions before restaging. No private model token is required.
Existing AutoRound, GGUF and compile-cache files are retained; no pruning is performed.

## Verification after the user merges

ArgoCD applies the changed arguments through the existing `Recreate` deployment.
There will be an inference interruption while the model loads. This default
change does not alter the checkpoint, cache precision, memory budget or GPU ownership.

From the workstation:

```bash
kubectl -n vllm get jobs,pods
kubectl -n vllm logs job/vllm-download-qwen38-fp8
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
server ceiling, not a claim that two full 262K requests fit concurrently, or
that near-ceiling vision is verified. Run the existing
`benchmarks/ai-realworld-load/` harness after smoke checks; record TTFT,
prefill/decode, cache preemptions, GPU peaks, and a sustained multi-turn soak.
Test a context ladder before claiming 262K usability. Prefix caching makes
warm prompts cheaper; unique-prefix tests are needed for genuine prefill.
Compare the prior 2,048-token budget against the 8,192 aggregate / 4,096
per-request profile using the same prompts, output budgets and sampler. Test
one fresh long prompt, two fresh prompts, and a long prefill arriving during
decode. Record time to first token, inter-token latency, preemptions, available
KV capacity and peak memory. Do not reuse the September 6 pool measurements
as proof of capacity after changing prefill workspace. Prefix-hit counters
alone do not establish correctness or a latency improvement.

Stop on staging/hash failure, insufficient KV pool, OOM/Xid, broken tool or
vision output, or repeated preemptions. Do not enable MTP to rescue a failing
baseline. Preparation checks cover manifests, file integrity behavior and
routing configuration; they do not establish new runtime performance.

## Rollback

For an immediate per-request opt-down, explicitly select medium, low or off.
To restore the default permanently, revert the paired GitOps and dotfiles PRs,
apply the restored Pi settings and zshrc, and start a fresh session. ArgoCD
reconciles the server and WebUI policy; it cannot update workstation settings.
Do not change model weights, sampler or KV precision to roll back effort.

vLLM is the only GPU inference backend; there is no second backend to fall back
to. A bad checkpoint or runtime change is rolled back by reverting its commit and
letting the staging hooks re-run against the retained cache.

The old AutoRound files are retained under
`Qwen3.8-27B-W4A16-AutoRound-3090-int8lmhead`. A later INT4/W4A8 A/B must pin its
own artifact manifest and demonstrate TP=2/Marlin compatibility; do not assume
its single-card history proves the dual-card speed path.
