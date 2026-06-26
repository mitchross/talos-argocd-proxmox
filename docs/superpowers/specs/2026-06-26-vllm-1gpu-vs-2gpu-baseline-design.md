# vLLM 1-GPU vs 2-GPU Baseline Design

## Purpose

Measure the current "good" vLLM daily-driver experience on two RTX 3090s, then compare it against a temporary one-RTX-3090 configuration. The result should answer whether the second 3090 is mostly buying context capacity, concurrency headroom, latency, or all three.

## Scope

This is a manual live-cluster experiment. It does not change the GitOps source for `my-apps/ai/vllm`. The live Deployment may be patched during the test, but it must be restored to the repository-backed two-GPU configuration before the work ends.

## Baseline Configuration

The current known-good state is `my-apps/ai/vllm/deployment.yaml`:

- model: `/models/Qwen3.6-27B-AWQ-BF16-INT4`
- served model name: `qwen3.6-27b`
- GPUs: `nvidia.com/gpu: "2"`
- tensor parallelism: `--tensor-parallel-size 2`
- context: `--max-model-len 262144`
- max sequences: `--max-num-seqs 2`
- KV cache: `--kv-cache-dtype fp8_e4m3`

## One-GPU Test Configuration

Patch only the live Deployment:

- GPUs: `nvidia.com/gpu: "1"`
- tensor parallelism: `--tensor-parallel-size 1`
- context: `--max-model-len 65536`
- leave model, served name, sampling, endpoint, prefix caching, and chunked prefill unchanged

The one-GPU test intentionally keeps the same model and client endpoint so Open WebUI, Perplexica, Pi agent, and direct OpenAI-compatible clients do not need rewiring.

## Measurements

For both states, collect the same evidence:

- `kubectl get deploy,pod` and live vLLM args/resources so the tested state is explicit
- `/v1/models` response to prove the endpoint is available
- `benchmarks/vllm` Job output for request throughput, output tokens/sec, total tokens/sec, TTFT, TPOT, and ITL across concurrency levels
- vLLM `/metrics` samples for running/waiting requests and KV cache usage
- optional manual notes while using Open WebUI, Perplexica, and Pi agent concurrently

## Restore Requirement

After the one-GPU test, restore vLLM from GitOps source:

```bash
kubectl apply -k my-apps/ai/vllm
kubectl rollout status -n vllm deploy/vllm-server --timeout=20m
```

Then verify the live Deployment is back to `nvidia.com/gpu: "2"` and `--tensor-parallel-size 2`.

## Success Criteria

The experiment is complete when there are comparable 2-GPU and 1-GPU benchmark summaries, a brief interpretation of the difference, and the live cluster is restored to the known-good two-GPU configuration.
