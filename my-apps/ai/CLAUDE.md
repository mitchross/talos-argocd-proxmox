# AI / GPU Workload Guidelines

## LLM Backend

One active OpenAI-compatible local backend, **NOT ollama**:

### vLLM — active, single card
- Endpoint: `http://vllm-service.vllm.svc.cluster.local:8080/v1`
- Served API model: **`qwen3.8-27b`** — the dense Qwen3.8-27B AutoRound W4A16
  checkpoint with native vision, fp8 KV at 64K, and 2-token MTP on **one**
  RTX 3090.
- **Use vLLM / `qwen3.8-27b` when wiring an in-cluster app to chat inference.**

### llama.cpp — parked rollback
- `replicas: 0`; do not point consumers at `llama-cpp-service` while parked.

`Qwen3.8-Flash-Next Q4` is the parked llama.cpp GGUF's id, a separate model —
do not use it as a `qwen3.8-27b` alias.

**No Unsloth quant is servable here.** Unsloth's only vLLM-ready Qwen3.8-27B is
NVFP4, which needs Blackwell tensor cores; the 3090 is Ampere. Their Q4 line for
this model is GGUF, i.e. the parked llama.cpp path.

**App→backend wiring + capacity rules:
[`model-catalog.md`](../../docs/domains/ai-gpu/model-catalog.md) ·
[`single-vs-dual-3090.md`](../../docs/domains/ai-gpu/single-vs-dual-3090.md).**

### Gotchas — parked llama.cpp path (see `docs/domains/ai-gpu/3090-llm-optimization.md` for full rationale)
- **KV cache must be SYMMETRIC** — `q8_0/q8_0` or `q4_0/q4_0`, never mixed.
  Asymmetric KV falls to CPU, 44x slower ([llama.cpp #20866]). Overrides the
  Qwen3-Coder docs' q8-K/q4-V suggestion.
- **Context limit = `min(model max, VRAM-affordable KV)`.** The live vLLM profile
  allocates 65536 tokens with fp8 KV and vision; read `GPU KV cache size` out of
  the startup log after every restart. Historical measurements are in
  [`single-vs-dual-3090.md`](../../docs/domains/ai-gpu/single-vs-dual-3090.md).
- **Local = unlimited token *volume* (free), not an infinite *window* per request.**
- **Engine choice:** the 27B runs on stock unpatched vLLM — `qwen3_5.py` already
  passes `quant_config` to `ParallelLMHead`, so W4A16 + int8 lm_head needs no
  runtime patch. The llama.cpp Flash-Next build is the parked rollback.
- **MTP stays off for Flash-Next.** The merged qwen4exp implementation did not
  include the final Flash-Next MTP path.
- **The dedicated N-gram shard stays lazy and mmap-backed.** Do not add mlock,
  disable `--tensor-read-lazy`, or explicitly offload `per_layer_token_embd`;
  the split IQ4_XS layout keeps that table separate from ordinary weights.
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

- **Current state:** vLLM `replicas: 1` holding the **sole** card; llama-cpp,
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
