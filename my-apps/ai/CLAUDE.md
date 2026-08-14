# AI / GPU Workload Guidelines

## LLM Backend

Two OpenAI-compatible local backends, **NEITHER is ollama**:

### vLLM — normal app backend, temporarily parked
- Endpoint: `http://vllm-service.vllm.svc.cluster.local:8080/v1`
- Served model: **`qwen3.6-27b`** (Qwen3.6-27B dense AWQ, multimodal/vision)
- `replicas: 0` during the Qwen 3.8 GGUF evaluation; do not scale or reconfigure it unless ending the evaluation.
- Perplexica, Project NOMAD, Karakeep, and the other normal consumers still point here and are unavailable while it is parked.
- **Use vLLM / `qwen3.6-27b` when wiring an in-cluster app to chat/vision inference.**

### llama-cpp — current Qwen 3.8 evaluation backend
- Endpoint: `http://llama-cpp-service.llama-cpp.svc.cluster.local:8080/v1`
- Serves **Qwen3.8-27B** `UD-Q4_K_XL.gguf` plus its BF16 vision projector.
- Advertises only `qwen3.8` and `qwen3.8-nothink`; both use the same weights.
- OpenWebUI points here during the evaluation. Chat/vision use `qwen3.8`; strict
  title/tag tasks use `qwen3.8-nothink`.
- **Models swap natively** via `llama-server --models-preset` — no external
  `llama-swap` needed. `--models-max 1` = one resident at a time.

**App→backend wiring table + what each model is / when to use it:
[`docs/domains/ai-gpu/model-catalog.md`](../../docs/domains/ai-gpu/model-catalog.md).**

### Gotchas (see `docs/domains/ai-gpu/3090-llm-optimization.md` for full rationale)
- **KV cache must be SYMMETRIC** — `q8_0/q8_0` or `q4_0/q4_0`, never mixed.
  Asymmetric KV falls to CPU, 44x slower ([llama.cpp #20866]). Overrides the
  Qwen3-Coder docs' q8-K/q4-V suggestion.
- **Context limit = `min(model max, VRAM-affordable KV)`.** Qwen3.8 model max is
  256K; a single 3090 only *affords* ~64K of KV after weights. Pool both 3090s
  (48GB) for resident 256K. CPU expert-offload is a last resort on this
  Broadwell/DDR4 node (memory-bandwidth-bound, ~8-12 TPS).
- **Local = unlimited token *volume* (free), not an infinite *window* per request.**
- **Engine tradeoff:** Qwen 3.8 has no Ampere-usable vLLM AWQ quant yet, so the
  evaluation uses llama.cpp GGUF. Keep the proven Qwen 3.6 AWQ vLLM deployment
  parked and unchanged so it can be restored after the evaluation.
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

The production AI workloads are pinned to the existing `gpu-worker=true`
label. The Wi-Fi Dell worker is CPU-only and deliberately does not carry that
label, so it cannot receive these 24/48-GiB model workloads.

- **Current state:** vLLM `replicas: 0`; llama-cpp `1`; ComfyUI and SwarmUI `0`.
  (Current, not permanent — flip the committed replica counts to swap which
  workload owns the cards. Full procedure + card truth table:
  [`docs/domains/ai-gpu/gpu-scale-swap.md`](../../docs/domains/ai-gpu/gpu-scale-swap.md).)
- Time-slicing is DISABLED (`time-slicing-config.yaml` has no sharing block) so
  whole-card allocation is enforced. Don't set `NVIDIA_VISIBLE_DEVICES` or
  `CUDA_VISIBLE_DEVICES` in pod env — they override the device-plugin's CDI
  injection. (Sole exception: the infrastructure `nvidia-powerlimit` admin
  DaemonSet, which must see all cards without consuming a `nvidia.com/gpu`
  allocation.)
- **Both 3090s are power-capped at 200W** by
  `infrastructure/controllers/nvidia-gpu-operator/powerlimit-daemonset.yaml`.
  This is a **house-circuit constraint, not an efficiency choice**: at the
  previous 290W cap the Threadripper box drew ~900W at the wall and basement
  lights flickered. 290W is the measured efficiency knee and 200W is below it
  (club-3090 measures ~16% worse efficiency at 230W than 290W), so this
  deliberately trades throughput for electrical headroom. Don't raise it back
  toward 290W without confirming the circuit; don't "fix" a perceived slowdown
  by deleting the cap.

## GPU Workload Pattern

Reference `my-apps/ai/comfyui/` for complete example:

```yaml
spec:
  template:
    spec:
      # Select GPU nodes
      nodeSelector:
        feature.node.kubernetes.io/pci-0300_10de.present: "true"
        gpu-worker: "true"

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
