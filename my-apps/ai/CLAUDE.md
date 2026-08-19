# AI / GPU Workload Guidelines

## LLM Backend

One OpenAI-compatible local backend, **NOT ollama**:

### vLLM — active, single card
- Endpoint: `http://vllm-service.vllm.svc.cluster.local:8080/v1`
- Served model: **`qwen3.8-27b`** — Qwen3.8-27B W4A16 AutoRound with INT8
  group-128 `lm_head`, BF16 `embed_tokens`, FP8 KV, on **one** RTX 3090 (TP=1).
- **Multimodal**: the vision tower is enabled, with one image and no video
  allowed per prompt to bound one-card VRAM use.
- **Use vLLM / `qwen3.8-27b` when wiring an in-cluster app to chat inference.**

### llama-cpp — parked
- `replicas: 0`. Endpoint `http://llama-cpp-service.llama-cpp.svc.cluster.local:8080/v1`.
- Serves Qwen3.8-27B GGUF plus a vision projector when scaled up; advertises
  `qwen3.8` and `qwen3.8-nothink`. It is an alternate GGUF backend and may be
  scaled up only via the swap procedure.

All in-cluster vLLM consumers request `qwen3.8-27b`, including Karakeep text and
image inference. ComfyUI's dedicated llama.cpp-client workflow still requests
`qwen3.8` because that integration calls the parked llama.cpp Service directly.

**App→backend wiring + capacity rules:
[`model-catalog.md`](../../docs/domains/ai-gpu/model-catalog.md) ·
[`single-vs-dual-3090.md`](../../docs/domains/ai-gpu/single-vs-dual-3090.md).**

### Gotchas (see `docs/domains/ai-gpu/3090-llm-optimization.md` for full rationale)
- **KV cache must be SYMMETRIC** — `q8_0/q8_0` or `q4_0/q4_0`, never mixed.
  Asymmetric KV falls to CPU, 44x slower ([llama.cpp #20866]). Overrides the
  Qwen3-Coder docs' q8-K/q4-V suggestion.
- **Context limit = `min(model max, VRAM-affordable KV)`.** The live MTP profile
  uses a 65536 ceiling at 0.90 utilization with vision enabled; read `GPU KV cache size` from the
  boot log after every restart rather than predicting it. Historical non-MTP
  measurements are in
  [`single-vs-dual-3090.md`](../../docs/domains/ai-gpu/single-vs-dual-3090.md).
- **Local = unlimited token *volume* (free), not an infinite *window* per request.**
- **Engine choice:** Qwen 3.8 runs on vLLM via W4A16 AutoRound with an INT8
  `lm_head`, which stock vLLM loads unpatched, including its vision tower.
  llama.cpp GGUF is the alternate backend.
- **MTP/spec-decode gives NO net speedup** on Ampere + 35B-A3B under llama.cpp
  (same-hw benchmark). The live single-card vLLM profile enables MTP-2, but its
  acceptance and throughput must be verified from metrics and two warm runs.
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

- **Current state:** vLLM `replicas: 1` holding **one** card; llama-cpp,
  ComfyUI and SwarmUI `0`. One 3090 is free for a second single-card workload.
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
