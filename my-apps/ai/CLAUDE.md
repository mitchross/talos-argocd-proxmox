# AI / GPU Workload Guidelines

## LLM Backend

The Git-declared production backend is **vLLM**, never Ollama. See
[`vllm/README.md`](vllm/README.md) for the pinned official FP8 checkpoint,
staging order, runtime flags, reasoning/sampling controls and rollback.

- Model ID: `qwen3.8-27b`; official `Qwen/Qwen3.8-27B-FP8`.
- vLLM v0.28.0, two RTX 3090s with TP=2, FP8 KV, vision, 262,144-token ceiling.
- **MTP/speculation stays off** pending the long-session fixes and validation.
- Explicit thinking levels: `low`, `medium`, `xhigh`; coding/server default
  is `medium`, preservation true. xhigh is opt-in; generic high maps to medium.
- Off requests use `enable_thinking=false`, `preserve_thinking=false`, and
  the separate non-thinking sampler in the vLLM runbook. Preserve the server's
  thinking sampler; do not globally disable preserved thinking.
- Direct URL: `http://vllm-service.vllm.svc.cluster.local:8080/v1`.
- Existing `llama-cpp-service` URLs alias vLLM. Both LAN hostnames route to the
  vLLM selector Service, not an ExternalName backend.
- Live capacity and client guidance: `docs/domains/ai-gpu/3090-llm-optimization.md`.
  A configured ceiling is not proof of concurrent near-ceiling vision capacity.
- llama.cpp is the parked GGUF rollback. AutoRound is a later speed A/B only.

## GPU Topology

Whole-card allocations, time-slicing disabled, `Recreate` strategy. vLLM
requests both RTX 3090s; llama.cpp, ComfyUI and SwarmUI remain at zero replicas.
Use committed replica counts and the
[scale-swap runbook](../../../docs/domains/ai-gpu/gpu-scale-swap.md).

Do not set `NVIDIA_VISIBLE_DEVICES` or `CUDA_VISIBLE_DEVICES` in GPU workloads;
the device plugin/CDI owns allocation. The `nvidia-powerlimit` utility DaemonSet
is the exception. Keep the **220 W per-card** cap; do not raise it for benchmarks.
The production GPU node has `gpu-worker=true`; the Wi-Fi worker is CPU-only.

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

**Large CPU-offloaded LLMs need reserved RAM.** The GPU node currently also
hosts unrelated workloads and storage; do not assume it is isolated. Resolve
competing allocations before a large-model cutover; see
[`flash-next-dual-3090.md`](../../../docs/domains/ai-gpu/flash-next-dual-3090.md).

## Debugging GPU

```bash
kubectl get nodes -o json | jq '.items[].metadata.labels' | grep gpu
kubectl get pods -n gpu-operator
kubectl exec -it -n vllm deploy/vllm-server -- nvidia-smi
kubectl logs -n vllm deploy/vllm-server -f
```
