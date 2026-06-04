# AI / GPU Workload Guidelines

## LLM Backend

This cluster uses **vLLM** for all local AI inference (NOT ollama, NOT llama-cpp
— llama-cpp/comfyui/swarmui are retired to `replicas: 0`). vLLM pools BOTH RTX
3090s at `--tensor-parallel-size 2` (~48 GB).
- Endpoint: `http://vllm-service.vllm.svc.cluster.local:8080` (OpenAI API at
  `/v1`; external `https://vllm.vanillax.me`). Apps send `model: default`.
- vLLM needs **AWQ/GPTQ/compressed-tensors/AutoRound-INT4/FP8** weights — never
  GGUF (that's llama-cpp). FP8 is Hopper/Ada-only.

### Models — pre-staged on NFS, served read-only

`my-apps/ai/vllm/` serves the AWQ models staged on the TrueNAS share
`192.168.10.133:/mnt/ai-pool/vllm`, mounted **read-only** at `/models` via a
static CSI PV (the immich RO pattern — no HF download, no Hub token). One
Deployment per model (both share `app: vllm-server`); each claims BOTH cards at
TP=2, so **exactly one runs at a time**. Switch by scaling one to `replicas: 1`
and the other to `0`, then commit (ArgoCD selfHeal reverts a bare `kubectl scale`).

| Deployment | `--model` (local path) | `model:` names | replicas |
|---|---|---|---|
| `deployment.yaml` ⭐ | `/models/Qwen3.6-27B-AWQ-INT4` | `qwen3.6-27b`, `default` | 1 |
| `deployment-bf16.yaml` | `/models/Qwen3.6-27B-AWQ-BF16-INT4` | `qwen3.6-27b-bf16`, `default` | 0 |

Both are **Qwen3.6-27B — dense, multimodal, Gated-DeltaNet hybrid.** GDN recurrent
state scales with CONCURRENCY (not context), so `--max-num-seqs` is pinned LOW
(**2**); raising it is the likeliest OOM. `--max-model-len 65536` stays clear of
the DeltaNet big-context cliff. compressed-tensors AWQ → vLLM auto-detects the
Marlin kernel (no `--quantization` flag). Tool-calling via
`--enable-auto-tool-choice --tool-call-parser hermes`; vision via
`--limit-mm-per-prompt image=4`.

Add a model: stage it on the NFS share, copy a `deployment-*.yaml` (change
`--model`/`--served-model-name`/labels), and list it in `kustomization.yaml`.
`llama-cpp`, `comfyui` and `swarmui` are at `replicas: 0` because vLLM claims both
cards.

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
  **and** `VLLM_WORKER_MULTIPROC_METHOD=spawn`, or tensor-parallel startup hangs.
  With P2P off, vLLM auto-disables its custom all-reduce; NCCL falls back to host
  shared memory.
- **`/dev/shm` must be large** — mount an in-memory `emptyDir` (≥16Gi for TP=2) at
  `/dev/shm`; the 64 MB container default causes NCCL/IPC bus errors.
- **AWQ/GPTQ/compressed-tensors/FP8 only**, never GGUF. Attention heads must
  divide by 2.
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
