# vLLM — parked Qwen3.8-27B rollback backend

vLLM is retained in Git and on the GPU-node NVMe cache, but **production is
`replicas: 0`**. Stock llama.cpp now owns the single RTX 3090 and serves the
canonical `qwen3.8-27b` API model.

The old DNS name `vllm-service.vllm.svc.cluster.local:8080` remains as an
`ExternalName` compatibility alias to `llama-cpp-service` so persistent clients
whose configuration lives outside Git do not break during the cutover.

The old `vllm.vanillax.me` HTTPRoute is not rendered by this Kustomization;
`my-apps/ai/llama-cpp/httproute.yaml` owns that hostname while llama.cpp is
production.

## Retained rollback shape

- stock `vllm/vllm-openai:v0.28.0`
- Qwen3.8-27B AutoRound W4A16 + INT8 lm_head + BF16 embeddings
- native vision
- 65,536 max model length
- fp8 E4M3 KV
- float16 DeltaNet recurrent state
- stock MTP with 2 speculative tokens
- explicit Qwen3 reasoning and tool parsers
- node-local NVMe model and compile caches

Nothing in the vLLM model/cache path is deleted by the llama.cpp cutover.

## Rollback

A rollback must be one GitOps change that:

1. sets `vllm-server=1` and `llama-cpp-server=0`,
2. restores `httproute.yaml` to the vLLM Kustomization and removes
   `vllm.vanillax.me` from the llama.cpp HTTPRoute,
3. changes `vllm-service` back from `ExternalName` to the vLLM selector Service,
4. repoints Git-managed consumers from `llama-cpp-service` to `vllm-service`.

Never run both whole-card deployments at one replica on the single RTX 3090.
