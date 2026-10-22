# Fleet inventory — October 21, 2026

**Purpose:** list every machine in the lab, with what runs on it and how loaded it is.
**Status:** dated, read-only snapshot. It replaces the [October 15 inventory](2026-10-15-full-inventory.md)
as the current host list. Disks are maintained in the [disk map](../domains/storage/disk-map.md).

Collection: about 13:10–13:20 UTC, from Prometheus (`physical-node` exporters and in-cluster
node-exporter), the Kubernetes API, and Longhorn objects. Queries ran separately, so this is not an
atomic snapshot. CPU % is a 10-minute average. No benchmarks or changes were made.

## What changed since October 15

- **Dell OptiPlex 7060 (`.16`) retired** ([#3067](https://github.com/mitchross/talos-argocd-proxmox/pull/3067)). Its VM, machine class, Proxmox provider and Longhorn node are gone, and the host is powered off.
- **Two bare-metal Talos workers joined**, PXE-booted through `booter` on the Pi ([#3069](https://github.com/mitchross/talos-argocd-proxmox/issues/3069), [#3074](https://github.com/mitchross/talos-argocd-proxmox/pull/3074), [#3077](https://github.com/mitchross/talos-argocd-proxmox/pull/3077)). They are the first nodes not running as Proxmox VMs.
- **Omni v1.12.4 and Talos v1.14.4** on every node ([#3068](https://github.com/mitchross/talos-argocd-proxmox/pull/3068)).
- **Paseo turned off** ([#3072](https://github.com/mitchross/talos-argocd-proxmox/pull/3072)). Hermes is the cluster agent.
- Two single-replica volumes faulted after the upgrade reboots. On 2026-10-21 `tubesync/config-pvc` was restored from kopiur and `paperless-ngx/paperless-export-pvc` was recreated ([#3071](https://github.com/mitchross/talos-argocd-proxmox/issues/3071)).

## Physical machines

| Machine | Address | CPU | RAM | Platform | Runs | CPU used | RAM free | Uptime |
|---|---|---|---:|---|---|---:|---:|---:|
| Threadripper (X399) | `.14` | Ryzen TR 2950X · 32 threads | 125.7 GiB | Proxmox VE 9 (kernel 7.0.14-25-pve) | GPU worker VM (30 vCPU, 100 GiB, 2× RTX 3090) | 49% | 20.2 GiB | 0.9 d |
| HP ProDesk 600 G4 SFF | `.21` | i5-8500 · 6 threads | 62.6 GiB (4× 16 GB, full) | Proxmox VE 9 (7.0.14-25-pve) | **control plane** VM (4 vCPU, 12 GiB) + worker VM (6 vCPU, 40 GiB) | 37% | 11.3 GiB | 0.9 d |
| HP Elite Mini 600 G9 | `.22` | i5-13500T · 20 threads | 30.6 GiB (2× 16 GB DDR5) | Proxmox VE 9 (7.0.14-20-pve) | worker VM (16 vCPU, 26 GiB) + Proxmox Datacenter Manager LXC | 16% | **2.1 GiB** | 4.4 d |
| HP ProDesk 600 G4 DM (shed) | `.20` | i5-8500T · 6 threads | 31.1 GiB | Proxmox VE 9 (7.0.14-25-pve) | worker VM (4 vCPU, 12 GiB), USB radios, Wi-Fi bridge | 5% | 24.1 GiB | 0.9 d |
| **Dell Pro Micro QCM1250** | `.181` | Core Ultra 5 245T · 14 cores, iGPU + NPU | 16 GiB (1 DIMM, 1 slot free) | **Talos v1.14.4 bare metal** | worker `mini-pc-dell-ultra-worker` | 4% | see nodes | 0.4 d |
| **HP Elite Mini 800 G9** | `.82` | i5-12500T · 12 threads | 16 GiB (2× 8 GB, both slots used) | **Talos v1.14.4 bare metal** | worker `hp-elite-gen12` | 6% | see nodes | 0.8 d |
| HPE ProLiant DL360 Gen9 (TrueNAS) | `.133` | Xeon E5-2680 v4 · 28 threads | 377.6 GiB | TrueNAS 28.0 (kernel 6.18.55) | NFS/SMB storage, kopiur repository | 3% | 25.3 GiB (ARC uses the rest) | 7.8 d |
| Raspberry Pi 5 | `.15` | Cortex-A76 · 4 threads | 7.7 GiB | Ubuntu 26.04 | Omni v1.12.4, 4 Proxmox providers, booter v0.4.0 (PXE), Technitium DNS, ProxCenter | 1% | 5.8 GiB | 34.4 d |
| ~~Dell OptiPlex 7060~~ | ~~`.16`~~ | — | — | retired, powered off | — | — | — | — |

The Proxmox hosts `.14`, `.21` and `.20` were apt-upgraded and rebooted during the Talos rollout on 2026-10-20/21. That explains their 0.9-day uptime.

## Kubernetes nodes

Cluster `talos-prod-cluster-v2`: **7 nodes**, all Ready, Talos v1.14.4, kernel 6.18.57, Kubernetes v1.37.1, containerd 2.3.7.

| Node | Host | Role / pool | CPU (alloc) | Memory (alloc) | CPU used | Memory used (working set) | Memory requested | Pods | Accelerators |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| `talos-prod-cluster-v2-control-planes-7mxjxv` | `.21` VM | control plane (`NoSchedule`) | 3.95 | 11.1 GiB | 0.32 | 5.8 GiB | 4.2 GiB | 20 | — |
| `talos-prod-cluster-v2-gpu-workers-jxfkdr` | `.14` VM | `gpu` | 29.95 | 97.7 GiB | 12.0 | 39.8 GiB | 66.8 GiB (68%) | 62 | `nvidia.com/gpu=2` (RTX 3090) |
| `talos-prod-cluster-v2-hp-sff-workers-h76ncc` | `.21` VM | `general` | 5.95 | 38.7 GiB | 0.65 | 12.5 GiB | 23.6 GiB (61%) | 44 | `gpu.intel.com/i915=4` |
| `talos-prod-cluster-v2-hp-elite-workers-l5zlgr` | `.22` VM | `general` | 15.95 | 24.9 GiB | 1.87 | 9.0 GiB | 15.7 GiB (63%) | 69 | `gpu.intel.com/i915=4` |
| `talos-prod-cluster-v2-hp-micro-workers-pstbbd` | `.20` VM | `edge` (taint `link=wifi`) | 3.95 | 11.2 GiB | 0.06 | 2.1 GiB | 2.6 GiB | 13 | — |
| `mini-pc-dell-ultra-worker` | `.181` bare metal | `general` | 13.25 | 13.5 GiB | 0.27 | 6.3 GiB | 8.0 GiB (59%) | 48 | `gpu.intel.com/i915=4`, NPU extension (no device plugin yet) |
| `hp-elite-gen12` | `.82` bare metal | `general` | 11.25 | 13.7 GiB | 0.30 | 3.6 GiB | 7.2 GiB (53%) | 45 | `gpu.intel.com/i915=4` |
| **Total** | | | **84.25** | **210.8 GiB** | **15.5** | **79.1 GiB** | **128.1 GiB** | **301** | |

The bare-metal minis give Kubernetes 13.5–13.7 GiB of their 16 GiB, after the kubelet reservations (`system` 1 GiB, `kube` 512 MiB). The 16 GiB shed VM, by comparison, gives 11.2 GiB.

## Storage

**Longhorn:** 66 volumes, 59 attached and healthy, 7 detached (normal). All 78 PVCs are Bound.

| Node | Longhorn disk | Scheduling | Size | Free | Scheduled (requested) |
|---|---|---|---:|---:|---:|
| GPU worker | `gpu-bulk` | on | 799.6 GiB | 756.4 GiB | 478.1 GiB |
| GPU worker | `ssd-flash` (PLP, `clone-ok`) | on | 439.9 GiB | 222.5 GiB | 502.0 GiB (over-provisioned) |
| hp-sff worker | `hp-sff-ssd` | on | 689.7 GiB | 611.7 GiB | 316.0 GiB |
| hp-elite worker | `hp-elite-nvme` (Intel 660p, 76% worn) | on | 439.8 GiB | 409.8 GiB | 176.0 GiB |
| hp-micro worker | `hp-micro-ssd` | **off** (Wi-Fi node) | 849.6 GiB | 833.2 GiB | 0 |
| both minis | — | compute-only, no Longhorn disk | — | — | — |

Each node also has a `talos-ephemeral` disk with scheduling off. NAS pools and dataset usage were not re-collected; see the [October 15 inventory](2026-10-15-full-inventory.md#truenas-and-management-services).

## GitOps health

98 Argo CD applications. 97 are Synced/Healthy. `my-apps-posthog` is OutOfSync (Healthy) while it waits on its `clickhouse-migrations-init` hook.

## Findings

1. **HP Elite 600 G9 (`.22`) host has 2.1 GiB free.** Its 26 GiB VM plus the PDM LXC leave Proxmox little headroom. This is the tightest host, and #3071 step 8 plans to convert it to bare metal (`hp-elite-gen13`).
2. **The shed host (`.20`) has 24 GiB free.** Its VM uses 12 GiB of 31.1 GiB. The machine-class comment still describes a 16 GiB host. Growing the VM is possible, but the node is tainted for Wi-Fi-only workloads, so extra RAM only helps pods that tolerate that taint.
3. **GPU worker memory requests are at 68%**, the highest in the cluster. The descheduler now sheds nodes above 65% ([#3079](https://github.com/mitchross/talos-argocd-proxmox/pull/3079)).
4. **Threadripper reports 87–89 °C on `k10temp`.** The 2950X reports `Tctl` with a +27 °C offset, so the die is about 60–62 °C. That is normal under 49% load. Other hosts peak at 57–68 °C, and the minis at 44–50 °C.
5. **Control plane is still one VM.** The 1 → 3 move with both minis is the next planned change ([#3071](https://github.com/mitchross/talos-argocd-proxmox/issues/3071) step 4, draft [#3014](https://github.com/mitchross/talos-argocd-proxmox/pull/3014)).

## Limits

- Physical CPU and RAM come from node-exporter on each host. VM sizes come from the Omni machine classes and the October 15 VM table. Proxmox was not queried.
- "Memory requested" counts running pods only. Percentages are of allocatable memory.
- Disk serials stay out of this page. See the disk map for drive models and roles.
