# AI / GPU Workload Guidelines

## LLM Backend

This cluster uses **llama-cpp** (NOT ollama) for all local AI inference.
- Endpoint: `http://llama-cpp-service.llama-cpp.svc.cluster.local:8080`
- OpenAI-compatible API at `/v1`
- Primary model: **Qwen3.6-35B-A3B** (Unsloth UD-Q4_K_XL, multimodal via `mmproj-BF16.gguf`)
- Fallbacks: Gemma 4 26B-A4B / 31B (multimodal)
- Staged (need GGUF on NFS): **Qwen3-Coder-30B-A3B** (coding agent),
  **WhiteRabbitNeo v2.5** (authorized security learning, isolated preset),
  **Qwen3-4B/8B FC** (fast n8n tool-calling)
- Creative-only toy: Qwen 3.5 Uncensored — **keep abliterated models OUT of
  Perplexica / RAG / tool-calling** (abliteration degrades accuracy)
- Full preset list (model IDs clients send in the `model` field): `my-apps/ai/llama-cpp/presets.ini`
- **Models swap natively** via `llama-server --models-preset` — no external
  `llama-swap` needed. `--models-max 1` = one resident at a time.

Always use llama-cpp when configuring AI backends for in-cluster tools.

### Gotchas (see `docs/3090-llm-optimization.md` for full rationale)
- **KV cache must be SYMMETRIC** — `q8_0/q8_0` or `q4_0/q4_0`, never mixed.
  Asymmetric KV falls to CPU, 44x slower ([llama.cpp #20866]). Overrides the
  Qwen3-Coder docs' q8-K/q4-V suggestion.
- **Context limit = `min(model max, VRAM-affordable KV)`.** Qwen3.6 model max is
  256K; a single 3090 only *affords* ~64K of KV after weights. Pool both 3090s
  (48GB) for resident 256K. CPU expert-offload is a last resort on this
  Broadwell/DDR4 node (memory-bandwidth-bound, ~8-12 TPS).
- **Local = unlimited token *volume* (free), not an infinite *window* per request.**
- **Engine: llama.cpp, not vLLM.** Same-hw benchmarks: vLLM ≈7x slower on a
  single 3090 for this MoE (AWQ weights starve the card → eager mode); our library
  is all GGUF. vLLM only wins at TP=2 (dual-card pooled) — the one optional
  big-context endpoint. `ik_llama.cpp` is the more relevant single-card speedup.
- **MTP/spec-decode gives NO net speedup** on Ampere + 35B-A3B under llama.cpp
  (same-hw benchmark) — only helps under vLLM TP=2. Don't bother on single-card.
- **TurboQuant `turbo3` KV** (≈5x smaller) is coming to mainline llama.cpp
  (PR #21089) — adopt it then for cheap big context.

[llama.cpp #20866]: https://github.com/ggml-org/llama.cpp/issues/20866

## GPU Topology

Two RTX 3090s (24 GB each), dedicated split — one pod per card:
- **GPU 0 → llama-cpp** (always-on, serves every AI-using app)
- **GPU 1 → ComfyUI** (bursty, needs whole card for Wan 2.2 / Qwen-Image-Edit)

Time-slicing is DISABLED (`time-slicing-config.yaml` has no sharing block)
so the node advertises `nvidia.com/gpu: 2` and whole-card allocation is
enforced. Don't set `NVIDIA_VISIBLE_DEVICES` or `CUDA_VISIBLE_DEVICES`
in pod env — they override the device-plugin's CDI injection and steer
the workload onto the wrong card.

## GPU Workload Pattern

Reference `my-apps/ai/comfyui/` for complete example:

```yaml
spec:
  template:
    spec:
      # Select GPU nodes
      nodeSelector:
        feature.node.kubernetes.io/pci-0300_10de.present: "true"

      # NVIDIA runtime for CUDA
      runtimeClassName: nvidia

      # Priority to prevent eviction
      priorityClassName: gpu-workload-preemptible

      # Allow scheduling on GPU nodes
      tolerations:
      - key: nvidia.com/gpu
        operator: Exists
        effect: NoSchedule

      containers:
      - name: app
        resources:
          requests:
            nvidia.com/gpu: "1"
          limits:
            nvidia.com/gpu: "1"
```

**GPU node is reserved for LLM RAM** — do not schedule Longhorn replicas or non-GPU workloads there.

## Debugging GPU

```bash
# Verify GPU nodes are labeled
kubectl get nodes -o json | jq '.items[].metadata.labels' | grep gpu

# Check NVIDIA GPU Operator
kubectl get pods -n gpu-operator

# Test GPU from pod
kubectl exec -it gpu-pod -n app-name -- nvidia-smi
```
