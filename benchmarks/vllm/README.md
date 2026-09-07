# Historical vLLM throughput benchmark

**Retired fixture.** The adjacent Job targets the old Qwen3.6 AWQ tokenizer
and an older benchmark client. It is outside ArgoCD discovery and is not a
current deployment or an acceptance test for official Qwen3.8-27B FP8.
Do not apply it unchanged to the current server.

Use [the real-workload harness](../ai-realworld-load/README.md) and the
[current vLLM acceptance runbook](../../my-apps/ai/vllm/README.md) for the
`qwen3.8-27b` backend. The [dual-3090 capacity audit](../../docs/domains/ai-gpu/3090-llm-optimization.md)
records the measured pool, context tests, and their limitations.

If reviving this synthetic throughput sweep, first update and verify its
client version, model ID, tokenizer path, explicit reasoning/sampling, and
result handling in a separate PR. Fixed-length random prompts with ignored
EOS measure throughput, not answer quality. Concurrency above two queues on
the current server; two slots do not provide two full 262K contexts.

Historical commands and observations remain in Git history. No benchmark Job
was submitted as part of the September reasoning/client audit.
