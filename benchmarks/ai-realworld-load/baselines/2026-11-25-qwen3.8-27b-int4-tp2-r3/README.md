# qwen3.8-27b int4, TP=2, 3 repeats (2026-11-25)

A `compare_models.py` run against the model that vLLM serves today. It replaces the
2026-11-03 FP8 run as the current baseline; that run stays for comparison.

## What was running

Read from the live pod and `GET /v1/models` at 16:50Z, just before the run.

| Setting | Value |
|---|---|
| Model | `Qwen3.8-27B-int4-AutoRound-b4c61732c4f2`, served as `qwen3.8-27b` |
| Engine | vLLM 0.34.0, image `ghcr.io/mitchross/vllm-qwen38-dualfast:0.34.0-dualfast.1` |
| GPUs | 2x RTX 3090, tensor parallel 2, both unlocked, 200 W limit each |
| Context | 262,144 tokens, FP8 KV cache, FlashInfer attention |
| Batching | `--max-num-seqs 16`, chunked prefill, 8,192 batched tokens |

## How it differs from the 2026-11-03 run

- The requests went straight to `vllm-service.vllm.svc:8080`, not through LiteLLM. Expect
  a few milliseconds less TTFT than a LiteLLM run. The header line in `results.md` was
  edited by hand to say so.
- The quant and the engine both changed (FP8 on vLLM 0.32 → int4 AutoRound on vLLM 0.34),
  so the speed gain belongs to both together.
- Same prompts file, seed, thinking setting (off) and repeat count.

vLLM showed 0 running requests and about 1 finished request in the 30 minutes before the
run. Other traffic was not blocked during it.

## Medians

| Prompt | TTFT s | Prefill tok/s | Decode tok/s | Decode on 2026-11-03 |
|---|---:|---:|---:|---:|
| short-chat | 0.36 | 212.9 | 63.21 | 40.22 |
| prefill-8k | 4.21 | 1477.3 | 88.75 | 57.23 |
| coding | 0.29 | 505.2 | 62.89 | 39.70 |
| reverse-engineering | 0.41 | 571.1 | 62.74 | 39.30 |
