# Fleet inventory — November 3, 2026

**Purpose:** the current list of machines in the lab: what is inside them, how fast they are, what
they cost to run, and what runs on them.
**Status:** dated, read-only snapshot. It replaces the [October 27 inventory](2026-10-27-fleet-inventory.md)
as the current page. Disks are maintained in the [disk map](../domains/storage/disk-map.md).

How it was collected, all on November 3:

- **Cluster, RAM, NVMe models:** the Kubernetes API, Omni `MachineStatus` and Prometheus. These
  queries ran separately, so this is not an atomic snapshot.
- **Proxmox host and TrueNAS details** (DIMMs, PCIe links, `fio`, RAM bandwidth, PSU): read-only
  commands over SSH. Nothing was written to a pool or a disk.
- **Power:** Home Assistant plug sensors, last calendar month.

## What changed since October 27

- **Talos is v1.14.5** on all 7 nodes (was v1.14.4). Kubernetes is still v1.37.1.
- **Two more mini PCs were added** (one HP, one Dell). They are not in Omni or Prometheus yet. See
  [New machines](#newest-machines).
- **New measurements:** DIMM layout and speed, PCIe link widths, NVMe `fio`, RAM bandwidth and
  power per plug are on this page for the first time.
- **`hp-elite-gen13` shows a second NVMe**, a WDC SN530 256 GB, next to the Intel 660p. Its role
  was not checked.

## Physical machines

| Machine | Address | CPU | RAM | Platform | Runs |
|---|---|---|---:|---|---|
| Threadripper (X399 Taichi) | `.14` | Ryzen TR 2950X · 16 cores, 32 threads | 125.7 GiB (8× 16 GB) | Proxmox VE 9 | GPU worker VM (30 vCPU, 100 GiB, 2× RTX 3090), a `kali-linux` VM (12 GB) |
| HP ProDesk 600 G4 SFF | `.21` | i5-8500 · 6 threads | 62.6 GiB | Proxmox VE 9 | **control plane** VM (4 vCPU, 12 GiB) + worker VM (6 vCPU, 40 GiB) |
| HP ProDesk 600 G4 DM (shed) | `.20` | i5-8500T · 6 threads | 31.1 GiB | Proxmox VE 9 | worker VM (4 vCPU, 12 GiB), USB radios, Wi-Fi bridge |
| Dell Pro Micro QCM1250 | `.181` | Core Ultra 5 245T · 14 cores, iGPU + NPU | 32 GB (2× 16 GB) | Talos v1.14.5 bare metal | worker `mini-pc-dell-ultra-worker` |
| HP Elite Mini 800 G9 | `.82` | i5-12500T · 12 threads | 16 GB (2× 8 GB DDR5-4800) | Talos v1.14.5 bare metal | worker `hp-elite-gen12`, Zigbee stick |
| HP Elite Mini 600 G9 | `.88` | i5-13500T · 20 threads | 16 GB (1× 16 GB) | Talos v1.14.5 bare metal | worker `hp-elite-gen13` |
| HPE ProLiant DL360 Gen9 (TrueNAS) | `.133` | 1× Xeon E5-2680 v4 · 14 cores, 28 threads | 377.6 GiB (12× 32 GB) | TrueNAS 28.0 | NFS/SMB storage, kopiur repository |
| Raspberry Pi 5 | `.15` | Cortex-A76 · 4 threads | 7.7 GiB | Ubuntu 26.04 | Omni v1.12.4, 3 Proxmox providers, booter (PXE), Technitium DNS, ProxCenter |

The desktop (7800X3D, 64 GB DDR5, RX 6800) is not part of the cluster.

## Memory

| Machine | Slots used | DIMMs | Runs at | Note |
|---|---|---|---|---|
| Threadripper `.14` | 8 of 8 | 8× 16 GB DDR4, two mixed Corsair 3600 kits | **2133 MT/s** | The sticks are rated 3600. 2133 is AMD's official speed with 8 DIMMs. 128 GB is the board maximum. |
| DL360 `.133` | 12 of 24 (CPU1 only) | 12× 32 GB DDR4 quad-rank | **1600 MT/s** | Rated 2133. Three DIMMs per channel forces the lower speed. The CPU2 socket and its 12 slots are empty. |
| Dell Pro Micro `.181` | 2 | 2× 16 GB DDR5 | not read | — |
| Elite Mini 800 G9 `.82` | 2 | 2× 8 GB DDR5-4800 | not read | — |
| Elite Mini 600 G9 `.88` | 1 | 1× 16 GB | not read | One DIMM, so single channel. |

The Threadripper host has about 19 GiB free once the GPU VM (100 GiB) and the kali VM (12 GB) run.

## Bandwidth and speed

### RAM read bandwidth

| Machine | 1 thread | Best | At best threads |
|---|---:|---:|---:|
| Threadripper `.14` | 5.6 GB/s | 24.6 GB/s | 32 |
| DL360 `.133` | 5.3 GB/s | 32.1 GB/s | 8 |
| GPU worker VM (pod, AVX2 test) | — | 43 GB/s | 8 |

**Read these as floors, not as the hardware limit.**

- The host numbers come from parallel `dd` reads out of `/dev/shm`, because the hosts have no `gcc`.
  `dd` copies through the kernel, so it under-reports.
- The DL360 figure falls at 28 threads (14.7 GB/s). That is the `dd` method, not the memory.
- The 43 GB/s VM figure is capped by the pod's 8 CPUs.
- Theoretical peaks for comparison: Threadripper quad-channel at 2133 is about 68 GB/s. One DL360
  socket at 1600 is about 51 GB/s. These are calculated, not measured.

### NVMe on the Threadripper

Two EDILOCA EN605 512 GB drives, both PCIe Gen3 x4 and attached to the CPU. `fio --readonly`
on the raw device:

| Drive | Sequential 1 MiB | 9 MiB reads (model-file style) | Random 16 KiB | Wear |
|---|---:|---:|---:|---:|
| `nvme0` | 1.88 GB/s | 1.72 GB/s | 557 MB/s | 16% |
| `nvme1` | 2.12 GB/s | 1.83 GB/s | 448 MB/s | 20% |

Free space on the Proxmox side: `nvme1-vmstore` 459 GB, `nvme0-vmstore` 177 GB. `ssd-ent` and
`tr-sda-vmstore` are nearly full. `lspci` finds only these 2 NVMe drives.

Other disk speeds are in the [September 20 measurements](2026-09-20-capacity-and-benchmarks.md) and
[NAS performance](../nas-performance.md). Both are older.

### PCIe links

| Device | Slot can do | Running |
|---|---|---|
| RTX 3090 (×2) on the Threadripper | Gen3 x16 | **x8** (Gen1 speed at idle; links step up under load) |
| EN605 NVMe (×2) | Gen3 x4 | Gen3 x4 |
| DL360 slot 1 | Gen3 x16 | free |
| DL360 slot 2 | Gen3 | LSI SAS2308 disk controller |
| DL360 slot 3 | Gen3 | needs the CPU2 socket, which is empty |

The Threadripper also holds an ASM1166 SATA card in a PCIe slot.

## Power

Home Assistant plug sensors, **last calendar month** (`*_energy_last_month`). Cost is at the
current all-in rate of $0.2135/kWh. Summer rates are $0.235–0.285.

| Plug | kWh | Cost |
|---|---:|---:|
| Threadripper host (both 3090s) | 164 | $35.0 |
| TrueNAS DL360 | 84 | $17.9 |
| HP SFF + Optiplex | 59 | $12.6 |
| NAS drive PSU | 30 | $6.5 |
| HP Elite Mini G9 | 29 | $6.1 |
| Shed lab | 20 | solar |
| **Homelab total** | **366** | **$78** |
| Gaming PC | 86 | $18.3 |
| MacBook + monitor | 31 | $6.6 |

- **The homelab is about 32% of the house's kWh.** The house used 1,156 kWh ($247) last month.
- **Not on any plug:** the Pi, switches, router and access points.
- **The HP SFF + Optiplex plug covers three boxes:** the HP SFF host, the Dell Pro Micro and the
  Elite Mini 600 G9.
- **The Threadripper is the biggest item.** It averaged about 210–275 W over the month.
- The DL360 has one 500 W power supply, reading 110 W; its second bay is empty, so the BMC reports
  "redundancy lost".
- Live watts are not used for cost. They swing with load (the Threadripper plug read 401 W under load today).

## Newest machines

The two newest mini PCs joined the cluster about 12 days ago: **hp-elite-gen13**
(HP Elite Mini 600 G9, `.88`) and **mini-pc-dell-ultra-worker** (Dell Pro Micro, `.181`).
Both are on the HP SFF + Optiplex plug, so last month's 59 kWh includes them.

## Kubernetes nodes

Cluster `talos-prod-cluster-v2`: **7 nodes**, all Ready, Talos v1.14.5, Kubernetes v1.37.1.
Usage is a point-in-time `kubectl top` reading.

| Node | Host | CPU (alloc) | Memory (alloc) | CPU used | Memory used | Pods | Accelerators |
|---|---|---:|---:|---:|---:|---:|---|
| `talos-prod-cluster-v2-control-planes-7mxjxv` | `.21` VM | 3.95 | 11.1 GiB | 0.60 | 7.1 GiB | 22 | — |
| `talos-prod-cluster-v2-gpu-workers-jxfkdr` | `.14` VM | 29.95 | 97.7 GiB | 4.63 | 45.7 GiB | 79 | `nvidia.com/gpu=2` |
| `talos-prod-cluster-v2-hp-sff-workers-h76ncc` | `.21` VM | 5.95 | 38.7 GiB | 0.84 | 19.7 GiB | 51 | `gpu.intel.com/i915` |
| `talos-prod-cluster-v2-hp-micro-workers-pstbbd` | `.20` VM | 3.95 | 11.2 GiB | 0.17 | 3.1 GiB | 14 | — |
| `mini-pc-dell-ultra-worker` | `.181` bare metal | 13.25 | 29.3 GiB | 2.95 | 16.6 GiB | 54 | `gpu.intel.com/i915` |
| `hp-elite-gen12` | `.82` bare metal | 11.25 | 13.7 GiB | 0.59 | 7.1 GiB | 39 | `gpu.intel.com/i915` |
| `hp-elite-gen13` | `.88` bare metal | 19.25 | 13.2 GiB | 1.24 | 6.3 GiB | 59 | `gpu.intel.com/i915` |

"Pods" counts running pods. 103 of 104 Argo CD applications are Synced and Healthy; one is
OutOfSync. Longhorn has 67 volumes (60 attached and healthy, 7 detached). All 80 PVCs are Bound.
Per-node Longhorn disks are in the [disk map](../domains/storage/disk-map.md).

## Findings

1. **The Threadripper's RAM runs at 2133 MT/s with 3600-rated sticks.** Raising it in the BIOS
   (2666, then 2933, with a memtest pass) could add bandwidth. Untested; the kits are mixed and 8
   DIMMs is hard on a 2950X.
2. **The DL360 RAM runs at 1600 MT/s** because of three DIMMs per channel. Spreading DIMMs across
   two CPUs would let them run faster. Untested, and HPE's population rules apply.
3. **Both 3090s run at x8**, not x16. This is the board, not a setting.
4. **The Threadripper's NVMe is Gen3 and tops out near 2 GB/s.** A Gen4 drive would be capped by
   the Gen3 link.
5. **The Intel 660p is past its rated writes** (see the [disk map](../domains/storage/disk-map.md)).
6. **The X399 chipset has been failing since 2026-08-28.** Both NVMe drives are
   CPU-attached, so this does not touch them.

## Open questions

- What models are the two new mini PCs, and which plug are they on?
- Does the Threadripper have a third NVMe (maybe in a chipset M.2 slot)? `lspci` finds two.
- The second, out-of-service DL360: CPU, DIMM count and type, what is broken, and does its PSU work?

## Limits

- Proxmox host CPU temperatures, uptime and the NAS pool layout were not re-collected. Pool
  layout is in the [October 15 inventory](2026-10-15-full-inventory.md).
- Mini PC DIMM speeds were not read.
- Power covers plugged devices only.
- Disk serials stay out of this page.

## History

Earlier snapshots are listed in [Inventory](index.md#history). The October 21 and 22 snapshots were
deleted; their content is superseded by this page and stays in git history.
