# vllm — default app-inference backend

OpenAI-compatible vLLM server for AWQ/compressed-tensors models, TP=2 across both 3090s.
Auto-discovered by the `my-apps/*/*` ApplicationSet → ArgoCD Application `my-apps-vllm`, namespace `vllm`.

**This is the normal backend for in-cluster app inference** (served model `qwen3.6-27b`).
It is temporarily parked at `replicas: 0` while OpenWebUI evaluates Qwen 3.8-27B GGUF on
llama.cpp. Other consumers still point here and remain unavailable during the evaluation.
Do not change this deployment or its NFS weights until the evaluation ends.

**Models** (already on NFS `ai-pool/vllm`, mounted RO at `/models`):
- `Qwen3.6-27B-AWQ-INT4` (primary, 20 GB) · `Qwen3.6-27B-AWQ-BF16-INT4` (25 GB, fits via TP=2)

**GPU topology — mutually-exclusive whole-card, scale-swap.** The three GPU workloads (vLLM,
llama-cpp, ComfyUI) are whole-card and `type: Recreate` with time-slicing disabled — never two on
the cards at once. Bringing one up means scaling the others to `replicas: 0`. vLLM TP=2 pools BOTH
3090s, so when it runs nothing else can.

**Current evaluation state:** vLLM is scaled down (`replicas: 0`) and llama-cpp is at `1`.
To restore vLLM, commit llama-cpp `replicas: 0`, vLLM `replicas: 1`, and the
OpenWebUI endpoint/model reversal together. ArgoCD self-heal makes imperative
`kubectl scale` unsuitable for the handoff. Then verify:
`curl -s https://vllm.vanillax.me/v1/models | jq`.

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
