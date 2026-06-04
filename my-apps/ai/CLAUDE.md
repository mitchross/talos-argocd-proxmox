# AI / GPU Workload Guidelines

## LLM Backend

This cluster uses **vLLM** for all local AI inference (NOT ollama, NOT llama-cpp
— llama-cpp is retired to `replicas: 0`). vLLM pools BOTH RTX 3090s at
`--tensor-parallel-size 2` (~48 GB).
- Endpoint: `http://vllm-service.vllm.svc.cluster.local:8000` (OpenAI API at `/v1`).
- Apps send `model: default` — it always resolves to whichever bank model is
  currently running (every entry sets `--served-model-name default <name>`).
- vLLM needs **AWQ/GPTQ/FP8** weights — never GGUF. On Ampere (sm_86) use **AWQ**
  (FP8 is Hopper/Ada-only; Intel AutoRound INT4 is blocked on Ampere).

### The vLLM preset bank (swap on demand)

`my-apps/ai/vllm/` defines **one Deployment per model**, all sharing
`app: vllm-server` so `vllm-service` routes to whichever is scaled up. The node
has only two cards and each model claims both at TP=2, so **exactly one runs at a
time**. Switch by setting one to `replicas: 1` and the rest to `0`, then commit
(ArgoCD selfHeal reverts a bare `kubectl scale`).

| Model (`model:` field) | HF repo (AWQ) | replicas | Use |
|---|---|---|---|
| `qwen3.6` / `default` ⭐ | `QuantTrio/Qwen3.6-35B-A3B-AWQ` | 1 | daily driver — chat/tools/RAG/vision |
| `coder` | `QuantTrio/Qwen3-Coder-30B-A3B-Instruct-AWQ` | 0 | coding agent |
| `gemma4` | `cyankiwi/gemma-4-26B-A4B-it-AWQ-4bit` | 0 | multimodal fallback (`--tool-call-parser gemma4`; see vLLM #40247 image note) |
| `gemma4-31b` | `cyankiwi/gemma-4-31B-it-AWQ-4bit` | 0 | top-quality dense (slow) |
| `tool-fast` | `cyankiwi/Qwen3-4B-Instruct-2507-AWQ-4bit` | 0 | fast triage / tool calls |

Add a model: copy a `deployment-*.yaml`, change name/labels/`--model`/
`--served-model-name`, and list it in `kustomization.yaml`. `llama-cpp` and
`swarmui` are at `replicas: 0` (kept for revert) because vLLM claims both cards.

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
