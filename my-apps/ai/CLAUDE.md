# AI / GPU Workload Guidelines

## LLM Backend

Two OpenAI-compatible local backends, **NEITHER is ollama**:

### vLLM — DEFAULT for app inference
- Endpoint: `http://vllm-service.vllm.svc.cluster.local:8080/v1`
- Served model: **`qwen3.6-27b`** (Qwen3.6-27B dense AWQ, multimodal/vision)
- OpenWebUI, Perplexica, Project NOMAD, and Karakeep all point here.
- **Use vLLM / `qwen3.6-27b` when wiring an in-cluster app to chat/vision inference.**

### llama-cpp — multi-preset playground + ComfyUI vision
- Endpoint: `http://llama-cpp-service.llama-cpp.svc.cluster.local:8080/v1`
- Serves **Qwen3.6-35B-A3B** MoE (Unsloth UD-Q4_K_XL + `mmproj-BF16.gguf`)
  plus Gemma 4 and Qwen 3.5 Uncensored as selectable presets (aliases
  `qwen3.6` / `qwen3.6-nothink` / `qwen3.6-longctx` / `gemma4*` / `uncensored`;
  see `my-apps/ai/llama-cpp/presets.ini`).
- Kept for **ComfyUI's vision→image workflow** and manual/interactive
  multi-preset use. App traffic no longer depends on these presets.
- Creative-only toy: Qwen 3.5 Uncensored — **keep abliterated models OUT of
  Perplexica / RAG / tool-calling** (abliteration degrades accuracy).
- **Models swap natively** via `llama-server --models-preset` — no external
  `llama-swap` needed. `--models-max 1` = one resident at a time.

**App→backend wiring table + what each model is / when to use it:
[`docs/domains/ai-gpu/model-catalog.md`](../../docs/domains/ai-gpu/model-catalog.md).**

### Gotchas (see `docs/domains/ai-gpu/3090-llm-optimization.md` for full rationale)
- **KV cache must be SYMMETRIC** — `q8_0/q8_0` or `q4_0/q4_0`, never mixed.
  Asymmetric KV falls to CPU, 44x slower ([llama.cpp #20866]). Overrides the
  Qwen3-Coder docs' q8-K/q4-V suggestion.
- **Context limit = `min(model max, VRAM-affordable KV)`.** Qwen3.6 model max is
  256K; a single 3090 only *affords* ~64K of KV after weights. Pool both 3090s
  (48GB) for resident 256K. CPU expert-offload is a last resort on this
  Broadwell/DDR4 node (memory-bandwidth-bound, ~8-12 TPS).
- **Local = unlimited token *volume* (free), not an infinite *window* per request.**
- **Engine tradeoff (single-card vs pooled).** Same-hw benchmarks: vLLM ≈7x slower on a
  single 3090 for the 35B GGUF MoE (AWQ weights starve the card → eager mode), which is
  why llama-cpp serves the GGUF preset bank. vLLM wins at TP=2 (dual-card pooled) and is
  the **default app backend** serving the `qwen3.6-27b` dense AWQ build.
  `ik_llama.cpp` is the more relevant single-card speedup for the llama-cpp side.
- **MTP/spec-decode gives NO net speedup** on Ampere + 35B-A3B under llama.cpp
  (same-hw benchmark) — only helps under vLLM TP=2. Don't bother on single-card.
- **TurboQuant `turbo3` KV** (≈5x smaller) is coming to mainline llama.cpp
  (PR #21089) — adopt it then for cheap big context.

[llama.cpp #20866]: https://github.com/ggml-org/llama.cpp/issues/20866

## GPU Topology

GPU workloads (vLLM, llama-cpp, ComfyUI) are **mutually-exclusive whole-card**
(`type: Recreate`, time-slicing disabled) — **NEVER two pods on the cards at
once**. They **scale-swap**: bringing one up means scaling the others to
`replicas: 0`.

- **Current state:** vLLM `replicas: 1`; llama-cpp and ComfyUI at `0`.
  (Current, not permanent — flip the replica counts to swap which workload owns
  the cards.)
- Time-slicing is DISABLED (`time-slicing-config.yaml` has no sharing block) so
  whole-card allocation is enforced. Don't set `NVIDIA_VISIBLE_DEVICES` or
  `CUDA_VISIBLE_DEVICES` in pod env — they override the device-plugin's CDI
  injection. (Sole exception: the `gpu-power-limit` admin DaemonSet, which must
  see all cards without consuming a `nvidia.com/gpu` allocation.)
- **Both 3090s are power-capped at 290W** by `my-apps/ai/gpu-power-limit/`
  (measured efficiency knee: −22% power for −7% decode TPS — see the power
  section of `docs/domains/ai-gpu/3090-llm-optimization.md`). Don't "fix" a
  perceived slowdown by deleting the cap; tune `POWER_LIMIT_WATTS` instead.

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
