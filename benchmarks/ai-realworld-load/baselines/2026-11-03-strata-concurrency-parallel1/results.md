# Strata concurrency, one request at a time (parallel 1), 2026-11-03

Qwen3.8-Flash-Next IQ3_S on 2x RTX 3090 (layer split), Strata 0.1.40.3, 131K context, int8 KV, KV streaming.
`tools/concurrency_probe.py` straight to Strata (port-forward, not through LiteLLM): C different ~200-word prose
requests sent at once, `max_tokens` 256 (212-256 generated), thinking off, 2 rounds per level. C=1 uses the 3 warm
rounds (the very first request ran at 40 tok/s cold). TTFT includes the time spent waiting in Strata's queue.

| Concurrent | Total tok/s | Per-request decode tok/s | TTFT median | TTFT max (last in queue) | Slowest request |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 68.9 | 79.6 | 0.6 s | 0.76 s | 4.4 s |
| 2 | 64.0 | 76.2 | 2.3 s | 4.2 s | 7.4 s |
| 4 | 69.3 | 84.2 | 5.7 s | 10.9 s | 13.3 s |
| 8 | 74.7 | 86.5 | 11.7 s | 22.6 s | 24.9 s |

With one slot each request decodes at full speed and the others wait: total throughput stays flat (~65-75 tok/s)
and the Nth request's first token comes after N-1 whole answers (~3.3 s each here), so 4 at once -> 11 s and
8 at once -> 22.6 s for the last one. With real answers of 500-2000 tokens the wait grows in proportion.

`"parallel": 2` (batch slots) was not measured: changing it restarts the pod. Raw rows: `results.json`
(`rounds[]`, one entry per round).

```bash
kubectl -n strata port-forward deploy/strata-server 18080:8080
python3 tools/concurrency_probe.py --base-url http://127.0.0.1:18080/v1 --model qwen3.8-flash-next-iq3_s \
    --levels 1,2,4,8 --rounds 2 --max-tokens 256 --out results.json
```
