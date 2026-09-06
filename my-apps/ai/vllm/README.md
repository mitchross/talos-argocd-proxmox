# vLLM — official Qwen3.8-27B FP8 on two RTX 3090s

**Live production backend, verified 2026-09-06.** Official FP8 is loaded on
both cards. The [capacity and client audit](../../../docs/domains/ai-gpu/3090-llm-optimization.md)
records measured KV capacity and request checks. The medium fallback in this
PR takes effect after merge and Argo reconciliation; live probes sent medium explicitly.

| Setting | Value |
|---|---|
| Model | Official `Qwen/Qwen3.8-27B-FP8`, no Unsloth/GGUF conversion |
| Revision | `017b9c7af6b5689d5dd426a76e0bc077eb5ca20a` |
| Runtime | stock vLLM `v0.28.0`, existing immutable image digest |
| GPUs | 2 × RTX 3090, tensor parallel 2, multiprocessing executor |
| Interconnect | no custom all-reduce; NCCL P2P disabled; shared host transport |
| Context ceiling | 262,144 tokens, native model limit, no RoPE extrapolation |
| Concurrency | at most two sequences sharing one KV pool |
| Attention | FlashInfer explicitly selected for Ampere FP8 KV |
| KV / recurrent state | `fp8_e4m3` / float16 |
| GPU utilization budget | 0.92 per GPU |
| Prefill | chunked, 2,048 tokens per batch |
| Vision | native encoder; one image per request, video disabled |
| Reasoning | on, explicit `medium` default; `low` and `xhigh` per request |
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

Speculation is disabled because the GDN/Mamba long-session fault work remains
open. No community kernel patches, W4A8 overlays, or experimental speculative
backports are installed. Revisit MTP only against a fixed runtime and a
long-session regression test.
[Upstream fault/fix discussion](https://github.com/vllm-project/vllm/pull/50021)

## Endpoints and client compatibility

- model ID: `qwen3.8-27b`
- direct: `http://vllm-service.vllm.svc.cluster.local:8080/v1`
- existing app alias: `http://llama-cpp-service.llama-cpp.svc.cluster.local:8080/v1`
- LAN: `https://llama.vanillax.me/v1` and `https://vllm.vanillax.me/v1`

The vLLM Service selects its pod. The llama.cpp Service becomes an
`ExternalName` alias to it, so existing app configuration remains valid.
Both LAN hostnames are owned by the vLLM HTTPRoute, targeting its selector
Service directly; the gateway is not asked to route to an ExternalName.
The old llama.cpp route remains in Git for rollback but is not rendered.

## Explicit reasoning and sampling

The server supplies `enable_thinking=true`, `reasoning_effort=medium`, and
`preserve_thinking=true` through the checkpoint's native chat template.
The Qwen reasoning parser emits reasoning separately from answer content;
`qwen3_coder` parses tool calls and automatic tool choice remains enabled.

| Desired behavior | `chat_template_kwargs` |
|---|---|
| No thinking | `{"enable_thinking":false,"preserve_thinking":false}` |
| Brief thinking | `{"enable_thinking":true,"reasoning_effort":"low"}` |
| Normal coding (default) | `{"enable_thinking":true,"reasoning_effort":"medium"}` |
| Difficult task (explicit opt-in) | `{"enable_thinking":true,"reasoning_effort":"xhigh"}` |

The valid efforts are `low`, `medium`, and `xhigh`; `high` is invalid. Clients
should expose only valid levels or map generic `high` to `medium`. The server
merges its explicit defaults with request kwargs, so omitted effort stays
`medium`; do not remove that default and expose the upstream implicit `xhigh`.
No custom chat template is needed.

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
| `repetition_penalty` | 1.0 | 1.0 |

Changing the thinking flag alone does not switch vLLM's sampler. Direct
clients must send all six non-thinking values when opting out. Open WebUI's
Qwen filter applies these mode-specific values to both forwarding forms; Pi's
thinking toggle controls template kwargs, with the optional repo-owned
sampler extension selecting the matching values. See the
[Pi guide](../../../docs/domains/ai-gpu/pi-agent-local-dev.md).
[Official Qwen controls and sampling](https://huggingface.co/Qwen/Qwen3.8-27B-FP8#api-usage)

**Source check, 2026-09-06:** the official FP8 repository's latest revision is
still `017b9c7af6b5689d5dd426a76e0bc077eb5ca20a` (2026-08-14). There is no newer
official checkpoint in that history to migrate to. This change addresses
client/default behavior; it does not claim a universal cure for thinking loops.
`medium` is this deployment's coding policy, while upstream still defaults to
`xhigh` and cautions that lower effort can cause more retries in agent tasks.
[Official FP8 history](https://huggingface.co/Qwen/Qwen3.8-27B-FP8/commits/main)

## Reasoning acceptance checks

Before live tests, inspect the **running** Deployment args and request payloads.
A short answer alone cannot prove which effort reached the model. The running
`--default-chat-template-kwargs` must contain thinking=true, effort=medium and
preservation=true. Keep the stock parser/template and thinking sampler.

```bash
kubectl -n vllm get deploy vllm-server -o json | jq '.spec.template.spec.containers[0].args'
uv run --with pyyaml python -m unittest discover -s scripts/tests -p test_qwen_reasoning.py -v
kubectl -n vllm port-forward svc/vllm-service 18000:8080
```

In another terminal, this request deliberately omits template kwargs to test
the server fallback. Repeat it with each row's kwargs and record the complete
response (including `reasoning` or `reasoning_content`, content, tools and usage).

```bash
curl -fsS http://127.0.0.1:18000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3.8-27b","messages":[{"role":"user","content":"What is 37*43? Verify the calculation."}],"max_tokens":2048}'
```

| Case | Request / expected result |
|---|---|
| Default | Omit kwargs; running defaults resolve to enabled/medium/preserved; answer 1591 with separate reasoning. |
| Explicit low | `{"enable_thinking":true,"reasoning_effort":"low"}`; payload remains low, coherent answer. |
| Explicit medium | `{"enable_thinking":true,"reasoning_effort":"medium"}`; payload remains medium, coherent answer. |
| Explicit xhigh | `{"enable_thinking":true,"reasoning_effort":"xhigh"}`; xhigh appears only after explicit selection. |
| Off | `{"enable_thinking":false,"preserve_thinking":false}` plus the non-thinking sampler; empty/absent reasoning fields and no think tags in content. |
| Tool under medium | Supply a `lookup` function with an integer `id` argument and ask to look up id 7; expect a valid `tool_calls` entry with parseable JSON `{"id":7}`. Do not execute external actions. |
| Image under medium | Send one known local image as an `image_url` data URI plus a factual question; check visible facts against the actual image. HTTP 200 alone is insufficient. |
| Multi-turn medium | Append the full assistant tool-call message (including returned reasoning), a matching `tool_call_id` result and a follow-up question; expect coherent use of the result, intact roles and separately parsed reasoning/content/tools. |

For off, use the complete request policy, not just the thinking switch:

```json
{
  "chat_template_kwargs": {"enable_thinking": false, "preserve_thinking": false},
  "temperature": 0.7, "top_p": 0.8, "top_k": 20, "min_p": 0.0,
  "presence_penalty": 1.5, "repetition_penalty": 1.0
}
```

Repeat through Open WebUI and Pi. Capture their outgoing kwargs: Open WebUI's
legacy `qwen_non_thinking_default` function ID now updates in place to the
reasoning policy; Pi must retain its explicit mapping and medium startup level.
Generic `high` must become medium in WebUI or be unavailable in Pi. Clear stale
per-chat presets that explicitly request xhigh. Stored user/client settings
outside Git still require payload inspection after rollout.

The offline tests check policy resolution and preservation of tool/image/history
payloads, not model quality. Actual tool/vision/multi-turn generation must pass
after merge. Treat output truncation (`finish_reason=length`) as inconclusive,
not a successful reasoning check. Stop on loops, malformed tool output or lost
history and inspect payloads before changing runtime flags. Roll back this
reasoning-policy commit through Git if needed; it does not alter backend sizing.

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
least 31 GB free; local NVMe has at least that much free as well. Local free
space was checked at approximately 123 GiB before staging. NAS SSH access was
unavailable from this workstation, so export write permissions and NAS free
space remain rollout checks. No private model token is required. Existing
AutoRound, GGUF and compile-cache files are retained; no pruning is performed.

## Verification after the user merges

Application-level sync waves do not order separate Applications. During the
swap the new two-GPU pod may be Pending until Argo scales llama.cpp to zero;
that is expected. There will be an inference interruption during model loading.

From the workstation:

```bash
kubectl -n vllm get jobs,pods
kubectl -n llama-cpp get deploy llama-cpp-server
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

Expected: both staging hooks complete, vLLM Ready, llama.cpp at zero,
two GPUs visible to vLLM, health OK, the expected model ID and answer 42.
Also verify both LAN hostnames and an existing app using the llama.cpp DNS
alias, one image, a tool call, and every reasoning mode.

**Read the allocated KV capacity from startup logs.** 262K is the configured
server ceiling, not a claim that two full 262K requests fit concurrently, or
that near-ceiling vision is verified. Run the existing
`benchmarks/ai-realworld-load/` harness after smoke checks; record TTFT,
prefill/decode, cache preemptions, GPU peaks, and a sustained multi-turn soak.
Test a context ladder before claiming 262K usability. Prefix caching makes
warm prompts cheaper; unique-prefix tests are needed for genuine prefill.
The 2,048-token prefill batch favors interactive latency over peak bulk prefill.

Stop on staging/hash failure, insufficient KV pool, OOM/Xid, broken tool or
vision output, or repeated preemptions. Do not enable MTP to rescue a failing
baseline. Preparation checks cover manifests, file integrity behavior and
routing configuration; they do not establish new runtime performance.

## Rollback

Revert the FP8 cutover commit through Git, preserving the prior hardware
expansion. That restores llama.cpp's replica, selector Service, both-hostname
HTTPRoute and vLLM's old alias/zero replicas. Argo releases vLLM's two cards
before the retained one-card GGUF profile can run. Verify the model ID and
endpoints again. The caches remain intact, so rollback needs no large model
transfer.

The old AutoRound files are retained under
`Qwen3.8-27B-W4A16-AutoRound-3090-int8lmhead`. A later INT4/W4A8 A/B must pin its
own artifact manifest and demonstrate TP=2/Marlin compatibility; do not assume
its single-card history proves the dual-card speed path.
