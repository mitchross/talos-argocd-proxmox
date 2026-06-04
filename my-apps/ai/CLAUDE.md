# AI / GPU Workload Guidelines

## LLM Backend

This cluster uses **vLLM** for all local AI inference (NOT ollama, NOT llama-cpp
— llama-cpp is retired to `replicas: 0`, see "Strategy" below).
- Endpoint: `http://vllm-service.vllm.svc.cluster.local:8000`
- OpenAI-compatible API at `/v1` (chat/completions, models, …)
- Primary model: **Qwen2.5-Coder-32B-Instruct-AWQ**, served at
  `--tensor-parallel-size 2` across BOTH 3090s. Swap the model via the `--model`
  arg in `my-apps/ai/vllm/deployment.yaml`. vLLM needs **AWQ/GPTQ/FP8** weights —
  it does NOT use GGUF efficiently.
- Client-facing model names (the `model` field clients send): `qwen2.5-coder-32b`
  and the alias `default` (set via `--served-model-name`).

Always point in-cluster AI backends at the vLLM endpoint above.

### Strategy: vLLM-first on both GPUs

We run **one** vLLM server pooling both RTX 3090s (TP=2 ≈ 48GB) instead of the
old one-model-per-card llama.cpp / ComfyUI split — this is the dual-card pooled
endpoint that wins for big-context coding/research. `llama-cpp` and `swarmui`
are at `replicas: 0` (kept for a fast revert) because the node has only two
cards and vLLM claims both.

## GPU Topology

Two RTX 3090s (24 GB each), **pooled** for one vLLM server:
- **GPU 0 + GPU 1 → vLLM** (`--tensor-parallel-size 2`, ~48 GB usable)

`llama-cpp` (was GPU 0) and `swarmui` (was GPU 1) are at `replicas: 0`. To run a
dual-GPU batch Job (e.g. `llmfit`) scale vLLM to 0 first — the node has exactly
two cards.

Time-slicing is DISABLED (`time-slicing-config.yaml` has no sharing block) so the
node advertises `nvidia.com/gpu: 2`; a pod requesting `nvidia.com/gpu: 2` gets
both whole cards. Don't set `NVIDIA_VISIBLE_DEVICES` or `CUDA_VISIBLE_DEVICES` in
pod env — they override the device-plugin's CDI injection.

### Dual-3090 TP=2 gotchas (vLLM)
- **No NVLink + PCIe passthrough → no GPU peer-to-peer.** Set `NCCL_P2P_DISABLE=1`
  **and** `--disable-custom-all-reduce`, or tensor-parallel startup hangs. NCCL
  falls back to host shared memory.
- **`/dev/shm` must be large** — mount an in-memory `emptyDir` (≥8–10Gi) at
  `/dev/shm`; the 64 MB container default causes NCCL/IPC bus errors.
- **AWQ/GPTQ/FP8 only**, never GGUF. Attention heads must divide by 2 (Qwen2.5 ok).
- **Request `nvidia.com/gpu: 2`** so the device plugin injects both cards (cuda:0/1).

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
