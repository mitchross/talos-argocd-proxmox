# vLLM — Qwen3.8-27B on one RTX 3090

The active OpenAI-compatible chat, tool, and vision backend. Every in-cluster
consumer points here.

- in cluster: `http://vllm-service.vllm.svc.cluster.local:8080/v1`
- on the LAN: `https://vllm.vanillax.me/v1`
- API model: `qwen3.8-27b`

The chassis has one RTX 3090. llama.cpp is the parked GGUF rollback at
`replicas: 0`; scale it up only in the same commit that scales this to zero.

## Model and storage

The checkpoint is derived from the public
`dbirks/Qwen3.8-27B-W4A16-AutoRound` Hugging Face repository. It is already on
the TrueNAS `ai-pool/vllm` share as
`Qwen3.8-27B-W4A16-AutoRound-3090-int8lmhead` and is mounted read-only through
the NFS CSI driver. The existing 10 GbE NFS path is the repo's faster and more
appropriate tier for large sequential model reads; no Longhorn model PVC or
in-cluster download Job is needed.

The server uses the stock digest-pinned `vllm/vllm-openai:v0.28.0` image. There
is no custom image, runtime patch, or model-prep controller in this deployment.

Unsloth publishes no 4-bit checkpoint that runs here: their only vLLM-servable
Qwen3.8-27B is NVFP4, which needs Blackwell tensor cores, and the 3090 is
Ampere. Their Q4 line for this model is GGUF, i.e. the parked llama.cpp path.

The checkpoint is natively multimodal (`Qwen3_5ForConditionalGeneration`) and
includes its vision configuration and processor. The Deployment leaves the
vision tower enabled.

## Serving profile

- 65,536-token request ceiling with FP8 KV cache
- `gpu-memory-utilization=0.93`
- 2-token stock MTP speculative decoding
- FP16 DeltaNet recurrent state
- 2,048-token chunked prefill
- `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`
- vision enabled, limited to one image and no video per prompt
- Qwen3 reasoning and `qwen3_coder` tool-call parsers

The 65,536-token ceiling is the conservative one-card profile after restoring
the roughly 2.7 GiB vision tower. It is not a measured maximum. Read the cache
pool from the startup log and validate long-context plus image requests before
raising it.

`CONTEXT_WINDOW` in `my-apps/ai/open-webui/open-webui-configmap.env` must track
this number — if it is larger, Open WebUI overruns the server's ceiling.

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
