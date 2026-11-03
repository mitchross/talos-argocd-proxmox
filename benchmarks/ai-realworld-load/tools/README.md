# Comparing the two GPU models (`compare_models.py`)

`compare_models.py` sends the same fixed prompts to each LiteLLM model and
saves the timings and answers side by side. By default it compares
`qwen3.8-27b` (vLLM, GPU 0) with `qwen3.8-flash-next` (Strata, GPU 1).

The prompts are in `../workloads/compare-prompts.json`:

| id | What it tests |
|---|---|
| `short-chat` | short answer, 256 output tokens |
| `prefill-8k` | ~8K-token prompt with a hidden code to recall (prefill speed) |
| `coding` | a Python function plus unit tests |
| `reverse-engineering` | explain a short x86-64 routine and write its inverse |

Every request gets a unique first line, so neither engine can answer from
its prefix cache. Both models get the same sampler and thinking setting.

## Run it

Needs Python 3 only (no packages). Run it when nothing else is using the
models: Strata serves one request at a time, so other traffic queues ahead of
yours and inflates TTFT.

```bash
export LITELLM_API_KEY=...            # the LiteLLM master key (1Password: litellm/master_key)
# In the cluster (Hermes, a pod): the Service URL. From the LAN: https://litellm.vanillax.me/v1
export LITELLM_BASE_URL=http://litellm-service.litellm.svc.cluster.local:4000/v1

python3 benchmarks/ai-realworld-load/tools/compare_models.py                       # all prompts, both models
python3 benchmarks/ai-realworld-load/tools/compare_models.py --repeats 3           # medians over 3 runs
python3 benchmarks/ai-realworld-load/tools/compare_models.py --only short-chat --models qwen3.8-27b
python3 benchmarks/ai-realworld-load/tools/compare_models.py --thinking medium     # default: thinking off
```

Results go to `benchmarks/ai-realworld-load/runs/<UTC time>_compare/`
(git-ignored), or to `--out <dir>`:

- `results.md`: one table row per prompt and model, then the answers in a
  two-column table.
- `results.json`: run settings, the summary table, the answers keyed by
  prompt and model (`side_by_side`), and every raw run.

The script exits 1 when any request failed.

## What the numbers mean

| Column | How it is measured |
|---|---|
| TTFT s | request sent to the first streamed token (reasoning or answer), seen by this client |
| Prefill tok/s | prompt tokens / TTFT; includes the LiteLLM hop and any queueing |
| Decode tok/s | output tokens / time between the first and last streamed token |
| Total s | request sent to stream closed |
| Prompt / Output tok | the engine's own `usage` block |

These are client-side numbers through the gateway, so compare the two models
with each other, not with server-side figures from vLLM's `/metrics`. One run
per prompt is noisy; use `--repeats 3` before drawing conclusions. If you
change the prompt file, old results are no longer comparable.
