# AI / GPU Workload Guidelines

## LLM Backend

One active OpenAI-compatible local backend, **NOT ollama**:

### llama.cpp — active, single card
- Endpoint: `http://llama-cpp-service.llama-cpp.svc.cluster.local:8080/v1`
- LAN endpoints: `https://vllm.vanillax.me/v1` and `https://llama.vanillax.me/v1`
- Served API model: **`qwen3.8-27b`**
- Runtime: stock llama.cpp `b10752` CUDA12 on one RTX 3090.
- Model: Qwen3.8-27B `UD-Q4_K_XL`, full-GPU target + MTP draft.
- Context: 65,536; symmetric q8_0 target/draft KV; MTP `n-max=2`.
- Native vision is enabled with the BF16 projector.
- **Use llama.cpp / `qwen3.8-27b` when wiring an in-cluster app to chat inference.**

### vLLM — parked rollback
- `replicas: 0`; its model/cache artifacts remain intact.
- `vllm-service.vllm.svc.cluster.local` is an `ExternalName` compatibility alias
  to llama.cpp for persistent/out-of-Git clients. New Git-managed consumers
  should use `llama-cpp-service` directly.

**App→backend wiring + capacity rules:**
[`model-catalog.md`](../../docs/domains/ai-gpu/model-catalog.md) ·
[`single-vs-dual-3090.md`](../../docs/domains/ai-gpu/single-vs-dual-3090.md).

### Current llama.cpp gotchas
- **Use b10752 or newer.** Qwen3.8-27B MTP KV initialization regressed in
  b10745 and was fixed in b10751.
- **KV cache stays symmetric q8_0/q8_0** for target and draft on the 3090.
- **Keep target and MTP draft on GPU.** The point of this profile is to avoid
  putting the Threadripper/system RAM in the per-token hot path.
- **65K is the production window, not a benchmark target.** Increase only after
  text, tools, vision, Pi and multi-turn stability are established.
- **`GGML_CUDA_GRAPH_OPT=1` is intentional** for dense RTX decode.
- **`GGML_CUDA_CUBLAS_COMPUTE_TYPE=fp32` is intentional** for the Ampere vision
  path; it avoids a reported cuBLAS multimodal prefill failure.
- **`--image-min-tokens 1024` is intentional** for Qwen vision/grounding
  correctness.
- **Do not re-add `--cache-reuse` while multimodal is enabled.** llama.cpp
  disables it with the projector loaded and only emits a warning.
- **Local = unlimited token volume (free), not an infinite request window.**

## GPU Topology

GPU workloads (vLLM, llama-cpp, ComfyUI, SwarmUI) are **mutually-exclusive
whole-card workloads** (`type: Recreate`, time-slicing disabled). Never run two
of them at one replica on the single RTX 3090.

The production AI workloads are pinned to `gpu-worker=true`. The Wi-Fi worker
is CPU-only and deliberately does not carry that label.

- **Current state:** llama.cpp `replicas: 1`; vLLM, ComfyUI and SwarmUI are `0`.
- To change GPU ownership, change committed replica counts in Git; Argo self-heal
  will undo ad-hoc manual scaling.
- Time-slicing is disabled, so whole-card allocation is enforced.
- Do not set `NVIDIA_VISIBLE_DEVICES` or `CUDA_VISIBLE_DEVICES` in workload pod
  env; they override the device-plugin/CDI injection.
- The infrastructure `nvidia-powerlimit` DaemonSet is the exception because it
  administers the physical card without consuming a workload allocation.
- The current **220 W** 3090 power cap is a house-circuit constraint. Do not
  raise it as a casual performance tweak.

## GPU Workload Pattern

Reference `my-apps/ai/comfyui/` for a complete example:

```yaml
spec:
  template:
    spec:
      nodeSelector:
        feature.node.kubernetes.io/pci-0300_10de.present: "true"
        gpu-worker: "true"
      runtimeClassName: nvidia
      priorityClassName: gpu-workload-preemptible
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

**GPU node is reserved for LLM RAM** — do not schedule Longhorn replicas or
unrelated workloads there.

## Debugging GPU

```bash
kubectl get nodes -o json | jq '.items[].metadata.labels' | grep gpu
kubectl get pods -n gpu-operator
kubectl exec -it -n llama-cpp deploy/llama-cpp-server -- nvidia-smi
kubectl logs -n llama-cpp deploy/llama-cpp-server -f
```
