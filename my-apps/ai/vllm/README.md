# vLLM — Qwen3.8-27B on one RTX 3090

The node's other 3090 runs Strata (Qwen3.8-Flash-Next, [`../strata/`](../strata/README.md)).

**Git-declared backend and operating policy.** The
[2026-09-06 capacity and client audit](../../../docs/domains/ai-gpu/3090-llm-optimization.md)
records measurements of the earlier v0.28.0 deployment, with medium sent
explicitly. It is not a benchmark of the current tunables or xhigh default below; the running version is pinned in `deployment.yaml`.
Confirm the running arguments and repeat acceptance after merge and Argo reconciliation.

| Setting | Value |
|---|---|
| Model | `Qwen3.8-27B-W4A16-AutoRound-3090-int8lmhead`: local W4A16 AutoRound of Qwen3.8-27B, INT8 `lm_head`, BF16 `embed_tokens` |
| Runtime | stock vLLM, pinned immutable image digest |
| GPUs | 1 × RTX 3090, tensor parallel 1 |
| Context ceiling | 65,536 tokens (prompt plus output) |
| Concurrency | up to three sequences sharing one KV pool; the pool, not the slot count, bounds what runs |
| Attention | FlashInfer explicitly selected for Ampere FP8 KV |
| KV / recurrent state | `fp8_e4m3` / float16 |
| GPU utilization budget | 0.93 (0.90 left too little KV for one 65,536-token request) |
| Prefill | 2,048-token budget per step |
| Vision | native encoder; one image per request, video disabled |
| Reasoning | on, explicit `xhigh` default; `low` and `medium` per request |
| Speculation | MTP, 2 draft tokens |
| Power | existing 220 W per card |
| Host resources | 8 GiB request, 64 GiB limit; VPA recommendation-only |

The official FP8 checkpoint is 28.77 GiB and does not fit one 24 GiB card, so
the single card serves the W4A16 checkpoint it ran before the dual-card setup
(#2102). The FP8 files stay on the NFS archive and the node cache for a return
to two cards.

FlashInfer is explicitly selected: vLLM 0.28.0's Triton backend rejects FP8
KV on SM86. The official checkpoint does not contain calibrated K/V scales;
the stock FP8 path uses unit scales. This makes answer-quality and long-context
checks part of acceptance, not just throughput checks. No unsupported legacy
`--calculate-kv-scales` flag is added to this runtime.
[vLLM FlashInfer support](https://github.com/vllm-project/vllm/blob/v0.28.0/vllm/v1/attention/backends/flashinfer.py),
[Triton architecture guard](https://github.com/vllm-project/vllm/blob/v0.28.0/vllm/v1/attention/backends/triton_attn.py),
[KV scale handling](https://github.com/vllm-project/vllm/blob/v0.28.0/vllm/model_executor/layers/quantization/kv_cache.py).

MTP with two draft tokens is back on, as in the earlier single-card setup.
The upstream GDN spec-decode fix is still open; if long sessions fault, remove
the two `--speculative-config` lines first.
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

`--max-num-batched-tokens 2048` is the per-step scheduling budget. A larger
budget raises the profiled activation peak and takes VRAM from the KV pool,
which one card cannot spare.

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

## Single-card checkpoint

The W4A16 checkpoint was quantized locally and has no Hugging Face revision.
`model-manifest.json` pins it with `"repo": null`, so the download Job only
verifies the archive copy and never fetches anything. Generate the manifest
from the NFS archive once, before merging a checkpoint change:

```bash
kubectl -n vllm create configmap vllm-describe-checkpoint \
  --from-file=model_cache.py=my-apps/ai/vllm/scripts/model_cache.py
kubectl apply -f my-apps/ai/vllm/manual/describe-checkpoint-job.yaml
kubectl -n vllm wait --for=condition=complete job/vllm-describe-checkpoint --timeout=2h
kubectl -n vllm logs job/vllm-describe-checkpoint > my-apps/ai/vllm/model-manifest.json
kubectl -n vllm delete job/vllm-describe-checkpoint configmap/vllm-describe-checkpoint
```

Expected: a JSON file with `"repo": null`, the checkpoint directory and one
size and SHA-256 per file. `test_vllm_model_cache.py` fails until the manifest
names the directory the Deployment serves.

## Reproducible staging

`model-manifest.json` pins every checkpoint file by exact byte count and
SHA-256 (and by revision when the checkpoint has an upstream).

1. Wave -3 creates the namespace; wave -2 creates the scripts ConfigMap and
   dedicated NFS writer PV/PVC. The existing archive reader PVC is unchanged.
2. Wave -1 `vllm-download-qwen38-fp8` downloads into a revision-named directory
   on `192.168.10.133:/mnt/ai-pool/vllm`. Interrupted downloads retain `.part`
   files; every completed file is hash/size verified before atomic rename.
   A `"repo": null` checkpoint is only verified there, never downloaded.
3. Wave 0 `vllm-cache-sync` verifies the archive, copies to local NVMe and
   verifies the destination. Only then does it publish `.verified-manifest`.
4. Wave 1 Deployment waits for the matching manifest marker and complete file
   inventory. Serving is offline from the local cache.

Warm syncs hash files again; same-size corruption must not be mistaken for a
valid cache. A manifest change invalidates old readiness. Failed copies never
publish readiness, and incomplete artifacts never replace verified files.
The wait container uses a small pinned Python image; it does not need CUDA.

Prerequisites: the checkpoint is complete on the NFS archive and the local
NVMe has room for it. No private model token is required.
Existing AutoRound, GGUF and compile-cache files are retained; no pruning is performed.

## Verification after the user merges

ArgoCD applies the changed arguments through the existing `Recreate` deployment.
There will be an inference interruption while the cache sync copies the W4A16
files to the node and the model loads. The node cache has 440 GB free (Nov 3).

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

Expected: both staging hooks complete, vLLM Ready, one GPU visible to vLLM,
health OK, the expected model ID and answer 42. Also verify both LAN hostnames,
one image, a tool call, and every reasoning mode.

**Read the allocated KV capacity from startup logs.** It must hold at least one
65,536-token request. To compare against Strata on the other card, run
[`compare_models.py`](../../../benchmarks/ai-realworld-load/tools/README.md). Run the existing
`benchmarks/ai-realworld-load/` harness after smoke checks; record TTFT,
prefill/decode, cache preemptions, GPU peaks, and a sustained multi-turn soak.
Prefix caching makes warm prompts cheaper; unique-prefix tests are needed for
genuine prefill. Prefix-hit counters alone do not establish correctness or a
latency improvement.

Stop on staging/hash failure, insufficient KV pool, OOM/Xid, broken tool or
vision output, or repeated preemptions. Preparation checks cover manifests, file integrity behavior and
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

To return to two cards, revert this change: the FP8 checkpoint, its manifest
and the TP=2 flags come back together, and Strata's Deployment must go to zero
replicas first.
