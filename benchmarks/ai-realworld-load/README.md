# Real-world AI load baseline (dual vs single RTX 3090)

Answered one question: **can ONE RTX 3090 serve the real workload without
materially losing usable context?** Context capacity was the criterion, not
tokens/sec. **It can** — see Results below.

The Deal Scout digest is excluded from both baselines: it 500s on an
application bug, so it contributed no load and would have made the comparison
uneven.

Not ArgoCD-managed — `benchmarks/` sits outside every AppSet glob. Nothing here
deploys; the collector only reads. Runs land in `runs/` (git-ignored).

## Baselines

| | Hardware | Model | Status |
|---|---|---|---|
| **A** | 2x RTX 3090, TP=2, PCIe/no NVLink | Qwen3.8-27B-**FP8** (Marlin weight-only) | measured |
| **B** | 1x RTX 3090, TP=1 | Qwen3.8-27B W4A16 AutoRound, INT8 `lm_head`, BF16 `embed_tokens` | measured |

Both used the **verbatim prompts in this file**. Any re-run must too, or the
comparison is void.

## Results

| | A — 2x3090 | **B — 1x3090** |
|---|---:|---:|
| KV pool | 313,367 | **200,826** |
| Peak resident context | 160,468 (51.2%) | **152,867 (76.1%)** |
| Preemptions | 0 | **0** |
| Prefix-cache hit rate | 97.5% | **96.3%** |
| Truncation / abort / error | 0 / 0 / 0 | **0 / 0 / 0** |
| TTFT mean | 3.808s | 4.564s |
| Prefill mean | 3.012s | 4.242s |
| TPOT mean | 0.036s | 0.038s |
| Completed requests | 122 | 141 |

**One 3090 is sufficient for this workload.** The penalty is prefill and TTFT
latency, not usable context. Full analysis and the rules that follow:
[`docs/domains/ai-gpu/single-vs-dual-3090.md`](../../docs/domains/ai-gpu/single-vs-dual-3090.md).

Caveat kept deliberately: the agent workload converged near 146K tokens of
context in B, so the pool was measured to ~76% utilisation. Behaviour nearer the
ceiling is extrapolated.

### Baseline B configuration

```
vLLM 0.27.1 (STOCK image) · Qwen3.8-27B W4A16 + INT8 g128 lm_head · TP=1 · 1 card
--max-model-len 180000        --gpu-memory-utilization 0.972
--max-num-seqs 3              --max-num-batched-tokens 2048
--kv-cache-dtype fp8_e4m3     --language-model-only  (text-only, no vision)
--async-scheduling            max_cudagraph_capture_size 4
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
200W/card power limit

KV capacity ceiling : 200,826 tokens   <- read from the boot log, never predicted
Max concurrency     : 1.12x @ 180,000
Weights             : 15.43 GiB   activation: 0.75  CUDA graphs: 0.45  KV: 6.50 GiB
```

### Baseline A configuration (measured at boot, not assumed)

```
vLLM 0.27.1 · Qwen3.8-27B-FP8 · TP=2 · mp · no custom all-reduce
--max-model-len 262144      (native, NO YaRN)
--max-num-seqs 3
--gpu-memory-utilization 0.92
--kv-cache-dtype fp8_e4m3   (uncalibrated, scale 1.0)
--enable-prefix-caching --enable-chunked-prefill --max-num-batched-tokens 8192
--limit-mm-per-prompt {"image": 16}
200W/card power limit

KV capacity ceiling : 313,367 tokens   <- Baseline A ceiling. Not the earlier ~291K estimate.
Max concurrency     : 1.20x @ 262,144
Weights             : 14.46 GiB/GPU   KV: 4.99 GiB/GPU   CUDA graphs: 0.46 GiB/GPU
```

**Do not change** gpu-memory-utilization, KV precision/scales, quantization, or
any other vLLM tuning during Baseline A.

### FP8 KV cache — stated accurately

> Uncalibrated FP8 KV; vLLM defaults to scale 1.0 when checkpoint scales are
> unavailable; published vLLM accuracy work suggests this is often good,
> including strong Qwen3.5-27B long-context results, but our exact RTX
> 3090/SM86 Qwen3.8 path is not independently validated.

Hence the retrieval sanity check in step 6. `--calculate-kv-scales` stays **off**.

### Preemption is RECOMPUTE — verified in the running engine

Confirmed by reading `vllm/v1/core/sched/scheduler.py` inside the live pod, not
from docs. `_preempt_request()` calls `_free_request_blocks()` and sets
`request.num_computed_tokens = 0`. There is no `PreemptionMode` and no
`swap_out` anywhere under `vllm/v1/` — swap was removed in V1.

A preempted 262K request therefore **re-prefills from token 0** (32 chunks at
`max-num-batched-tokens 8192`). Prefix caching can partially rescue it, but the
blocks it would need are the ones evicted under the pressure that caused the
preemption. At 1.20x concurrency this is the most likely source of a severe
user-visible stall with no request technically failing — which is why
`report.py` prints per-event forensics including KV% immediately before.

## What gets measured, and how honestly

| Number | Source | Tag |
|---|---|---|
| Peak simultaneous resident context | `kv_cache_usage_perc` x 313,367 | **DERIVED** (upper bound: includes prefix-cache blocks) |
| Pi peak context | `usage.input` in Pi's session JSONL | **MEASURED** |
| Perplexica peak context | histogram bucket, Pi excluded by elimination | **DERIVED** (range) |
| Deal Scout digest prompt | smallest histogram bucket; exact via `/tokenize` after | **DERIVED** |
| running / waiting / preemptions / KV% | vLLM gauges + counters | **MEASURED** |
| TTFT / TPOT / queue / prefill | histogram `_sum`/`_count` deltas | **DERIVED** (means) |
| VRAM / util / power / temp per card | `nvidia-smi` in the powerlimit DaemonSet | **MEASURED** |

vLLM's `request_prompt_tokens` buckets are coarse (…20k, 50k, 100k, 200k, Inf),
so server-side per-request sizes are **ranges**. Getting exact values would need
`--enable-log-requests` (a restart) or a logging proxy (changes production app
behaviour) — both out of scope. Per-request counts are never invented from
aggregate counters.

## Run sequence

Two traps that invalidate a run, both hit in practice:

- **Restart vLLM first and verify the prefix cache is cold**
  (`prefix_cache_queries_total` and `hits` both 0). A warm cache contaminates
  exactly the metric under test.
- **Drive long HTTP workloads from inside the cluster.** The external gateway
  terminates connections at 300s, killing a research query mid-flight.
  `kubectl port-forward` does not work for Perplexica — it binds the pod IP, so
  forwarding to localhost is refused. A detached Job calling the service DNS is
  immune to both.

```bash
cd benchmarks/ai-realworld-load

# 1. start collection (verifies /health first, refuses on an unhealthy server)
./tools/collect.sh start baseline-a

# 2. watch it, in a second terminal — reads only the collector's files
./tools/live.sh
```

Then launch the three workloads **close together** — all three must genuinely
overlap or the run does not test concurrency. `report.py` fails loudly if they
never do.

3. **Workload A — Perplexica.** Open <https://perplexica.vanillax.me>, select
   `Qwen 3.8 27B (vLLM, TP=2)`, paste the Workload A prompt below.
4. **Within ~30s, Workload B — Pi.** In a clone of `mitchross/deal-scout`:
   `pi --model qwen3.8-27b` then paste the Workload B prompt.
5. **Workload C — Deal Scout digest**, once A and B are both generating:
   ```bash
   curl -sS -X POST https://deals.vanillax.me/api/digest/generate | jq '.model, .note'
   ```
   Read-only summarisation of existing rows; writes one `digests` row. It does
   not mutate listings.
6. **Retrieval sanity check**, while long contexts are resident — asks the model
   to recall something only findable deep in Perplexica's own returned context:
   in the same Perplexica thread, ask
   `Quote the exact sentence from your sources that gives the VRAM figure for the Ryzen AI Max+ 395, and name the source.`
   A confident answer citing nothing, or a number absent from the sources, is
   the FP8-KV/long-context failure mode we are watching for.
7. Tell me when all three are active. Leave the collector running until
   everything finishes.

```bash
# 8. finalise
./tools/collect.sh stop
./tools/report.py runs/<dir> --pi-session ~/.pi/agent/sessions/<deal-scout-dir>/<newest>.jsonl
```

---

## Workload A — Perplexica (verbatim; reuse for Baseline B)

```
Research Qwen3.8-27B local inference as of August 2026. Determine the practical
hardware requirements for running it as a long-context local research and coding
model. Compare 1x RTX 3090, 2x RTX 3090 over PCIe without NVLink, Ryzen AI Max+
395, Ryzen AI Max+ PRO 495, and NVIDIA DGX Spark.

Investigate Qwen3.8 itself, not merely Qwen3.6.

For every result distinguish:
- directly measured Qwen3.8 data
- same-architecture Qwen3.6 proxy data
- vendor claims
- calculated estimates
- community anecdotes

Research:
- model and quantization formats
- inference runtime
- VRAM/memory usage
- usable context length
- KV-cache format
- long-context retrieval quality
- prefill performance at large context
- decode performance
- speculative decoding/MTP
- power draw where measured
- Qwen3.8-specific bugs
- Claude Code/Codex/Pi compatibility
- whether one 24GB RTX 3090 can provide roughly 200-256K useful context without
  unacceptable quality or prefill loss
- whether dual 3090s materially improve useful context/concurrency
- current KVarN/TurboQuant/low-bit-KV developments

Use primary sources where possible, plus high-quality GitHub issues and
community measurements.

Reconcile conflicting measurements rather than picking whichever number looks
best.

Produce a detailed cited report.
```

## Workload B — Pi in `mitchross/deal-scout` (verbatim; reuse for Baseline B)

Let Pi read files naturally. Do **not** stuff files into the prompt — the point
is watching context grow on its own.

```
Perform a deep READ-ONLY architecture and correctness investigation of this
repository.

Trace the real system from scraper ingestion through normalization,
price/quantity extraction, classification, persistence, ranking/filtering,
Temporal/background processing, dashboard/API output, and local-LLM
digest/analysis.

Inspect implementation, tests, configuration, docs, git history where useful,
and representative data handling.

Pay special attention to:
- product/model numbers incorrectly interpreted as quantities
- lot/bundle/quantity inference
- false-positive deal classification
- duplicate/normalization behavior
- stale or conflicting business rules
- where deterministic logic stops and LLM judgment begins
- guards against hallucinated LLM facts/numbers
- failure/retry behavior
- places where a prior debugging fix may have created a new edge case

Run existing tests as appropriate.

Do NOT modify files.

Return the five most important correctness/architecture findings with exact
files/functions, evidence, and recommended follow-up tests.
```

## Workload C — Deal Scout digest

Real supported path, confirmed in source: `dashboard/app.py:834`
`POST /api/digest/generate` -> `generate_digest(conn)`, driven in production by
`worker/activities.js:82 generateDigest()`.

`build_digest_facts()` is pure SQL and always renders; `narrate_digest()` is the
optional LLM leg. It is **best-effort by design** — that is exactly why the dead
`qwen3.6-27b` id produced no error for months, just silently factual digests. If
`.model` in the response is null, the LLM leg did not run and Workload C
contributed no load.

---

## Engine A/B — vLLM control vs NInfer-3090 candidate

The candidate is `my-apps/ai/ninfer/` (NInfer-3090 `v0.6.0-rtx3090`, commit
`2ae51915225d`, official `qwen3_8_27b.ninfer` artifact, SHA-pinned). The
chassis holds **one RTX 3090 — permanently** — so the engines are compared
**sequentially on the identical card** by scale-swapping committed replicas
(`vllm-server: 1/ninfer-server: 0` ↔ `0/1`, one commit each way — see
`docs/domains/ai-gpu/gpu-scale-swap.md`). Same silicon, same 200 W cap, and
every swap restarts the engine, so each window starts with a provably cold
prefix cache. The vLLM control config and everything above this line is
UNCHANGED — control runs still use `collect.sh` + `report.py` and the verbatim
Workload A/B prompts. Workload C (Deal Scout digest) stays excluded while its
application bug stands.

The card is power-limited to 200 W by the powerlimit DaemonSet; do not change
that between the two windows of an A/B without recording it in `context.env`.

### Candidate #2 — qwen38-3090 (syv-ai patched vLLM)

`my-apps/ai/qwen38-3090/` (pinned commit `e00bc1b7`) is **vLLM 0.27.1 with
upstream patches** — so unlike NInfer it speaks normal vLLM Prometheus, and the
CONTROL tooling collects it directly:

```bash
BENCH_NS=qwen38-3090 BENCH_APP=qwen38-3090-server \
BENCH_DEPLOY=qwen38-3090-server BENCH_PORT=18020 ./tools/collect.sh start qwen38-window
```

Same swap-window procedure as below with `CANDIDATE_URL=https://qwen38.vanillax.me/v1
CANDIDATE_MODEL=qwen3.8-27b` for `ab-smallload.sh candidate`. Two comparison
caveats stated up front: this candidate is **text-only** (`--language-model-only`
is hardcoded upstream — vision rows are N/A), and upstream's published numbers
were measured at **250 W** against our 200 W cap.

### Candidate tooling (parallel, not replacing)

| | Control (vLLM) | Candidate (NInfer) |
|---|---|---|
| Collector | `tools/collect.sh` | `tools/collect-ninfer.sh` |
| Report | `tools/report.py` | `tools/report-ninfer.py` |
| Server-side source | Prometheus `/metrics` | schema-v8 request-log JSONL (`/logs/serve.requests.jsonl`, emptyDir — collect DURING the run; lost on pod restart) |
| Endpoint | `https://vllm.vanillax.me/v1`, model `qwen3.8-27b` | `https://ninfer.vanillax.me/v1`, model `qwen3.8-ninfer` |

`tools/openai_probe.py` is the shared streamed client — the same code times
both engines, so client-side TTFT/decode/E2E are comparable by construction.
Client-side and server-side numbers are reported separately and never mixed.

### Metric semantics — what is and is not comparable

| Concept | vLLM | NInfer | Comparable? |
|---|---|---|---|
| TTFT / prefill / decode | histogram sums (server) | `request_done.timings_seconds` (server) | yes (both server-side) |
| Decode tok/s | derived from inter-token latency | derived: completion / decode_s | yes (derived, per engine) |
| Prefix reuse | `prefix_cache_{hits,queries}_total` | per-request `cache_tokens` / `prefix_reuse_path` | approximately (rate vs per-request) |
| Spec decode acceptance | `spec_decode_num_{accepted,draft}_tokens_total` (MTP2) | `speculative.{accepted,drafted}_tokens` (MTP3) | yes, but draft counts differ (2 vs 3) — compare acceptance %, state the mode |
| KV usage over time | `kv_cache_usage_perc` gauge | **N/A** — startup KV ledger only | no; report NInfer's ledger + admission behavior |
| Preemption | recompute preemption counter | **N/A** — concept absent (FIFO full-entitlement admission; overload → 429/503) | no; count queue rejections/timeouts instead |
| Peak VRAM / util / power | nvidia-smi (powerlimit DS) | nvidia-smi (powerlimit DS) | yes |

Known control/candidate config differences to state with any result: vLLM runs
MTP2 + FP8 KV + 65,536 context; NInfer starts at MTP3 + INT8 KV + 32,768
context (the fork's only tested vision profile). These are each engine's
recommended shapes — the comparison is engine-vs-engine as operated, not
knob-for-knob identical.

### Order of operations

Every candidate step below happens inside a **NInfer window** (committed swap:
`ninfer-server: 1`, `vllm-server: 0`); control steps happen inside a **vLLM
window** (the normal production state). One engine at a time, always.

1. **Control window — baseline A/B half:** with production vLLM up,
   `collect.sh start ab-control`, then `tools/ab-smallload.sh control`
   (6,055-token fixed prompt — counted by the live Qwen tokenizer — ~600-token
   answer, cold then warm, C1). Stop the collector. Note the printed `RUN=` dir.
2. **Swap to NInfer** (one commit), then **smoke (correctness before speed):**
   `tools/smoke-ninfer.sh all <image.jpg>` — text stream, thinking on/off,
   tools (`tool_choice=auto` is the Perplexica-compatibility gate), vision
   (judge the description content), 16K-context needle. Vision must name
   details actually present in the image; HTTP 200 is not a pass.
3. **Candidate A/B half, same window:** `collect-ninfer.sh start ab-candidate`,
   then `AB_RUN=<dir-from-step-1> tools/ab-smallload.sh candidate`. Stop the
   collector; run both reports. Then the **real workload**: Workload A
   (Perplexica: point its custom-OpenAI provider at the NInfer endpoint in its
   settings UI — config-only, revert after) and Workload B (Pi: add a
   `vanillax-ninfer` provider to `~/.pi/agent/models.json`,
   `pi --model qwen3.8-ninfer`) with the VERBATIM prompts above. Note that
   in-cluster consumers (Open WebUI etc.) are down during a NInfer window —
   that is inherent to single-card swap. Swap back to vLLM when done.
4. **Long-context gate (only after 1–3 pass):** raise `--max-context`/
   `--kv-capacity` through git one step at a time — 65,536 → 131,072 → 153,600
   → 163,840 — and at each step run `tools/smoke-ninfer.sh context <N>` plus a
   real Pi session, watching VRAM, TTFT, prefill, decode, MTP acceptance, and
   the retrieval sanity check from step 6 above. Success is the ~150K-class Pi
   working set served without truncation/OOM/corruption at acceptable latency —
   not "server started". A startup KV allocation at some size proves nothing
   about sustained serving at that size.
