# vLLM — parked Qwen3.8-27B rollback

This ArgoCD-discovered app is retained at `replicas: 0` as a rollback backend.
The active `qwen3.8-27b` service is llama.cpp; no consumer or HTTPRoute points
at this Deployment.

- in cluster: `http://vllm-service.vllm.svc.cluster.local:8080/v1`
- no direct LAN route; `vllm.vanillax.me` is a compatibility hostname on the active llama.cpp route

The chassis has one RTX 3090. Scale llama.cpp to zero in the same commit before
restoring this Deployment to one replica.

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

The checkpoint is natively multimodal (`Qwen3_5ForConditionalGeneration`) and
includes its vision configuration and processor. The Deployment leaves the
vision tower enabled.

## Serving profile

- 65,536-token request ceiling with FP8 KV cache
- `gpu-memory-utilization=0.90`
- 2-token stock MTP speculative decoding
- FP16 DeltaNet recurrent state
- 2,048-token chunked prefill
- `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`
- vision enabled, limited to one image and no video per prompt
- Qwen3 reasoning and `qwen3_coder` tool-call parsers

The 65,536-token ceiling is the conservative one-card profile after restoring
the roughly 2.7 GiB vision tower. It is not a measured maximum. Read the cache
pool from the startup log and validate long-context plus image requests before
raising it. llama.cpp remains a parked GGUF alternative, not a prerequisite for
vision.

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

Also send an OpenAI-compatible chat request containing one base64 image and
confirm the response describes it. Requests with multiple images or video are
rejected intentionally by `--limit-mm-per-prompt`.

Run a benchmark twice after each restart; the first pass includes JIT warmup
and can read substantially low. Historical single-vs-dual measurements remain
under `benchmarks/ai-realworld-load/`.

## Rollback

Revert the Git commit and let ArgoCD sync. Do not use `kubectl edit` or
imperative scaling: ArgoCD self-heal will overwrite it. The model share uses a
Retain PV and is unaffected by a Deployment rollback.
