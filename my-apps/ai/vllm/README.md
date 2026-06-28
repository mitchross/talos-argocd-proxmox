# vllm — default app-inference backend

OpenAI-compatible vLLM server for AWQ/compressed-tensors models, TP=2 across both 3090s.
Auto-discovered by the `my-apps/*/*` ApplicationSet → ArgoCD Application `my-apps-vllm`, namespace `vllm`.

**This is the current default backend for in-cluster app inference** (served model `qwen3.6-27b`).
OpenWebUI, Perplexica/Vane, Project NOMAD, and Karakeep all point here. See the authoritative
app→backend table in `docs/domains/ai-gpu/model-catalog.md`.

**Models** (already on NFS `ai-pool/vllm`, mounted RO at `/models`):
- `Qwen3.6-27B-AWQ-INT4` (primary, 20 GB) · `Qwen3.6-27B-AWQ-BF16-INT4` (25 GB, fits via TP=2)

**GPU topology — mutually-exclusive whole-card, scale-swap.** The three GPU workloads (vLLM,
llama-cpp, ComfyUI) are whole-card and `type: Recreate` with time-slicing disabled — never two on
the cards at once. Bringing one up means scaling the others to `replicas: 0`. vLLM TP=2 pools BOTH
3090s, so when it runs nothing else can.

**Current/default state:** vLLM is scaled up (`replicas: 1`) with llama-cpp and ComfyUI at `0`.
To swap a different workload in, scale vLLM down and the target up — for example, to bring back
llama-cpp (kept for ComfyUI's vision→image workflow and manual multi-preset use):
```
kubectl scale deploy/vllm-server      -n vllm      --replicas=0
kubectl scale deploy/llama-cpp-server -n llama-cpp --replicas=1   # and/or comfyui
```
Reverse to restore vLLM as the default. Then: `curl -s https://vllm.vanillax.me/v1/models | jq`.

**Tuning TODO:**
- Pin `image: vllm/vllm-openai:<tag>` to a version that supports the Qwen3.6/Qwen3-VL arch (currently `latest`).
- Confirm `nvidia.com/gpu: "2"` resolves to 2 whole physical cards (time-slicing is disabled — it should).
- Tune `--max-model-len` against club-3090 `docs/CLIFFS.md` (vLLM memory cliffs).

Full rationale + connection/creds/storage details: `~/nas-setup/VLLM-DEPLOY-BRIEF.md`
(also `\\192.168.10.133\General\homelab-docs\VLLM-DEPLOY-BRIEF.md`).

## OpenCode configuration

The global OpenCode config is `~/.config/opencode/opencode.json` on macOS and
Linux. The following is JSONC-compatible syntax but remains valid JSON:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "model": "vllm/qwen3.6-27b",
  "provider": {
    "vllm": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Homelab vLLM",
      "options": {
        "baseURL": "https://vllm.vanillax.me/v1"
      },
      "models": {
        "qwen3.6-27b": {
          "name": "Qwen3.6 27B (vLLM)",
          "limit": {
            "context": 262144,
            "output": 32768
          }
        }
      }
    }
  }
}
```
