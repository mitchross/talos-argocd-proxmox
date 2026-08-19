# vLLM — Qwen3.8-27B on one RTX 3090

This ArgoCD-discovered app serves `qwen3.8-27b` from one 24 GiB RTX 3090 at:

- in cluster: `http://vllm-service.vllm.svc.cluster.local:8080/v1`
- on the LAN: `https://vllm.vanillax.me/v1`

The second 3090 remains available for another whole-card workload. GPU
time-slicing is disabled, and both the request and limit are exactly one GPU.

## Model and storage

The checkpoint is derived from the public
`dbirks/Qwen3.8-27B-W4A16-AutoRound` Hugging Face repository. It is already on
the TrueNAS `ai-pool/vllm` share as
`Qwen3.8-27B-W4A16-AutoRound-3090-int8lmhead` and is mounted read-only through
the NFS CSI driver. The existing 10 GbE NFS path is the repo's faster and more
appropriate tier for large sequential model reads; no Longhorn model PVC or
in-cluster download Job is needed.

The server uses the stock digest-pinned `vllm/vllm-openai:v0.27.1` image. There
is no custom image, runtime patch, or model-prep controller in this deployment.

## Serving profile

- 131,072-token request ceiling with FP8 KV cache
- `gpu-memory-utilization=0.90`
- 2-token stock MTP speculative decoding
- FP16 DeltaNet recurrent state
- 2,048-token chunked prefill
- `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`
- `--language-model-only`; use the parked llama.cpp backend when vision is needed
- Qwen3 reasoning and `qwen3_coder` tool-call parsers

Startup can take several minutes while torch.compile, CUDA graphs, and
FlashInfer initialize. The startup probe allows up to one hour; readiness is
served by `/health`.

## Verify after ArgoCD sync

```bash
kubectl -n vllm rollout status deploy/vllm-server --timeout=20m
kubectl -n vllm logs deploy/vllm-server | grep 'GPU KV cache size'
kubectl -n vllm port-forward svc/vllm-service 8080:8080
curl -s http://127.0.0.1:8080/v1/models | jq
curl -s http://127.0.0.1:8080/metrics \
  | grep 'spec_decode_num_accepted_tokens_total'
```

Run a benchmark twice after each restart; the first pass includes JIT warmup
and can read substantially low. Historical single-vs-dual measurements remain
under `benchmarks/ai-realworld-load/`.

## Rollback

Revert the Git commit and let ArgoCD sync. Do not use `kubectl edit` or
imperative scaling: ArgoCD self-heal will overwrite it. The model share uses a
Retain PV and is unaffected by a Deployment rollback.
