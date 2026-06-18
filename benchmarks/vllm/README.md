# vLLM throughput benchmark

A repeatable, manual benchmark of the in-cluster vLLM OpenAI-compatible server
using `vllm bench serve`. It sweeps concurrency `1, 2, 4, 8, 16`, writes one JSON
result per level, and prints a consolidated summary table to the Job logs.

> **Manual-apply only — NOT GitOps-managed.** This lives under repo-root
> `benchmarks/` precisely because that path is outside every ArgoCD
> ApplicationSet scan path. ArgoCD never reconciles it. Run it by hand with
> `kubectl apply -k`, read the logs, then delete it.

## What it measures

| Metric (JSON key) | Meaning |
|---|---|
| `request_throughput` | completed requests / sec |
| `output_throughput` | **generated** tokens / sec |
| `total_token_throughput` | (prompt + generated) tokens / sec |
| `*_ttft_ms` | Time To First Token |
| `*_tpot_ms` | Time Per Output Token (decode latency, excludes prefill) |
| `*_itl_ms` | Inter-Token Latency |
| `max_concurrency` | in-flight cap for that run |

The concurrency sweep reveals the **saturation point**: where `output_throughput`
stops rising and TTFT/queueing starts climbing.

## ⚠️ Read this before interpreting results

The live server runs with **`--max-num-seqs 2`** (it's tuned for deep 262K
single-stream context, not high concurrency). It decodes **at most 2 sequences
at once**, so:

- `output_throughput` will roughly plateau **after concurrency = 2**.
- Beyond 2, extra requests **queue** — `ttft` climbs and `vllm:num_requests_waiting`
  goes above 0 (watch it in Grafana / `/metrics` during the run).
- This is expected behavior, not a benchmark bug. To benchmark true higher
  concurrency you'd raise `--max-num-seqs` on the server (a deliberate,
  separate change — not done here).

## 1. Find / confirm the vLLM service URL

```bash
# Service (namespace vllm, port 8080 → container 8000)
kubectl get svc -n vllm vllm-service

# In-cluster base URL (what the Job uses):
#   http://vllm-service.vllm.svc.cluster.local:8080
#   OpenAI API root: .../v1

# Confirm the served model name (the Job's MODEL env must match the "id"):
kubectl run curl-vllm --rm -i --restart=Never -n vllm --image=curlimages/curl --command -- \
  curl -s http://vllm-service.vllm.svc.cluster.local:8080/v1/models
# → currently {"id":"qwen3.6-27b", ...}
```

## 2. Run the benchmark

```bash
kubectl apply -k benchmarks/vllm
```

Override any knob without editing the file (set env, then re-apply / re-create):

```bash
# Example: longer outputs, only 1 and 4 concurrency
kubectl delete -k benchmarks/vllm          # remove the immutable old Job first
kubectl create -k benchmarks/vllm --dry-run=client -o yaml \
  | kubectl set env --local -f - OUTPUT_LEN=1024 CONCURRENCIES="1 4" -o yaml \
  | kubectl apply -f -
```

Tunable env vars (defaults): `VLLM_BASE_URL`, `MODEL=qwen3.6-27b`,
`TOKENIZER=/models/Qwen3.6-27B-AWQ-BF16-INT4`, `NUM_PROMPTS=128`, `INPUT_LEN=512`,
`OUTPUT_LEN=256`, `CONCURRENCIES="1 2 4 8 16"`.

> The Job mounts the existing **ReadOnlyMany** `vllm-models-pvc` so the `random`
> dataset tokenizes against the real local tokenizer with `HF_HUB_OFFLINE=1` —
> no Hugging Face Hub calls, exact-parity tokenization. It schedules **off** the
> GPU node and requests **no** GPU.

## 3. Watch it

```bash
# Stream logs (each concurrency run prints vllm's own table; a consolidated
# summary table prints at the very end)
kubectl logs -n vllm job/vllm-benchmark -f

# Pod status
kubectl get pods -n vllm -l app=vllm-benchmark
```

While it runs, watch the server-side view (queueing = saturation):

```bash
kubectl run curl-vllm --rm -i --restart=Never -n vllm --image=curlimages/curl --command -- sh -c \
 'curl -s http://vllm-service.vllm.svc.cluster.local:8080/metrics | grep -E "num_requests_(running|waiting)|gpu_cache_usage"'
```

## 4. Read the results

The consolidated table at the end of the logs is usually enough. For the raw
JSON (e.g. to copy off-cluster) before deleting:

```bash
POD=$(kubectl get pod -n vllm -l app=vllm-benchmark -o jsonpath='{.items[0].metadata.name}')
kubectl cp -n vllm "$POD":/results ./vllm-results    # only works while the pod still exists
```

**How to read it:**
- Find the concurrency where `out_tok/s` stops increasing — that's your
  throughput saturation point (expected ≈ 2 here, see warning above).
- `ttft_p95` rising sharply with concurrency = requests are queueing.
- `tpot_p50` ≈ steady-state per-token decode latency; `1000 / tpot_ms` ≈
  per-stream tokens/sec a single user sees.

## 5. Delete it

```bash
kubectl delete -k benchmarks/vllm
```

## Server-side metrics (Prometheus / Grafana)

vLLM's native Prometheus metrics are scraped continuously via the
`ServiceMonitor` that ships with the app at `my-apps/ai/vllm/servicemonitor.yaml`
(kube-prometheus-stack picks it up automatically). Useful PromQL during/after a run:

```promql
# Output (generated) tokens/sec
rate(vllm:generation_tokens_total{model_name="qwen3.6-27b"}[1m])

# Prompt tokens/sec
rate(vllm:prompt_tokens_total{model_name="qwen3.6-27b"}[1m])

# Total tokens/sec
rate(vllm:prompt_tokens_total{model_name="qwen3.6-27b"}[1m])
  + rate(vllm:generation_tokens_total{model_name="qwen3.6-27b"}[1m])

# Running vs waiting (queueing) requests — saturation signal
vllm:num_requests_running{model_name="qwen3.6-27b"}
vllm:num_requests_waiting{model_name="qwen3.6-27b"}

# KV cache utilization (0..1)
vllm:gpu_cache_usage_perc{model_name="qwen3.6-27b"}

# p95 TTFT (seconds)
histogram_quantile(0.95, sum by (le) (rate(vllm:time_to_first_token_seconds_bucket{model_name="qwen3.6-27b"}[5m])))

# p95 TPOT (seconds per output token)
histogram_quantile(0.95, sum by (le) (rate(vllm:time_per_output_token_seconds_bucket{model_name="qwen3.6-27b"}[5m])))
```
