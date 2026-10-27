# Fleet inventory — October 22, 2026

**Purpose:** list every machine in the lab, with what runs on it and how loaded it is.
**Status:** dated, read-only snapshot, replaced by the [October 27 inventory](2026-10-27-fleet-inventory.md).
It replaced the [October 21 inventory](2026-10-21-fleet-inventory.md)
as the current host list. Disks are maintained in the [disk map](../domains/storage/disk-map.md).

Collection: about 04:40 UTC, from the Kubernetes API (`kubectl get nodes`, `kubectl top nodes`,
running pods), Longhorn objects and Omni `MachineStatus`. Queries ran separately, so this is not an
atomic snapshot. CPU and memory use are point-in-time `kubectl top` values. Host CPU temperatures,
Proxmox host RAM and NAS pools were not re-collected; the Proxmox hosts did not change.

## What changed since October 21

- **HP Elite Mini 600 G9 (`.22`) is bare-metal Talos** as `hp-elite-gen13` ([#3087](https://github.com/mitchross/talos-argocd-proxmox/pull/3087)). Proxmox, its worker VM, the Proxmox Datacenter Manager LXC, the `proxmox-hp-elite` provider and the `hp-elite-worker` machine class are gone. The node keeps the class label `hp-elite-worker`.
- **One 16 GB DIMM moved** from the 600 G9 to the Dell Pro Micro. The Dell now has 2× 16 GiB; the 600 G9 has 1× 16 GiB.
- **New Longhorn disks:** the 600 G9's Intel 660p (`hp-elite-nvme`), the Dell's Apple SATA SSD (`dell-ultra-ssd`, [#3089](https://github.com/mitchross/talos-argocd-proxmox/pull/3089)) and the hp-sff spare 1 TB PNY (`hp-sff-ssd2`, [#3090](https://github.com/mitchross/talos-argocd-proxmox/pull/3090)). Every disk except the system disks and the Wi-Fi shed node now takes replicas.
- **The USB Coral is retired.** The Zigbee stick is in `hp-elite-gen12`, where Home Assistant runs. Frigate moves to the Dell NPU ([#3088](https://github.com/mitchross/talos-argocd-proxmox/issues/3088)) and is `Pending` until then.
- Six volumes had their only copy on the 660p. `container-registry/registry` was restored from kopiur. Four backup-exempt caches were recreated empty. `nginx-example/storage` (demo, no Argo CD owner) is still faulted. Tracking: [#3071](https://github.com/mitchross/talos-argocd-proxmox/issues/3071).

## Physical machines

| Machine | Address | CPU | RAM | Platform | Runs |
|---|---|---|---:|---|---|
| Threadripper (X399) | `.14` | Ryzen TR 2950X · 32 threads | 125.7 GiB | Proxmox VE 9 | GPU worker VM (30 vCPU, 100 GiB, 2× RTX 3090) |
| HP ProDesk 600 G4 SFF | `.21` | i5-8500 · 6 threads | 62.6 GiB | Proxmox VE 9 | **control plane** VM (4 vCPU, 12 GiB) + worker VM (6 vCPU, 40 GiB) |
| HP ProDesk 600 G4 DM (shed) | `.20` | i5-8500T · 6 threads | 31.1 GiB | Proxmox VE 9 | worker VM (4 vCPU, 12 GiB), USB radios, Wi-Fi bridge |
| **Dell Pro Micro QCM1250** | `.181` | Core Ultra 5 245T · 14 cores, iGPU + NPU | 32 GiB (2× 16 GB) | Talos v1.14.4 bare metal | worker `mini-pc-dell-ultra-worker` |
| **HP Elite Mini 800 G9** | `.82` | i5-12500T · 12 threads | 16 GiB (2× 8 GB) | Talos v1.14.4 bare metal | worker `hp-elite-gen12`, Zigbee stick |
| **HP Elite Mini 600 G9** | `.88` (DHCP; was `.22`) | i5-13500T · 20 threads | 16 GiB (1× 16 GB) | Talos v1.14.4 bare metal | worker `hp-elite-gen13` |
| HPE ProLiant DL360 Gen9 (TrueNAS) | `.133` | Xeon E5-2680 v4 · 28 threads | 377.6 GiB | TrueNAS 28.0 | NFS/SMB storage, kopiur repository |
| Raspberry Pi 5 | `.15` | Cortex-A76 · 4 threads | 7.7 GiB | Ubuntu 26.04 | Omni v1.12.4, 3 Proxmox providers, booter v0.4.0 (PXE), Technitium DNS, ProxCenter |

## Kubernetes nodes

Cluster `talos-prod-cluster-v2`: **7 nodes**, all Ready, Talos v1.14.4, Kubernetes v1.37.1.

| Node | Host | CPU (alloc) | Memory (alloc) | CPU used | Memory used | Memory requested | Pods | Accelerators |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `talos-prod-cluster-v2-control-planes-7mxjxv` | `.21` VM | 3.95 | 11.0 GiB | 0.72 | 6.7 GiB | 4.2 GiB | 20 | — |
| `talos-prod-cluster-v2-gpu-workers-jxfkdr` | `.14` VM | 29.95 | 97.6 GiB | 5.77 | 40.5 GiB | 58.3 GiB (60%) | 75 | `nvidia.com/gpu=2` |
| `talos-prod-cluster-v2-hp-sff-workers-h76ncc` | `.21` VM | 5.95 | 38.6 GiB | 1.75 | 16.5 GiB | 19.0 GiB (49%) | 52 | `gpu.intel.com/i915=4` |
| `talos-prod-cluster-v2-hp-micro-workers-pstbbd` | `.20` VM | 3.95 | 11.1 GiB | 0.17 | 3.5 GiB | 2.5 GiB | 20 | — |
| `mini-pc-dell-ultra-worker` | `.181` bare metal | 13.25 | 29.2 GiB | 0.87 | 10.2 GiB | 13.5 GiB (46%) | 69 | `gpu.intel.com/i915=4`, NPU extension (no device plugin yet) |
| `hp-elite-gen12` | `.82` bare metal | 11.25 | 13.6 GiB | 1.05 | 5.7 GiB | 6.9 GiB (51%) | 40 | `gpu.intel.com/i915=4` |
| `hp-elite-gen13` | `.88` bare metal | 19.25 | 13.2 GiB | 0.78 | 2.3 GiB | 5.7 GiB (43%) | 24 | `gpu.intel.com/i915=4` |
| **Total** | | **87.55** | **214.3 GiB** | **11.1** | **85.4 GiB** | **110.1 GiB** | **300** | |

"Memory requested" counts running pods only.

## Storage

**Longhorn:** 66 volumes; 59 attached and healthy, 6 detached (normal), 1 faulted
(`nginx-example/storage`). All 78 PVCs are Bound.

| Node | Longhorn disk | Scheduling | Size | Free | Scheduled (requested) |
|---|---|---|---:|---:|---:|
| GPU worker | `gpu-bulk` | on | 799.6 GiB | 753.2 GiB | 528 GiB |
| GPU worker | `ssd-flash` (PLP, `clone-ok`) | on | 439.8 GiB | 291.8 GiB | 482 GiB (over-provisioned) |
| hp-sff worker | `hp-sff-ssd` | on | 689.6 GiB | 607.2 GiB | 376 GiB |
| hp-sff worker | `hp-sff-ssd2` (new) | on | 919.5 GiB | 898.6 GiB | 61 GiB |
| `hp-elite-gen13` | `hp-elite-nvme` (Intel 660p, worn) | on | 476.7 GiB | 467.4 GiB | 0 |
| `mini-pc-dell-ultra-worker` | `dell-ultra-ssd` (new) | on | 233.6 GiB | 226.0 GiB | 20 GiB |
| hp-micro worker | `hp-micro-ssd` | **off** (Wi-Fi node) | 849.5 GiB | 833.2 GiB | 0 |
| `hp-elite-gen12` | — | compute-only | — | — | — |

Each node also has a `talos-ephemeral` disk with scheduling off. Over-provisioning is 200%,
so `ssd-flash` booking more than its size is allowed; its large users are pinned by the
`flash` disk selector. New replicas and rebuilds land on the new disks.

## GitOps health

98 Argo CD applications: 93 Synced/Healthy. Three are Progressing while pods restart after
the volume recovery (`database-redis-instance`, `my-apps-paperless-ngx`, and `my-apps-frigate`,
which waits on [#3088](https://github.com/mitchross/talos-argocd-proxmox/issues/3088)).
`my-apps-posthog` is OutOfSync (Healthy), and `root` reports Degraded from its children.

## Findings

1. **Monitoring still scrapes the old `.22` Proxmox host** (`physical-node` exporters in
   `monitoring/metrics/prometheus-stack/values.yaml`, its network policy, and
   `host-monitoring/inventory.yaml`). Those targets are down now. Remove them or point them at
   the bare-metal nodes.
2. **`hp-elite-gen13` and `hp-elite-gen12` have 13.2–13.6 GiB allocatable.** A second DIMM
   doubles either one. The Dell has 29.2 GiB after the DIMM move.
3. **Control plane is still one VM.** The 1 → 3 move with the minis is the next planned change
   ([#3071](https://github.com/mitchross/talos-argocd-proxmox/issues/3071) step 4).
4. **The Intel 660p is past its rated writes.** It is the first disk to replace; see the
   [disk map](../domains/storage/disk-map.md).

## Limits

- Proxmox host RAM, CPU temperature and uptime were not re-collected; they did not change since
  the [October 21 inventory](2026-10-21-fleet-inventory.md).
- Bare-metal RAM comes from Omni `MachineStatus` memory modules.
- Disk serials stay out of this page. See the disk map for drive models and roles.
