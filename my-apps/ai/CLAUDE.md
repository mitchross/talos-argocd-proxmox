# AI / GPU Workload Guidelines

## LLM Backend

One active OpenAI-compatible local backend, **NOT ollama**:

### llama.cpp — active, single card
- Endpoint: `http://llama-cpp-service.llama-cpp.svc.cluster.local:8080/v1`
- Served API model: **`qwen3.8-27b`** — temporary compatibility alias for
  Qwen3.8-Flash-Next UD-Q4_K_XL with F16 vision and symmetric q8_0 KV at 131K
  on **one** RTX 3090.
- **Use llama.cpp / `qwen3.8-27b` when wiring an in-cluster app to chat inference.**

### vLLM — parked rollback
- `replicas: 0`; do not point consumers at `vllm-service` while parked.

All in-cluster consumers request `qwen3.8-27b`, including Karakeep text and
image inference. ComfyUI's dedicated llama.cpp-client workflow also uses this
active Service.

**App→backend wiring + capacity rules:
[`model-catalog.md`](../../docs/domains/ai-gpu/model-catalog.md) ·
[`single-vs-dual-3090.md`](../../docs/domains/ai-gpu/single-vs-dual-3090.md).**

### Gotchas (see `docs/domains/ai-gpu/3090-llm-optimization.md` for full rationale)
- **KV cache must be SYMMETRIC** — `q8_0/q8_0` or `q4_0/q4_0`, never mixed.
  Asymmetric KV falls to CPU, 44x slower ([llama.cpp #20866]). Overrides the
  Qwen3-Coder docs' q8-K/q4-V suggestion.
- **Context limit = `min(model max, VRAM-affordable KV)`.** The live profile
  allocates 131072 tokens with q8_0 KV and vision; confirm `n_ctx_slot` and loaded
  VRAM after every restart. Historical vLLM measurements are in
  [`single-vs-dual-3090.md`](../../docs/domains/ai-gpu/single-vs-dual-3090.md).
- **Local = unlimited token *volume* (free), not an infinite *window* per request.**
- **Engine choice:** Qwen3.8-Flash-Next runs on a pinned post-merge llama.cpp
  qwen4exp build via UD-Q4_K_XL GGUF and the F16 projector. The stock-vLLM
  W4A16 deployment is a parked rollback.
- **MTP stays off for Flash-Next.** The merged qwen4exp implementation did not
  include the final Flash-Next MTP path.
- **PLE stays lazy and mmap-backed.** Do not add mlock or disable
  `--tensor-read-lazy`; the 100 GiB Talos VM cannot hold the Q4 model resident.
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

- **Current state:** llama-cpp `replicas: 1` holding the **sole** card; vLLM,
  ComfyUI and SwarmUI are `0`.
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
