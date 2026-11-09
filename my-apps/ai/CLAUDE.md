# AI / GPU Workload Guidelines

## LLM Backend

The Git-declared production backend is **vLLM**, never Ollama. See
[`vllm/README.md`](vllm/README.md) for the pinned AutoRound INT4 checkpoint,
staging order, runtime flags, reasoning/sampling controls and rollback.

- Model ID: `qwen3.8-27b`; `Frozenlock/Qwen3.8-27B-int4-AutoRound`.
- vLLM (version: `my-apps/ai/vllm/deployment.yaml`), two RTX 3090s with TP=2, FP8 KV, vision, 262,144-token ceiling.
- **MTP/speculation stays off** pending the long-session fixes and validation.
- Server default: `xhigh`, preservation true; thinking budgets low=4096, medium=16384, xhigh=16384.
  The baked template maps high/max to xhigh and minimal to low; explicit client efforts still win.
- Off requests use `enable_thinking=false`, `preserve_thinking=false`, and
  the separate non-thinking sampler in the vLLM runbook. Preserve the server's
  thinking sampler; do not globally disable preserved thinking.
- Application URL: `http://litellm-service.litellm.svc.cluster.local:4000/v1`; authenticate with an ExternalSecret from `litellm/master_key`.
- Direct diagnostic / gateway upstream URL: `http://vllm-service.vllm.svc.cluster.local:8080/v1`.
- Both LAN hostnames (`vllm.vanillax.me`, `llama.vanillax.me`) route to the vLLM
  selector Service.
- Historical capacity and current client guidance: `docs/domains/ai-gpu/3090-llm-optimization.md`.
  A configured ceiling is not proof of concurrent near-ceiling vision capacity.
- Strata is parked (`replicas: 0`); vLLM serves INT4/W4A8 with `max-num-seqs=16`.
- LiteLLM default/auto routes keep paid DeepSeek overflow; `qwen3.8-27b-local` is private-only.
  Each deployment cap is 16 per LiteLLM pod, not a shared engine-wide admission cap.

Pi's direct-Qwen settings and launcher are managed in `mitchross/dotfiles`;
keep their explicit xhigh preference unchanged unless requested. Explicit client efforts still win.
`pi-auto` inherits the local server default without forwarding Qwen effort;
its classifier stays thinking-off and its DeepSeek high/max routes are unchanged.

## GPU Topology

Whole-card allocations, time-slicing disabled, `Recreate` strategy. vLLM
requests both RTX 3090s; Strata is parked;
ComfyUI and SwarmUI remain at zero replicas.
Use committed replica counts and the
[scale-swap runbook](../../docs/domains/ai-gpu/gpu-scale-swap.md).

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

**Large CPU-offloaded LLMs need reserved RAM.** The GPU node also hosts
unrelated workloads and storage; do not assume it is isolated. The declared
vLLM container requests 8 GiB and limits memory to 64 GiB. That limit is not
reserved or free host RAM. Re-check guest allocatable memory, other pod
requests and steady-state usage before any large-model cutover; historical
node measurements are not a current capacity guarantee.

## Debugging GPU

```bash
kubectl get nodes -o json | jq '.items[].metadata.labels' | grep gpu
kubectl get pods -n gpu-operator
kubectl exec -it -n vllm deploy/vllm-server -- nvidia-smi
kubectl logs -n vllm deploy/vllm-server -f
```
