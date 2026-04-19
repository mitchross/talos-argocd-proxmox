# AI / GPU Workload Guidelines

## LLM Backend

This cluster uses **llama-cpp** (NOT ollama) for all local AI inference.
- Endpoint: `http://llama-cpp-service.llama-cpp.svc.cluster.local:8080`
- OpenAI-compatible API at `/v1`
- Primary model: **Qwen3.6-35B-A3B** (Unsloth UD-Q4_K_XL, multimodal via `mmproj-BF16.gguf`)
- Fallbacks: Gemma 4 26B-A4B (multimodal) + Qwen 3.5 Uncensored
- Full preset list (model IDs clients send in the `model` field): `my-apps/ai/llama-cpp/configmap.yaml`

Always use llama-cpp when configuring AI backends for in-cluster tools.

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
