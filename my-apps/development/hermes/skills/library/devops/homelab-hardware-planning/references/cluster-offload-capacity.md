# Moving work off a host / making room for a big pod

Use this for "offload more from the Threadripper" and "why can't the ~60 GiB model pod schedule".

## Rule
The scheduler packs pods by **requests**, not by real use. A node can show 50% memory used and still refuse a big pod because its requests are close to allocatable. Always report three numbers per node: allocatable, requested, used.

## Recipe (read-only, from the Hermes pod)
1. `kubectl top nodes`, then `kubectl get pods -A -o json > pods.json`, `kubectl top pods -A --no-headers > top.txt`, `kubectl get nodes -o json > nodes.json`.
2. In Python:
   - Sum container `resources.requests` (cpu, memory) per `spec.nodeName`, and join with `top.txt` for real use.
   - Print per node: allocatable / requested / used.
   - For the target node, list non-DaemonSet pods sorted by memory used.
   - Flag pins: `nodeSelector` or affinity mentioning `gpu` or `kubernetes.io/hostname`, and `nvidia.com/gpu` in resources.
   - Count PVCs, because they're Longhorn data that will read over the network after a move.
3. Bucket the pods:
   - **Pinned on purpose:** GPU workloads, apps pinned to the GPU host for local data.
   - **Over-requested:** request well above use. Fix by right-sizing in Git.
   - **Movable:** no pin. Move by node affinity or anti-affinity in Git.
4. Compare against free requested memory on the other nodes. Small mini PCs often have only 5–10 GiB of free requests, so they become the next limit. A RAM upgrade for the minis is the spend-to-save candidate here.
5. Plan in order, cheapest first:
   1. Right-size over-requests.
   2. Move unpinned heavy apps (analytics stacks such as PostHog are typical).
   3. Resize the VM. That's the user's Proxmox/Omni step.
   All cluster changes go through Git PRs.

## Pitfalls
- A pod using many cores but little RAM (e.g. a memory/consolidation service stuck working) also competes with CPU-heavy offload engines that want ~15 cores. List CPU use too, not just memory.
- Don't count the Wi-Fi/edge node as general capacity if Longhorn or edge-only rules keep workloads off it.
