# NAS hardware and performance

Start with the measured speeds below (2 minutes). Keep the existing RAM.
The September 20 tests compare physical-disk reads, warm RAM-cache reads, and
writes that request a final flush on all three data pools.

**Status:** historical, measured September 20, 2026. The NAS RAM (12× 32 GB at 1600 MT/s) and
its bandwidth were re-measured on November 3; see the
[fleet inventory](inventory/2026-11-03-fleet-inventory.md).

Original status: measured September 20, 2026. Historical network results and older
permissions are labeled separately. Recommendations are not deployed changes.

**Scope:** NAS-local tests on new disposable datasets. No raw devices, boot-pool
writes, production-file writes, global cache flushes, or ARC limit changes.
These results inform NAS purchases; they do not benchmark the whole Kubernetes,
SMB, NFS, or iSCSI path. See [storage architecture](storage-architecture.md)
for the deployed storage policy.

## Measured speeds: September 20

All sequential runs processed 4 GiB, with one job and queue depth one.
MB/s uses decimal megabytes. These are short, matched workload measurements,
not steady-state or maximum-concurrency ratings. Verdicts use drive-class
specifications, not a matched industry-average benchmark; the source links and
comparison limits are in [the drive comparison](#compared-with-the-actual-drive-specifications).

| Pool | Write + final flush | Disk read, direct | Disk read, prefetch | Warm RAM ARC read | Verdict / industry reference |
|---|---:|---:|---:|---:|---|
| BigTank | 203.4 MB/s | 254.9 MB/s | 480.4 MB/s | 5.34 GB/s | **Normal HDD bulk speed**; writes modest for two mirrors. HGST rates one He10 at ~249 MB/s sustained. |
| ai-pool | 396.3 MB/s | 274.1 MB/s | 1,066.0 MB/s | 5.50 GB/s | **Fast reads, modest writes**. One HP/Samsung SATA SSD is rated ~550 MB/s read / ~520 MB/s write. |
| Backup10T | 170.5 MB/s | 190.5 MB/s | 203.5 MB/s | 5.50 GB/s | **Normal single-HDD speed**. Read is ~80% of Seagate's 254 MB/s best-case transfer rating. |

Physical counters confirmed approximately 4 GiB of disk reads in each sequential disk-read
phase and zero physical reads in each warm ARC repeat. BigTank's write phase
produced about 8.1 GiB of physical writes, consistent with two copies in mirrors.

### Small random requests and durable writes

| Pool | 4 KiB disk read IOPS | Read p99 latency | Write + fsync IOPS | Mean write + fsync cycle | Verdict / industry reference |
|---|---:|---:|---:|---:|---|
| BigTank | 97.9 | 108.53 ms | 61.2 | 16.34 ms | **Slow for busy VMs/databases**; mean read ~10.2 ms is mechanical-class, p99 is long. HGST: 8 ms seek + 4.16 ms rotation. |
| ai-pool | 1,502.5 | 1.02 ms | 415.9 | 2.40 ms | **Much faster than HDDs**; raw Samsung QD1 reference is 10K read IOPS, but does not include this 128 KiB record amplification. |
| Backup10T | 130.3 | 19.79 ms | 123.3 | 8.11 ms | **HDD-limited**; Seagate's 170/370 read/write IOPS is QD16, not a matched QD1/fsync comparison. |

These requests access 128 KiB ZFS records. Reading 4 KiB can cause a much
larger physical read. Do not compare this directly with a drive vendor's raw
4 KiB benchmark. Write IOPS include an `fsync` after every operation. The
separate fsync latency in the raw results is not the whole write cycle.

Warm ARC random reads reached 173,072 IOPS on BigTank, 177,745 on ai-pool,
and 166,158 on Backup10T, with no physical reads. That demonstrates caching
for this 4 GiB working set, not that every installed gigabyte is necessary.

[Download compact results](assets/nas-benchmarks/2026-09-20/summary.json) ·
[Full fio output and exact arguments](assets/nas-benchmarks/2026-09-20/results.jsonl)


## Is this NAS fast or slow?

**Good for bulk files. HDD latency is the weak fit for busy VMs and databases.**
The SSD pool reads quickly, but it has no redundancy, so it is a poor default
for irreplaceable state. The tests did not show CPU capacity as a NAS bottleneck.

| Workload | Verdict from this run | What to consider |
|---|---|---|
| Large files, media, backup copies on BigTank | Reasonable HDD-class throughput: 480 MB/s reads, 203 MB/s flushed writes | Keep it. Schedule competing backups and judge actual completion windows |
| Random uncached VM/database access on BigTank | Slow relative to SSDs: 98 QD1 read IOPS, 108.5 ms read p99; 61 fsync writes/s | Prefer a measured, redundant SSD path for latency-sensitive state |
| Repeated hot reads | Very fast locally: 5.34–5.50 GB/s from RAM | Keep RAM now. Network clients cannot receive data faster than their link |
| Large model files on ai-pool | Good measured aggregate read rate: 1.07 GB/s | The current stripe suits only data you can lose or re-download. The 396 MB/s writes deserve a longer representative test if write speed matters |
| Backup10T | Plausible single-HDD result: 203 MB/s reads, 171 MB/s writes | Capacity/staging tier, not high-availability primary storage |

### Compared with the actual drive specifications

| Drive | Manufacturer's reference | Comparison boundary |
|---|---|---|
| HGST He10 10 TB | Typical sustained 249 MB/s per drive; 8 ms read seek + 4.16 ms average rotation | BigTank's ~10.2 ms mean random-read completion is in mechanical-latency territory. Four advertised rates are not a guaranteed ZFS pool rate. |
| Seagate ST10000NM0096 | Up to 254 MB/s at the outer diameter | 203 MB/s buffered disk reads are plausible on an allocated, live filesystem. They are not evidence of a failing disk. |
| HP S700 500 GB | Up to 564/518 MB/s sequential read/write | Vendor conditions differ from one ZFS job on a mixed three-drive pool. |
| Samsung 860 EVO 1 TB | Up to 550/520 MB/s; random reads 10K IOPS at QD1 versus 98K at QD32 | Queue depth and block size matter. This test's 128 KiB records do not reproduce raw-device 4 KiB conditions. |
| P3-512 | Live evidence establishes SATA 6 Gb/s, vendor identity unconfirmed | Do not apply Crucial P3 NVMe specifications to this SATA device. |

Sources: [HGST He10 datasheet](https://documents.westerndigital.com/content/dam/doc-library/en_us/assets/public/western-digital/product/data-center-drives/ultrastar-hdd-sata-series/ultrastar-he10/data-sheet-ultrastar-he10.pdf),
[Seagate Enterprise Capacity v6 datasheet](https://www.seagate.com/www-content/datasheets/pdfs/ent-cap-3-5-hdd-10tb-channelDS1863-6C-1701US-en_US.pdf),
[HP/Biwin S700 specification](https://hp.biwintech.com/u_file/photo/20220916/HP-S700-2.5-Specifications.pdf),
[Samsung 860 EVO datasheet](https://download.semiconductor.samsung.com/resources/data-sheet/Samsung_SSD_860_EVO_Data_Sheet_Rev1.pdf).
These are specification comparisons, not an industry percentile or matched lab shootout.

A 10 GbE link has an arithmetic ceiling of 1.25 GB/s before overhead. The old
1,119 MB/s TCP result equals 8.95 Gb/s. The SSD disk result approaches that
ceiling, and warm ARC exceeds it. A 2.5 GbE client has a 312.5 MB/s
arithmetic ceiling. The old claim that the network "cannot become a bottleneck"
was incorrect.

### Translating speeds into users

"User" is not a storage workload. Ten people watching cached video, ten people
copying large files, and ten database writers need different resources.
These are bandwidth-budget examples, not load-tested simultaneous-user limits:

| Example | Aggregate demand | Reading the result |
|---|---:|---|
| 10 direct-play streams at 100 Mb/s each | 125 MB/s | ~26% of BigTank's single-stream prefetch result; concurrent seek patterns, network, and transcoding still need testing |
| 40 direct-play streams at 25 Mb/s each | 125 MB/s | Same bandwidth; four times the independent requests may alter disk behavior |
| 4 file readers at 50 MB/s each | 200 MB/s | ~42% of the sequential read result; client links and concurrency matter |
| 2 file writers at 50 MB/s each | 100 MB/s | ~49% of the flushed sequential write result; leave room for backups and other traffic |
| Small database transactions or Kubernetes control-plane writes | No reliable users-per-second conversion | Use measured durable-write latency, real query/app tests and the workload's latency target |

These examples reserve substantial headroom. They do not model multi-file seeks,
cache misses, mixed reads/writes, transcoding CPU, or application locks.
For consolidation, use the [Proxmox and Kubernetes capacity assessment](inventory/2026-09-20-capacity-and-benchmarks.md).


## Four simultaneous bulk streams: measured

A separate follow-up ran at 17:58:44–17:59:51 UTC, using four new 1 GiB
files on a new BigTank scratch dataset. The reader comparison used those same
four files, with 4 GiB total per pass, data retention disabled and physical
reads verified. Conditions matched the first suite except job and file count.

| Test | Aggregate MB/s | Per-stream MB/s |
|---|---:|---:|
| One reader across four files | 434.3 | 434.3 |
| Four concurrent readers | 522.4 | 130.6–135.4 |
| Four concurrent writers, final fsync per job | 202.1 | 50.5–51.5 |

Four readers raised total throughput about 20%. Four writers shared roughly the
same total bandwidth as the earlier single writer. Aggregate throughput divides
total bytes by the longest fio job runtime; startup-inclusive wall rates were
416.2, 493.5, and 198.0 MB/s respectively.

For 1 MiB requests, read p99 rose from 31.9 ms with one reader to 95.9–106.4 ms
with four. Concurrent buffered writes showed 1.08-second p99 stalls; their cause
was not isolated. These are bulk request latencies, not application response times.
This was not a mixed read/write test, an SMB test, or a supported-user-count test.

The scratch dataset was deleted and independently checked absent. All pools
remained healthy. [Concurrency summary](assets/nas-benchmarks/2026-09-20/concurrency/summary.json)
· [Raw results](assets/nas-benchmarks/2026-09-20/concurrency/results.jsonl)
· [Executed script](assets/nas-benchmarks/2026-09-20/concurrency/run-remote.py).

## ARC is RAM; L2ARC is a separate device

**No L2ARC is installed.** The pool topology has no cache vdevs, and the kernel
reported `l2_ndev=0` and `l2_size=0`. An "L2ARC on versus off" result would need
hardware that this NAS does not have.

The useful test here is disk reads versus RAM ARC reads. Dataset-local
`primarycache=metadata` keeps file data out of ARC for the disk tests.
Metadata caching stays enabled. The warm-cache test changes only the scratch
dataset to `primarycache=all`, reads the file once, then repeats it.
All tests set `secondarycache=none`.

L2ARC caches reads. It is not a write-acceleration device. A separate log device
(SLOG) has a different job: synchronous-write intent logging. Do not buy either
just because a graph says the RAM cache is full.
[OpenZFS caching reference](https://openzfs.github.io/openzfs-docs/Basic%20Concepts/Pool%20Structure/Caching.html).

A prefetch-enabled disk read can record ARC demand hits as prefetched data is
consumed. The physical disk-byte counters separate
those reads from warm RAM reads. A high demand-hit count alone is not evidence.

## Hardware and pool inventory

| Component | Observed September 20 |
|---|---|
| Chassis | HP DL360 Gen9 |
| Processor | Xeon E5-2680 v4, 14 cores / 28 threads |
| Installed RAM | 12 × 32 GB ECC LRDIMM, 1600 MT/s; 384 GB installed |
| OS-usable RAM | 377.6 GiB |
| OS | `TrueNAS-26.0.0-MASTER+20260914-020141`, development build |
| ZFS | OpenZFS 2.4.3 |
| Network | 10 GbE path; historical TCP test below, not rerun in this pass |
| Cache/log additions | No L2ARC cache vdev or separate SLOG observed |

| Pool | Drive layout | Pool capacity | Allocated | Redundancy |
|---|---|---:|---:|---|
| BigTank | 4 × HGST HUH721010AL4200 10 TB SAS HDD, two mirrors | 18.2 TiB | 57% | One member can fail per mirror; both members of one mirror failing loses the pool |
| Backup10T | 1 × Seagate ST10000NM0096 10 TB HDD | 9.08 TiB | 68% | None |
| ai-pool | P3-512 512 GB + HP S700 500 GB + Samsung 860 EVO 1 TB SATA SSD, striped | 1.82 TiB | 75% | None; losing any member threatens the pool |
| boot-pool | Two mirrored SSDs | 222 GiB | 58% | Mirror; excluded from performance writes |

Pool capacities are ZFS pool figures, not a promise of the same writable dataset
capacity. BigTank reported 27% fragmentation and retained mappings from an earlier
vdev removal. Those facts do **not** establish the cause of a throughput limit.
Do not rebuild a pool based on that correlation alone.

Device names such as `/dev/sda` changed between inspections. Match disks by
persistent identifier or model and current `zpool status -P`, not an old letter.
All four pools were ONLINE with no known pool data errors at preflight.

## How much RAM is actually needed?

**384 GB is useful today. The minimum acceptable replacement size is unmeasured.**
A repeated read shows that caching helps. It does not show that the real working
set needs every gigabyte of the current cache.

| Observation | What it establishes |
|---|---|
| 17:16 UTC snapshot: 341.4 GiB ARC, 13.8 GiB other allocations, 22.3 GiB free | Most available memory is cache. "Other" includes OS, apps, kernel and other caches |
| 72-hour CPU mean 1.51%, p95 2.43% across ten-minute buckets | Substantial CPU headroom in the observed workload; averages hide short spikes |
| 72-hour demand-data hit rate 99.917% | Most counted demand requests hit cache; this is not a byte-weighted hit rate |
| RustFS about 3.2 GiB at inspection; peak ten-minute average 7.46 GiB | Reserve app peaks before allocating a future RAM budget to ARC |
| About 11 hours with ARC below 128 GiB and very high demand hits | A clue that some activity fits in less cache. The workload differed, so it is not a 128 GB replacement test |

Tailscale and monitoring used about 0.14 GiB combined. One configured 8 GB VM
was stopped. The five-minute passive sample showed no memory-pressure stalls
or ARC throttling, and no swap was configured. These were observations of the
existing workload, not a maximum-concurrency stress test.

### Future purchase priorities

1. **Keep the current RAM and improve cooling first.** Initial BigTank HDD
   temperatures were 58, 55, 54, and 43–44°C. Check airflow and trend comparable
   workloads. No temperature-caused failure was demonstrated.
2. **Choose drive layout for the workload.** Large media and backups and small durable
   VM and database requests have different needs. Use the sequential and random
   results separately. The SSD stripe is not redundant VM storage.
3. **Evaluate 128–256 GB only as expandable replacement candidates.** Reserve OS
   and app peaks. Keep 384 GB as the measured baseline. 64 GB is a larger,
   unvalidated cache tradeoff.
4. **Measure a representative week before buying.** Include backup, restore,
   Steam iSCSI, file opens, and concurrent users. Compare task duration, disk
   latency, memory peaks and cache misses, not cache occupancy alone.
5. **Validate a smaller cache budget in a separate planned test.** Define acceptable
   task times, record the original setting, warm up comparable workloads and
   restore the original budget if latency or pressure exceeds the target.
   An ARC cap is only an approximation of having less physical RAM.

The HP S700 had 816 lifetime CRC errors and the Samsung 860 EVO had four. No
matching recent kernel I/O errors were found in the inspection. Compare counter
deltas before diagnosing an active cable or controller fault. SMART passing does
not guarantee future reliability.

## Test method and reproducibility

The suite ran 17:45:56–17:54:58 UTC, using existing `fio` on the NAS.
Each data pool received one new, uniquely named scratch dataset with an 8 GiB
quota, `compression=off`, `sync=standard`, `recordsize=128K`, and `atime=off`.
All three scratch datasets were deleted and independently checked absent.
Production properties and global ARC limits were unchanged.

1. Write an allocated 4 GiB file, 1 MiB blocks, `psync`, one job, `end_fsync=1`.
2. Read it with `direct=1`, then with buffered prefetch. Keep data retention
   disabled with `primarycache=metadata` and `secondarycache=none`.
3. Run 15 seconds of 4 KiB direct random reads and 10 seconds of 4 KiB writes
   with `fsync=1` on the same scratch file.
4. Set only the scratch dataset's `primarycache=all`; warm the file, repeat the
   sequential read, then run 10 seconds of cached random reads.
5. Delete only the scratch dataset created by this run. Verify pool health,
   unchanged production properties, and absence of all three scratch datasets.

`end_fsync` requests persistence at the end. `fsync=1` requests it after each
write. One synchronous `psync` job is QD1 even if a larger `iodepth` is requested.
[Fio option definitions](https://fio.readthedocs.io/en/latest/fio_doc.html) and
[ZFS dataset properties](https://openzfs.github.io/openzfs-docs/man/master/7/zfsprops.7.html).

The file size is too small to prove long-run SSD behavior beyond device write
caches. The final flush is part of fio's reported write runtime. Physical-counter
brackets include process startup and occasional SMART polling overhead, so
those longer brackets are not the denominator for fio throughput. Production
traffic continued, so counter deltas can include that traffic and mirror copies.

**Reproduction prerequisites:** SSH access with appropriate NAS permissions,
healthy pools, sufficient free space, and a quiet agreed test window. Read the
[executed script](assets/nas-benchmarks/2026-09-20/run-remote.py) as a dated record.
Review its device mappings and choose a new unique dataset name for another run.
**Never substitute a production path or raw device for its scratch files.**

**Stop conditions:** new pool errors, a fio failure, a 180-second wall timeout,
or a SMART HDD temperature of 60°C during this run. That temperature was a
conservative testing guardrail, not a manufacturer failure threshold.
Check temperatures before and after each phase and during longer phases.

**Expected result:** allocated data, successful final flushes, physical reads
for disk phases, and near-zero physical reads for warm-cache repeats. A sparse
file or unexpected cache behavior invalidates the intended comparison.

**Failure/cleanup:** stop the workload, record the error, and remove only the
exact scratch dataset the run created, after verifying its identity. No
production setting needs rollback. The script's cleanup tracks created names
and refuses to adopt a pre-existing benchmark dataset.
[Independent final verification](assets/nas-benchmarks/2026-09-20/verification.json).


## From a Kubernetes pod over NFS: measured

This is the path apps use: a pod on the hp-sff worker (2.5 GbE) with a
fresh `truenas-nfs` volume (BigTank, `sync=standard`), next to a fresh local
`longhorn` volume on the same node. One run each, September 26.

| Test | NFS on the NAS | Longhorn (local SSD) |
|---|---:|---:|
| Create 2,000 files of 30 KB | 52 files/s | 493 files/s |
| Read those files back | 2,207 files/s | 25,533 files/s |
| Sequential write, 1 MiB direct | 30 MB/s | 71 MB/s |
| Sequential read, 1 MiB direct | 204 MB/s | 110 MB/s |
| 4 KiB random read, one at a time | 2,449 IOPS | 855 IOPS |
| 4 KiB random write + `fsync`, one at a time | 111 IOPS | 464 IOPS |

**Reading it:** the NAS wins at reading (its RAM cache) and loses at creating
files and durable writes, because each one waits for the HDD mirrors. It suits
read-mostly bulk data and does not suit databases. Placement
rules built on this are in the [disk map](domains/storage/disk-map.md#where-should-new-data-go).

**Network:** the NAS has one 10 GbE port, but only the Threadripper host also has
10 GbE. hp-sff and hp-elite connect at 2.5 GbE (about 312 MB/s at most). The
bare-metal minis and the shed host connect at 1 GbE. A pod's NFS speed is capped by its host's link.

## Earlier measurements: retained for context

These figures came from the previous performance reference. This page does not keep their full raw run
artifacts or exact collection timestamp, so
**they are not September 20 results or controlled regression baselines**.

| Earlier path | Read MB/s | Write MB/s | Limitation |
|---|---:|---:|---|
| Raw TCP, Proxmox `.14` ↔ NAS, one stream | 1,119 | n/a | No storage involved; MTU 1500 |
| NFS v4.2, one stream + readahead | 463 | 218 | `BigTank/k8s`, `sync=disabled` |
| NFS v4.2, four streams | 645 | 230 | Different concurrency from this pass |
| SMB 3.1.1, one stream + readahead | 634 | 141 | `BigTank/virtual-machines`, `sync=standard` |
| SMB 3.1.1, four streams | 408 | 174 | Different concurrency from this pass |
| 2.5 GbE workstation, raw TCP | 256 | n/a | A different client/link |

The NFS/SMB write rows do not isolate protocol cost, because the datasets had different
sync policies. Read results also mix mount options, concurrency and cache state.
The old explanation that NFS should accept a 4 MiB `rsize`, or that changing one
mount option would close the gap, was not demonstrated. It is not a tuning plan.
The live Kubernetes NFS StorageClass already uses `nconnect=16`; an old ad-hoc
mount without it does not describe that production path.

Earlier local sequential writes were BigTank 168 MB/s, Backup10T 203 MB/s and
ai-pool 243 MB/s; earlier BigTank disk reads were 408 MB/s. Old cache reads were
2.49, 2.47 and 2.89 GB/s respectively. Different files and methodology rule out
claiming an improvement or regression from the new test alone.

The first September 20 read-only sample used existing files: 1 GiB direct read
96.7 MB/s, 1 GiB first buffered read 273.9 MB/s, its cached repeat 4.84 GB/s,
and a 256 MiB SMB client-cache-bypassed read from `.14` at 219.7 MB/s. Those
small samples prompted the controlled all-pool rerun above. Do not use 96.7 MB/s
as BigTank's maximum or 4.84 GB/s as its disk speed.

## Source of truth

- Current layout/health: `zpool status -P` and `zpool list` on the NAS.
- Current properties: `zfs get` on the exact dataset; inheritance matters.
- Share definitions: `midclt call sharing.smb.query` and `sharing.nfs.query`.
- [Storage architecture](storage-architecture.md) and
  [kopiur backup architecture](domains/storage/kopiur-backup-architecture.md)
  own Kubernetes storage and recovery policy.
- [TrueNAS special-vdev stall runbook](truenas-special-vdev-stall-runbook.md)
  covers the earlier missing-pool/dashboard incident.

## Recorded sharing and permissions

**Purpose:** who can reach which data, and why. Use this model when adding a device or debugging "why can't this user read that file".

**Status:** retained configuration reference from the earlier inspection. The
September 20 benchmark did not revalidate every account, ACL, or share. Recheck
live permissions before changing them; benchmark datasets do not use these shares.

### The model in one sentence

Two groups define two tiers. **Only an account's group membership separates the tiers.**

| Account | UID | Groups | Reaches |
|---|---|---|---|
| `vanillax` | 3000 | `nas-public` + `nas-private` | everything |
| `k8-smb-user` | 3001 | `nas-public` + `nas-private` | everything |
| `proxmox` | 3002 | `nas-public` + `nas-private` | everything |
| `media-server` | 3003 | none | public tier, read-only |
| `truenas_admin` | 950 | not an SMB user | UI / SSH / API only |

`media-server` (TVs and appliances) is deliberately in no `nas-*` group. It
reads the public tier through the directory "other" bits and is blocked from the
private tier because those directories have no "other" bits at all.

**Why the appliance account is in no group rather than in `nas-public`:** POSIX
mode bits cannot distinguish two members of the same group. If the appliance
were in `nas-public`, then either the group has write and a TV can delete your
media, or it does not and your own account loses write too. Leaving the
appliance out of every group gives group = writers, other = readers, which is
the intent.

### Tiers

| Tier | Group | Mode | Datasets |
|---|---|---|---|
| Public | `nas-public` (3100) | `2775` | `k8s/jellyfin-media`, `k8s/tubearchivist`, `k8s/kiwix`, `k8s/versatiles`, and the `BigTank/k8s` parent |
| Private | `nas-private` (3101) | `2770` | `General`, `backup`, `photos`, `organized_backups`, `virtual-machines`, `proxmox`, `users`, `k8s/{frigate,ollama,rustfs,vanillax,volsync-kopia-nfs,llama-cpp-archive}`, `ai-pool/{comfyui,llama-cpp,vllm}` |

`2770` hides the data: with no "other" permission, an account outside
the group cannot traverse into the directory. `2775` grants the group write
and everyone else read. The leading `2` is setgid, so files created inside
inherit the directory's group instead of the creator's private group. That keeps
the tiers from drifting apart as data is written.

### Behaviour verified by the earlier inspection

The inspection ran commands as each account instead of reading modes:

| | `media-server` | `vanillax` | `k8-smb-user` |
|---|---|---|---|
| Public tier | read | write | write |
| Private tier | **no access** | write | write |

### Rules

- **Adding a device is one decision: which groups does it join?** An appliance
  joins none. A trusted machine joins both. There is no per-share configuration.
- **`BigTank/k8s` is a mixed container.** It holds public and private children.
  **Never apply a recursive `chmod`/`chgrp` at that level.** It re-opens the
  private children. Always scope to the individual leaf dataset.
- **The parent of a public dataset must stay traversable.** `BigTank/k8s` is
  `nas-public` for exactly this reason: if it were private, appliances could not
  traverse into the public datasets beneath it.
- `aclinherit` is `passthrough` on every pool. Do not set it back to `discard`.
  That stops new files inheriting and the tiers decay silently.

### Setting permissions through the API

`filesystem.setperm` rejects four-digit modes ("Please supply a value between
000 and 777"), so setgid cannot be applied through it. Use two passes:

```bash
# 1. group + base mode (recursive, strips stale ACLs)
midclt call -j filesystem.setperm \
  '{"path": "<path>", "uid": <uid>, "gid": 3101, "mode": "770",
    "options": {"stripacl": true, "recursive": true}}'

# 2. setgid on directories
sudo find <path> -type d -exec chmod g+s {} +
```

`stripacl: true` discards existing NFSv4 ACLs. That is intended here, because it
establishes a predictable mode-based baseline. It also removes hidden
grants. Before this work, `BigTank/General` showed mode `770 vanillax:vanillax`
while a different account had write through an invisible NFSv4 ACL. **On an
`nfsv4` dataset the mode you see is not necessarily the rule being enforced.**

### Known remaining inconsistencies

- **Two ACL models coexist.** `acltype=nfsv4` on BigTank and children;
  `acltype=posix` on Backup10T, ai-pool, and `BigTank/backup`. Do not change `acltype`
  casually on a populated dataset, so leave this as-is.
- **`Backup10T` root was `readonly=off` on September 20.** The earlier
  reference said `on`. Live inspection supersedes that statement. No production
  property was changed for the benchmark. Inspect individual replica datasets
  before assuming they are protected from ordinary writes.
- **Two unrelated locations are called "photos"**: the SMB share `photos` serves
  `/mnt/BigTank/organized_backups/photos`, while the NFS export
  `/mnt/BigTank/photos/All` serves the separate `BigTank/photos` dataset.
- **`jellyfin-media` is empty.** The public tier is real, but there is no film
  library on this NAS yet.

---
