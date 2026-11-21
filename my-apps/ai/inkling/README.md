# Inkling 2 Mini on both RTX 3090s (parked)

[Inkling 2 Mini](https://huggingface.co/thinkingmachines/Inkling-2-Mini) is
Thinking Machines' mixture-of-experts model (128 experts, 8 active, about 1.8B
parameters each, trained to 1,048,576 tokens of context). This app serves it
with mainline [llama.cpp](https://github.com/ggml-org/llama.cpp) `llama-server`
on both cards, split by layers, so it can be benchmarked against the live
Qwen3.8-27B on vLLM (`../vllm/`). Context length is the main question.

It is **parked** (`replicas: 0` in `kustomization.yaml`): vLLM owns both cards.
The model download still runs at every Argo sync, so the file is ready before
a swap.

| Setting | Value |
|---|---|
| Image | `ghcr.io/mitchross/llama-cpp:b12611-sm86`, built in mitchross/homelab-images. It must contain [ggml-org/llama.cpp#32704](https://github.com/ggml-org/llama.cpp/pull/32704) (first release `b12611`), or the output is gibberish |
| Model | [`unsloth/Inkling-2-Mini-GGUF`](https://huggingface.co/unsloth/Inkling-2-Mini-GGUF) at `ae9327c5fbc7333116ba32eee78bb5d2bbefae4f`, file `Mainline_Support/Inkling-2-Mini-UD-Q8_K_XL.gguf_file`, saved as `.gguf` |
| Precision | UD-Q8_K_XL: the original NVFP4 experts and BF16 for the rest, so no quality loss against the release weights |
| File | 22,867,452,896 bytes (21.3 GiB), sha256 `2da51788d43a17e1f033bec420fa83ba9cb87ac1f0130dc9135a4d2ed2678b68` |
| Disk | `inkling/` on the node-local NVMe `/var/mnt/ai-model-cache` |
| API | OpenAI-compatible, `http://inkling-service.inkling.svc.cluster.local:8080/v1`, model `inkling-2-mini`, no key |
| GPUs | 2 × RTX 3090 (`nvidia.com/gpu: 2`) at the usual 200 W cap |

Use only the `Mainline_Support/` files. The files at the repo root use
Unsloth's own layout and need Unsloth's llama.cpp fork.

## Start-up

1. `inkling-download-model` (an Argo Sync hook, CPU only, on the GPU node)
   downloads the pinned file to `inkling/Inkling-2-Mini-GGUF-ae9327c5fbc7/`,
   checks its size and sha256 and writes `.verified-manifest`. When the marker
   already matches it exits at once. An interrupted download resumes.
2. The server pod's `wait-for-model` init container waits for that marker.
3. `llama-server` loads the model. `/health` answers 503 while loading and 200
   once it serves.

## Swap the cards

Follow the [GPU scale-swap runbook](../../../docs/domains/ai-gpu/gpu-scale-swap.md):
in one commit set `inkling-server` to `count: 1` here and `vllm-server` to
`count: 0` in `../vllm/kustomization.yaml`. Every LLM client loses its local
backend while vLLM is parked; LiteLLM has no route to Inkling.

## Flags

| Flag | Why |
|---|---|
| `-m …/Inkling-2-Mini-UD-Q8_K_XL.gguf` | the lossless mainline-layout file |
| `--alias inkling-2-mini` | model name in the API |
| `--host 0.0.0.0 --port 8080` | the Service's target port |
| `-ngl 99 --split-mode layer` | every layer on the GPUs, whole layers per card |
| `--fit off` | keep `-c` and `-ngl` as written; if they do not fit, the load fails instead of a smaller context |
| `-fa on` | flash attention |
| `-c 262144` | same window as Qwen on vLLM |
| `-ub 128` | see memory below; smaller than the default 512 at some prefill cost |
| `-ctk f16 -ctv f16` | full-precision KV cache, no loss |
| `--parallel 1` | one request at a time |
| `--jinja` | use the chat template inside the GGUF (same as Thinking Machines' `chat_template.jinja`) |
| `--metrics` | Prometheus text at `/metrics` (`llamacpp:*` names) |
| `--temp 1.0 --top-p 1.0 --top-k 0 --min-p 0.0` | Thinking Machines / Unsloth recommendation |

Every flag was checked against `common/arg.cpp` at `b12611`.

## Memory (estimate, not measured)

Weights 21.3 GiB, f16 KV about 8.4 GiB at 256K, and the relative-position bias
about 6.4 GB: about 37 GiB of the 48 GiB on both cards. llama.cpp builds that
bias as a full fp32 table, 2 × 24 heads × context × ubatch × 4 bytes, so it
grows with both context and `-ub` ([estimate](https://vramcalculator.com/inkling-2-mini-vram/)).
Check the load log for the real numbers before trusting these.

To try more context, raise `-c` towards 524288 or 1048576 and lower `-ub` (64,
then 32) to keep the bias table down. If that still does not fit, switch the
KV cache to `-ctk q8_0 -ctv q8_0`, which halves it but is no longer lossless.
Record the setting with every benchmark result.

## Thinking

The chat template reads only `reasoning_effort`: `none` gives "Thinking effort
level: 0", unset gives 0.9, and `minimal` to `max` map between. Send it as
`chat_template_kwargs: {"reasoning_effort": "none"}`. A top-level
`reasoning_effort: "none"` does not reach the template in llama-server (the
server removes it), and `enable_thinking` is ignored by this template.

## Known limits

- No DSpark speculative decoding: mainline llama.cpp does not support the
  drafter yet ([#32218](https://github.com/ggml-org/llama.cpp/pull/32218)).
- No images: the vision projector (`mmproj-F16.gguf`) is not downloaded or
  loaded.
- One request at a time (`--parallel 1`); others queue.
- Not routed through LiteLLM and no HTTPRoute; reach it in the cluster only.
