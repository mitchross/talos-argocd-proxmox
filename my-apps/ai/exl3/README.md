# Qwen3.8-27B EXL3 single-RTX-3090 experiment

Experimental sidecar for MiaAI-Lab's Qwen3.8-27B EXL3 3.5 bpw deployment kit and ExLlamaV3 fork.

This app is intentionally parked at `replicas: 0`. It must never run at the same time as the production `my-apps/ai/vllm` deployment because the GPU worker has one RTX 3090.

## First test

The initial profile follows MiaAI-Lab's documented 24 GB recipe:

- target: `Mia-AiLab/Qwen3.8-27B-EXL3-3.5bpw` (~14.2 GB)
- runtime: MiaAI-Lab ExLlamaV3 fork, pinned to commit `63b32f001d7b2cfed3b3e3aaf25f534ba53cc7ed`
- deployment kit: pinned to commit `09791b8a9045210cd2e90b49c13ffd3b34fb2d70`
- speculative decoding: MTP
- KV: NVFP4
- context: 262144
- GPU memory budget: 22 GB
- CUDA arch: 8.6 (RTX 3090 / Ampere)
- API: OpenAI-compatible server on port 8888

No DFlash2 on the first pass. Prove MTP + NVFP4 + 262K boot, output quality, tools, and long-context correctness before adding the 1.4 GB DFlash2 drafter.

## Safety / activation

Keep this app at zero replicas in normal operation.

To run the experiment through GitOps:

1. set `my-apps/ai/vllm/deployment.yaml` to `replicas: 0`
2. set `my-apps/ai/exl3/deployment.yaml` to `replicas: 1`
3. merge and let ArgoCD reconcile
4. use `exl3-qwen38.vllm.svc.cluster.local:8888` from inside the cluster, or port-forward the Service for direct testing

Reverse those replica changes to restore production vLLM.

## Storage / first boot

The pod reuses the existing `ai-model-cache-vllm` local-PV-backed PVC in namespace `vllm`, under `/models/exl3`. This avoids adding another Longhorn copy of the model. The first boot installs build dependencies, creates the Mia deployment kit venv, compiles the pinned ExLlamaV3 CUDA extension, and downloads the EXL3 weights. The venv and model files persist on the node-local NVMe cache.

## What to validate

Before considering this backend usable, compare it with production vLLM using the same prompts:

- normal chat with explicit reasoning levels
- Pi coding/agent loop
- tool-call correctness and multi-turn tool state
- long-context needle/retrieval at 64K, 128K, then 262K
- prefix/multi-turn behavior
- output quality versus the current W4A16 production quant
- decode tok/s, prefill tok/s, TTFT, VRAM and GPU errors

Vision is not assumed by this experiment until the Mia ExLlamaV3 OpenAI server path proves multimodal support for this checkpoint.

## Upstream

- deployment kit: https://github.com/MiaAI-Lab/Qwen3.8-27B-DFlash2-EXL3-5.0bpw
- engine fork: https://github.com/MiaAI-Lab/exllamav3
