# Placing a workload on an accelerator

Use before proposing where a new inference, transcription or media job runs.

## 1. Who holds what (live)
```bash
kubectl get pods -A -o json | python3 -c '
import json,sys
for p in json.load(sys.stdin)["items"]:
  for c in p["spec"].get("containers",[]):
    r={**c.get("resources",{}).get("requests",{}),**c.get("resources",{}).get("limits",{})}
    g={k:v for k,v in r.items() if "intel" in k or "npu" in k or "nvidia" in k}
    if g: print(p["metadata"]["namespace"],p["metadata"]["name"],p["spec"].get("nodeName"),g)'
kubectl get nodes -o json | python3 -c '
import json,sys
for n in json.load(sys.stdin)["items"]:
  a=n["status"]["allocatable"]; print(n["metadata"]["name"],a["cpu"],a["memory"],{k:v for k,v in a.items() if ".com/" in k})'
kubectl top nodes
```
Then `kubectl describe node <n> | sed -n "/Allocated resources/,/Events/p"` for memory requests on the candidate node.

## 2. Rules
- `gpu.intel.com/i915` is one physical iGPU advertised as several shared slots; a slot count says nothing about load. Prefer a node where no pod requests it.
- `npu.intel.com/accel` advertises a single slot. If a pod (e.g. Frigate's detector) holds it, the NPU is unavailable; say so instead of proposing it.
- Both NVIDIA cards are owned whole by vLLM; never plan a new GPU model there without the GPU scale-swap procedure and a VRAM trade-off the user accepts.
- Name CPU models from the repo inventory (`docs/assets/inventory/*/inventory.json`, hardware tables in `docs/`), not from NFD `cpu-model.id` guesses.
- Present the result as a node table: chip, current iGPU/NPU user, free yes/no with one-line reason.
