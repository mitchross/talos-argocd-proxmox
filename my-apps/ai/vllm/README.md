# vLLM: Qwen3.8-27B on two RTX 3090s

vLLM runs one Qwen3.8-27B model on both 3090s. Every app reaches it as `qwen3.8-27b`.

## Switch models

1. Open `kustomization.yaml`.
2. Under `components:`, comment out the `ON` line and uncomment the model you want.
3. Open a PR and merge it.

ArgoCD then downloads and verifies the new model, copies it to the GPU node, and restarts vLLM.
Apps need no change. Two active lines fail the build on purpose.

| Folder in `models/` | Model | Notes |
|---|---|---|
| `frozenlock-qwen3.8-27b-int4-autoround` | [INT4 AutoRound](https://huggingface.co/Frozenlock/Qwen3.8-27B-int4-AutoRound) | Default. 19 GB. Fastest. |
| `qwen-qwen3.8-27b-fp8` | [Official FP8](https://huggingface.co/Qwen/Qwen3.8-27B-FP8) | Rollback. 29 GB. |
| `huihui-qwen3.8-27b-abliterated-fp8` | [Abliterated FP8](https://huggingface.co/munekazu/Huihui-Qwen3.8-27B-abliterated-FP8) | Uncensored. 31 GB. Not booted on this image yet. |

To add a model, copy a folder. Then pin the new repo revision and file checksums in its `manifest-patch.yaml`.

## How to reach it

- Apps: LiteLLM at `http://litellm-service.litellm.svc.cluster.local:4000/v1`. Telemetry needs this path.
- Diagnostics only: `http://vllm-service.vllm.svc.cluster.local:8080/v1`, `https://vllm.vanillax.me/v1` or `https://llama.vanillax.me/v1`.

Gateway wiring: [model catalog](../../../docs/domains/ai-gpu/model-catalog.md).

## Settings that bite

| Setting | Value | Why |
|---|---|---|
| GPU memory | `0.90` | At startup, the log must show at least 262,144 KV tokens. Otherwise, raise it to `0.92` in Git. Never cut context. |
| Context | 262,144 tokens | This is the native limit. Going past it needs YaRN; do not enable it. |
| Slots | 16 | The KV pool, not the slot count, limits real load. |
| Attention | FlashInfer | Triton rejects FP8 KV cache on 3090s. |
| Speculation / MTP | off | Long sessions crash it (vLLM #50021). Turn it on only after a long-session test passes. |
| INT4 activations | `VLLM_HUMMING_INPUT_QUANT_CONFIG={"dtype":"int8"}` | The boot log must show `[humming-w4a8] effective activations a_dtype=int8`. |
| `VLLM_MARLIN_INPUT_DTYPE` | never set | vLLM v0.34 refuses to start with it. |
| Power | 200 W per card | Do not raise it. |

The image is `ghcr.io/mitchross/vllm-qwen38-dualfast`, built in homelab-images.
Its fixes and the reasoning template are baked in, and nothing patches at boot.

## Thinking

The server thinks by default at `xhigh` effort, with a 16,384-token cap. The cap stops Qwen from overthinking.

| Client sends in `chat_template_kwargs` | Result |
|---|---|
| nothing | thinking, `xhigh` |
| `{"enable_thinking":true,"reasoning_effort":"low"}` | short thinking (4,096 cap) |
| `{"enable_thinking":true,"reasoning_effort":"medium"}` | thinking (16,384 cap) |
| `{"enable_thinking":false,"preserve_thinking":false}` | no thinking. Also send the off sampler below. |

| Sampler | Thinking | Off |
|---|---:|---:|
| `temperature` | 1.0 | 0.7 |
| `top_p` | 0.95 | 0.8 |
| `top_k` | 20 | 20 |
| `min_p` | 0.0 | 0.0 |
| `presence_penalty` | 0.0 | 1.5 |
| `repetition_penalty` | 1.05 | 1.0 |

The thinking switch alone does not change the sampler, so send all six "off" values.
When you change `repetition_penalty`, change the server, Open WebUI and Pi together.
The Pi setup lives in the [Pi guide](../../../docs/domains/ai-gpu/pi-agent-local-dev.md).

## How the model reaches the GPU

1. A download Job saves the pinned files to the NAS (`192.168.10.133:/mnt/ai-pool/vllm`). It checks each file's size and SHA-256.
2. A cache-sync Job copies them to the GPU node's NVMe. It then writes `.verified-manifest`.
3. vLLM waits for that marker, then loads the model from local disk, offline.

Later syncs skip the re-check while the marker matches. To force a full re-check, delete `.verified-manifest` and sync.
Nothing is ever pruned, so old models stay on the NAS and NVMe.

## Check it works

```bash
kubectl -n vllm get jobs,pods
kubectl -n vllm logs deploy/vllm-server --tail=200   # look for the KV token count and the humming line
kubectl -n vllm port-forward svc/vllm-service 18000:8080
curl -fsS http://127.0.0.1:18000/v1/models
curl -fsS http://127.0.0.1:18000/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"model":"qwen3.8-27b","messages":[{"role":"user","content":"What is 19 + 23?"}],"max_tokens":64,"chat_template_kwargs":{"enable_thinking":false,"preserve_thinking":false}}'
```

Expect `42`. Then try one image, one tool call and each thinking mode.
Stop if you see a hash failure, too few KV tokens, OOM or Xid errors, or broken tool or image output.
Do not turn on MTP to fix a failing setup.

Capacity history: [3090 LLM optimization](../../../docs/domains/ai-gpu/3090-llm-optimization.md).
