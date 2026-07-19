# Storage tiers

The cluster has four storage tiers, **classified by what the hardware is** — not by
which app uses them. Pick a class by the volume's access pattern.

| Class | Backing hardware | Character | Use for |
|-------|------------------|-----------|---------|
| `longhorn` (**default**) | Threadripper EDILOCA NVMe plus the Dell Talos system SSD | local RWO; Threadripper tier is **read-strong**, Dell is a small Wi-Fi-site failure domain | app state, caches, read-heavy volumes, big sequential-write DBs (ClickHouse, Prometheus TSDB, Loki) |
| `longhorn-flash` | Proxmox 2× enterprise SATA SSD, PLP, mdadm RAID1, **thick** LVM | fast local flash, **write-strong** (PLP), RWO | anything fsync-heavy: Postgres/MySQL commits, WAL, Kafka, Redis AOF, message queues |
| `truenas-nfs` | TrueNAS HDD (BigTank) | network bulk, **RWX** | shared volumes, rebuildable tile/grid caches |
| `*-smb` / static NFS | TrueNAS HDD / ai-pool SSD | network SMB/NFS shares | media libraries, model weights, hand-browsable data |

**The two local tiers have opposite strengths** (measured — see below): the enterprise
SATA wins durable writes ~12×; the EDILOCA NVMe wins reads ~2–3×. So they are two
distinct classes, and you choose per volume:

- **fsync-sensitive → `longhorn-flash`.** Every commit is a durable write; that is where
  the enterprise SSD's power-loss protection pays off.
- **read-heavy or big-sequential-write → `longhorn` (default).** The NVMe reads far
  faster, and sequential write on this host's X399 chipset SATA is only ~65–92 MB/s.
- **shared (RWX) → NFS/SMB.** Neither local block tier can be RWX safely.
- **when in doubt → `longhorn` default.**

## The rule that matters most in practice: get small-block RANDOM IO off the HDD

The biggest real-world storage win here is **not** flash-vs-NVMe (that difference is marginal, and
Longhorn caps fsync ~200 IOPS on both — see below). It is **HDD-NFS → local SSD** for the right
workload:

- **Small-block RANDOM IO on HDD-backed NFS (`truenas-nfs` / SMB on BigTank) is catastrophic** —
  measured **102 IOPS @ 310ms** on BigTank. A workload that reads/writes many small files with
  random access (a tile renderer, a search index, a small database) will *thrash* there.
- The same workload on **local SSD is thousands of IOPS at sub-ms** — a 20–100× win, from *either*
  local tier. Use `longhorn-flash` for it specifically, so the thrashing lands on the separate SSD
  spindle and stays **off** the shared NVMe disk the databases use.
- **Large SEQUENTIAL IO on HDD-NFS is fine** — jellyfin, frigate, tubearchivist, kiwix stream large
  media files, and HDDs do sequential throughput well (~160+ MB/s). Leave them on SMB/NFS.

So the question isn't "which apps deserve flash" — it's **"which apps do small-block random IO and
are currently on HDD-NFS."** First mover: **radar-ng** (`tiles`/`grids`/`state`/`pmtiles`), moved
from `truenas-nfs` (HDD) to `longhorn-flash` (SSD, RWO) on 2026-07-15. It was the textbook case — a
tile renderer thrashing thousands of small PNG/MVT files on 102-IOPS spinning disk over NFS.

### The second use of `longhorn-flash`: IO isolation for noisy write-heavy apps

`longhorn-flash` is also a *separate physical spindle*, so it doubles as an isolation lane. Apps
that are **write-heavy but read-tolerant** — metrics, logs, disposable analytics — are moved here
NOT because flash is faster (through Longhorn it isn't; ~200 fsync either way, and SATA reads
slower), but so their heavy IO stops contending with the latency-sensitive databases on the shared
NVMe disk. Moved 2026-07-15: **all of PostHog** (clickhouse/postgres/redis/kafka — disposable
product analytics) and **all of monitoring** (Prometheus TSDB, Alertmanager, Grafana, Loki
write/backend). All backup-exempt; their history is disposable (Loki/Tempo data lives on S3/RustFS
anyway), so the migration is a clean delete+recreate.

Net effect: the shared NVMe disk (`longhorn` default) is left for the databases and latency-
sensitive volumes; the flash spindle absorbs the noisy random/write-heavy IO. Two disks, workloads
split by profile.

RWX→RWO note: those PVCs were RWX only for multiple writer pods. Kubernetes RWO is per-*node*, so on
a single-node cluster co-located pods share one RWO volume (the proven `openmeteo-data` pattern).
Before going multi-node, pin the consumers with podAffinity or move back to a real RWX class.

## Do not put fsync-sensitive storage behind the network

Below the tier table is the record of a network-attached flash tier that was **built,
measured, and abandoned** — because sync writes do not survive a network hop. It is
kept so nobody rebuilds it. The node-local `longhorn-flash` tier above is the answer
that replaced it.

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

## The real single point of failure (unchanged until replica policy changes)

The Dell provides a second schedulable Longhorn disk, but the `longhorn`
StorageClass and existing volumes still request one replica. Capacity on two
nodes is not redundancy: selected volumes must move to two replicas before
they survive losing either Proxmox host. That trade-off is explicit because
the second synchronous replica crosses the Wi-Fi media bridge.
