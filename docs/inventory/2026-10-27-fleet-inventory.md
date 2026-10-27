# Fleet inventory — October 27, 2026

**Purpose:** list every machine in the lab, with what runs on it and how loaded it is.
**Status:** dated, read-only snapshot. It replaces the [October 22 inventory](2026-10-22-fleet-inventory.md)
as the current host list. Disks are maintained in the [disk map](../domains/storage/disk-map.md).

Collection: about 02:30 UTC, from the Kubernetes API (`kubectl get nodes`, `kubectl top nodes`,
`kubectl describe nodes`, running pods), Longhorn objects and Omni `MachineStatus`. Queries ran
separately, so this is not an atomic snapshot. CPU and memory use are point-in-time `kubectl top`
values. Proxmox host RAM, CPU temperatures and NAS pools were not re-collected.

## What changed since October 22

- **The `proxmox-hp-elite` provider is gone.** It was still running on the Pi and registered in
  Omni until October 26. Its container, its Omni provider object and the `hp-elite-worker` machine
  class are now removed. The Pi runs 3 Proxmox providers.
- **The Omni template matches the live cluster.** `omnictl cluster template diff` is empty.
- **The three bare-metal nodes have a hardware watchdog** (Intel TCO, 2 min), and
  `monitoring/logs/boot-reason` logs how each boot ended
  ([#3174](https://github.com/mitchross/talos-argocd-proxmox/pull/3174)).

## Physical machines

| Machine | Address | CPU | RAM | Platform | Runs |
|---|---|---|---:|---|---|
| Threadripper (X399) | `.14` | Ryzen TR 2950X · 32 threads | 125.7 GiB | Proxmox VE 9 | GPU worker VM (30 vCPU, 100 GiB, 2× RTX 3090) |
| HP ProDesk 600 G4 SFF | `.21` | i5-8500 · 6 threads | 62.6 GiB | Proxmox VE 9 | **control plane** VM (4 vCPU, 12 GiB) + worker VM (6 vCPU, 40 GiB) |
| HP ProDesk 600 G4 DM (shed) | `.20` | i5-8500T · 6 threads | 31.1 GiB | Proxmox VE 9 | worker VM (4 vCPU, 12 GiB), USB radios, Wi-Fi bridge |
| Dell Pro Micro QCM1250 | `.181` | Core Ultra 5 245T · 14 cores, iGPU + NPU | 32 GiB (2× 16 GB) | Talos v1.14.4 bare metal | worker `mini-pc-dell-ultra-worker` |
| HP Elite Mini 800 G9 | `.82` | i5-12500T · 12 threads | 16 GiB (2× 8 GB) | Talos v1.14.4 bare metal | worker `hp-elite-gen12`, Zigbee stick |
| HP Elite Mini 600 G9 | `.88` | i5-13500T · 20 threads | 16 GiB (1× 16 GB) | Talos v1.14.4 bare metal | worker `hp-elite-gen13` |
| HPE ProLiant DL360 Gen9 (TrueNAS) | `.133` | Xeon E5-2680 v4 · 28 threads | 377.6 GiB | TrueNAS 28.0 | NFS/SMB storage, kopiur repository |
| Raspberry Pi 5 | `.15` | Cortex-A76 · 4 threads | 7.7 GiB | Ubuntu 26.04 | Omni v1.12.4, 3 Proxmox providers, booter (PXE), Technitium DNS, ProxCenter |

## Kubernetes nodes

Cluster `talos-prod-cluster-v2`: **7 nodes**, all Ready, Talos v1.14.4, Kubernetes v1.37.1.

| Node | Host | CPU (alloc) | Memory (alloc) | CPU used | Memory used | Memory requested | Pods | Accelerators |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `talos-prod-cluster-v2-control-planes-7mxjxv` | `.21` VM | 3.95 | 11.1 GiB | 0.84 | 5.4 GiB | 4.0 GiB (35%) | 20 | — |
| `talos-prod-cluster-v2-gpu-workers-jxfkdr` | `.14` VM | 29.95 | 97.7 GiB | 5.14 | 45.2 GiB | 62.4 GiB (63%) | 82 | `nvidia.com/gpu=2` |
| `talos-prod-cluster-v2-hp-sff-workers-h76ncc` | `.21` VM | 5.95 | 38.7 GiB | 1.28 | 13.1 GiB | 22.1 GiB (57%) | 50 | `gpu.intel.com/i915=4` |
| `talos-prod-cluster-v2-hp-micro-workers-pstbbd` | `.20` VM | 3.95 | 11.2 GiB | 0.16 | 3.0 GiB | 2.4 GiB (21%) | 15 | — |
| `mini-pc-dell-ultra-worker` | `.181` bare metal | 13.25 | 29.3 GiB | 1.14 | 12.7 GiB | 15.6 GiB (53%) | 44 | `gpu.intel.com/i915=4` |
| `hp-elite-gen12` | `.82` bare metal | 11.25 | 13.7 GiB | 0.87 | 5.4 GiB | 8.3 GiB (60%) | 53 | `gpu.intel.com/i915=4` |
| `hp-elite-gen13` | `.88` bare metal | 19.25 | 13.2 GiB | 1.00 | 5.8 GiB | 8.1 GiB (61%) | 49 | `gpu.intel.com/i915=4` |
| **Total** | | **87.55** | **214.8 GiB** | **10.4** | **90.6 GiB** | **122.8 GiB** | **313** | |

"Pods" counts running pods. "Memory requested" comes from `kubectl describe node` and counts
every non-terminated pod.

## Storage

**Longhorn:** 68 volumes; 59 attached and healthy, 8 detached (normal), 1 faulted
(`nginx-example/storage`). All 80 PVCs are Bound.

| Node | Longhorn disk | Scheduling | Size | Free | Scheduled (requested) | Replicas |
|---|---|---|---:|---:|---:|---:|
| GPU worker | `gpu-bulk` | on | 799 GiB | 741 GiB | 493 GiB | 28 |
| GPU worker | `ssd-flash` (PLP, `clone-ok`) | on | 439 GiB | 253 GiB | 437 GiB | 11 |
| hp-sff worker | `hp-sff-ssd` | on | 689 GiB | 600 GiB | 376 GiB | 23 |
| hp-sff worker | `hp-sff-ssd2` | on | 919 GiB | 884 GiB | 176 GiB | 11 |
| `hp-elite-gen13` | `hp-elite-nvme` (Intel 660p, worn) | on | 476 GiB | 452 GiB | 170 GiB | 11 |
| `mini-pc-dell-ultra-worker` | `dell-ultra-ssd` | on | 233 GiB | 229 GiB | 0 | 0 |
| hp-micro worker | `hp-micro-ssd` | **off** (Wi-Fi node) | 849 GiB | 833 GiB | 0 | 0 |
| `hp-elite-gen12` | — | compute-only | — | — | — | — |

Each node also has a `talos-ephemeral` disk with scheduling off.

## GitOps health

101 Argo CD applications: 98 Synced/Healthy. `my-apps-deal-scout` is Progressing during a
rollout. Two are Degraded: `my-apps-homepage-public` and `infrastructure-container-registry`
(see findings).

## Findings

1. **`homepage-public` is in CrashLoopBackOff.** Its log repeats `Host validation failed for:
   10.244.x.x:3000`, so requests to the pod IP fail homepage's `HOMEPAGE_ALLOWED_HOSTS` check.
2. **`infrastructure-container-registry` is Degraded by its `registry-gc` CronJob.** The registry
   pod itself is Running.
3. **`dell-ultra-ssd` holds no replicas.** The node is Ready and Schedulable with tag
   `wired-storage`, so `longhorn` and `longhorn-wired-ha` volumes can use it. The cause is not checked.
4. **`hp-elite-gen13` and `hp-elite-gen12` have 13.2–13.7 GiB allocatable** and 60–61% of it
   requested. A second DIMM in the 600 G9 doubles it.
5. **The Intel 660p is past its rated writes.** It is the first disk to replace; see the
   [disk map](../domains/storage/disk-map.md).
6. **Control plane is still one VM.** The 1 → 3 move is tracked in
   [#3071](https://github.com/mitchross/talos-argocd-proxmox/issues/3071).
7. **Omni still lists health records for the retired `proxmox-dell` and `proxmox-hp-elite`
   providers.** They are in the `infra-provider-ephemeral` namespace, which Omni does not keep
   across restarts, so the next Omni restart clears them.

## Limits

- Proxmox host RAM, CPU temperature and uptime were not re-collected.
- Bare-metal RAM comes from Omni `MachineStatus` memory modules.
- Disk serials stay out of this page. See the disk map for drive models and roles.
