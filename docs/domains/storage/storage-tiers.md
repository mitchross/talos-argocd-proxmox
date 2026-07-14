# Storage tiers — and why database flash must be node-local

**Status (2026-07-13):** a network-attached flash tier was **built, measured, and abandoned**.
This doc records why, so nobody rebuilds it.

## The rule

| Use | Class |
|-----|-------|
| **Anything RWO** — app state, caches, **and databases** | `longhorn` (default, node-local block) |
| Bulk media, model weights, hand-browsable, **RWX** | SMB / NFS classes (see `infrastructure/storage/CLAUDE.md`) |

**Do not add a network-attached block StorageClass for databases.** We tried. Numbers below.

## What we tried and what it cost

A `flashpool` on the NAS — 3x HPE MK000480GWCEV enterprise SATA SSD (power-loss protected),
RAIDZ1 — exported to Kubernetes over **NVMe-oF/TCP** via `truenas-csi` v1.1.1.

**The driver worked.** Talos v1.13 has `CONFIG_NVME_TCP=y` built in and nvme-cli ships inside the
driver image, so it attached `/dev/nvme0n1` in a pod with **no system extension and no reboot**.
That part was never the problem.

**The performance was.** 4K QD1 `fsync=1` — one database commit:

| | IOPS | per-op |
|---|---|---|
| Longhorn (consumer EDILOCA NVMe, local to Proxmox) | 259 | 3.86 ms |
| flashpool zvol, **local on the NAS** | **2,510** | 0.076 ms |
| flashpool zvol, **over NVMe-oF** (what a pod actually gets) | **437** | **2.29 ms** |

**1.7x over Longhorn.** Not the ~11x the local numbers promised.

**And it is not the network.** Measured: RTT Proxmox->NAS is **0.147 ms**; ZFS on the zvol is
**0.076 ms**. Those imply ~0.22 ms/op (~4,500 IOPS). We got **2.29 ms/op**.

The ~2ms is the *chain*: every fsync becomes
`ext4 journal write` -> `NVMe-oF FLUSH` -> `nvmet` -> `ZFS ZIL commit` -> ack — each a round trip,
and the ZIL commit is a real write to real disks.

**Why enterprise SANs don't have this problem:** a NetApp/Pure/PowerStore acknowledges a sync
write once it lands in **battery-backed NVRAM mirrored across two controllers** (~100us), then
destages later. It cheats, safely. ZFS is *honest* about durability and actually commits the log.
A NAS running ZFS is not a SAN array, and asking it to behave like one produces exactly the
numbers above.

**Databases fsync on every commit.** That makes them the single worst workload to put behind a
network. This is the opposite of the intuition that led us here ("databases are write-heavy, so
give them the fast write tier") — the write-heaviness is precisely what the network destroys.

## Three operational failures, in the first hour

Recorded because any one would bite a future attempt:

1. **ext4 corruption** after a detach/reattach cycle (`UNEXPECTED INCONSISTENCY / Resize inode not
   valid`). Cause not fully isolated, but "maybe it corrupts volumes" is not acceptable under a
   database.
2. **Child datasets silently unmounted** (`flashpool/k8s/flash` had a mountpoint but was not
   mounted) -> *all* provisioning failed with `[ENOENT] Path /mnt/flashpool/k8s/flash not found`.
   This would return after every NAS reboot.
3. **Leaked NVMe-oF exports** — `csi-*` nvmet subsystems and namespaces survived PVC deletion,
   including from a *failed* provision. Had to be reaped by hand.

## Where the flash actually belongs: local to the node

The drives are not the problem — the *location* was. Raw, no stack, no network:

| 4K QD1 fsync, RAW device | IOPS | avg | p99 |
|---|---|---|---|
| **EDILOCA EN605** (consumer NVMe — currently holds every DB) | **697** | 0.299 ms | **2.83 ms** |
| **HPE enterprise SATA** (PLP) | **14,484** | 0.064 ms | **0.146 ms** |

**20.8x — and that is the bare drive, with Longhorn and the network removed.** Longhorn turns 697
into 259 (real overhead), but the *drive* is the primary bottleneck. The EDILOCA is DRAM-less with
no power-loss protection; its 1M sequential write is 109 MB/s and its QD32 p99 is **78 ms**.

**The fix is to put the enterprise SSDs in the Proxmox host**, on a PCIe SATA HBA (the X399
chipset SATA ports are unreliable), and tier Longhorn with disk tags:

| Disk | Wins at | Give it |
|---|---|---|
| EDILOCA NVMe x2 | **reads** (161k IOPS, 2310 MB/s) | app state, caches, read-heavy |
| Enterprise SATA x3 (PLP) | **writes** (20x fsync, p99 0.146ms) | **databases** |

Everything stays node-local: no network hop, no second CSI driver, no NVMe-oF, no rebuilt backup
path. It also takes Longhorn from ~1TB to ~2.44TB, relieving the thin-pool pressure.

This is also what modern Kubernetes-on-metal actually does — OpenShift Data Foundation, Portworx,
and vSAN all pool **local** NVMe and replicate in software, rather than front a SAN. Kubernetes
already handles replication at the app layer; shared-array semantics are redundant.

## The real single point of failure (unchanged by any of this)

`defaultClassReplicaCount: 1` on a single worker node. No storage protocol fixes that.
