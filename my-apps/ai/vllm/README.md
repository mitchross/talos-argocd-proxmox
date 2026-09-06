# vLLM — official Qwen3.8-27B FP8 on two RTX 3090s

**Git-declared production cutover.** This profile replaces the one-card
llama.cpp backend after merge and Argo reconciliation. The new FP8 model has
not yet been loaded or benchmarked during preparation of this change.

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
| Reasoning | on, explicit `low` default; `medium` and `xhigh` per request |
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

The server supplies `enable_thinking=true`, `reasoning_effort=low`, and
`preserve_thinking=true` through the checkpoint's native chat template.
The Qwen reasoning parser emits reasoning separately from answer content;
`qwen3_coder` parses tool calls and automatic tool choice remains enabled.

| Desired behavior | `chat_template_kwargs` |
|---|---|
| No thinking | `{"enable_thinking":false}` |
| Brief thinking | `{"enable_thinking":true,"reasoning_effort":"low"}` |
| Normal coding | `{"enable_thinking":true,"reasoning_effort":"medium"}` |
| Deliberate reasoning | `{"enable_thinking":true,"reasoning_effort":"xhigh"}` |

The valid effort values are `low`, `medium`, and `xhigh`; `high` is not a
valid model-template value. The default thinking sampler is temperature 1.0,
top-p 0.95, top-k 20, min-p 0, presence penalty 0. Clients disabling thinking
should also send temperature 0.7, top-p 0.8 and presence penalty 1.5 to use the
published instruct sampler. Changing a request's thinking flag does not
implicitly change the server-wide sampling defaults.
[Official model usage and sampling](https://huggingface.co/Qwen/Qwen3.8-27B-FP8)

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
  -d '{"model":"qwen3.8-27b","messages":[{"role":"user","content":"What is 19 + 23?"}],"max_tokens":64,"temperature":0,"chat_template_kwargs":{"enable_thinking":false}}'
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
