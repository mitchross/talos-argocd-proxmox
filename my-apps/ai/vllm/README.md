# vllm — scaffold (review + tune before relying on it)

OpenAI-compatible vLLM server for AWQ/compressed-tensors models, TP=2 across both 3090s.
Auto-discovered by the `my-apps/*/*` ApplicationSet → ArgoCD Application `my-apps-vllm`, namespace `vllm`.

**Models** (already on NFS `ai-pool/vllm`, mounted RO at `/models`):
- `Qwen3.6-27B-AWQ-INT4` (primary, 20 GB) · `Qwen3.6-27B-AWQ-BF16-INT4` (25 GB, fits via TP=2)

**Why `replicas: 0`:** steady state is GPU0=llama-cpp, GPU1=comfyui. vLLM TP=2 needs BOTH cards, so it's
a deliberate burst mode. To run:
```
kubectl scale deploy/llama-cpp-server -n llama-cpp --replicas=0
kubectl scale deploy/comfyui          -n comfyui   --replicas=0   # if running
kubectl scale deploy/vllm-server      -n vllm      --replicas=1
```
Reverse to restore the default split. Then: `curl -s https://vllm.vanillax.me/v1/models | jq`.

**Before first deploy — TODO:**
- Pin `image: vllm/vllm-openai:<tag>` to a version that supports the Qwen3.6/Qwen3-VL arch (currently `latest`).
- Confirm `nvidia.com/gpu: "2"` resolves to 2 whole physical cards (time-slicing is disabled — it should).
- Tune `--max-model-len` against club-3090 `docs/CLIFFS.md` (vLLM memory cliffs).

Full rationale + connection/creds/storage details: `~/nas-setup/VLLM-DEPLOY-BRIEF.md`
(also `\\192.168.10.133\General\homelab-docs\VLLM-DEPLOY-BRIEF.md`).
