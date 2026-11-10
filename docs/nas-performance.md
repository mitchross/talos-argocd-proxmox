# NAS performance and RAM

This page answers three questions about the TrueNAS box: how fast it is, what limits it,
and what to buy or not buy for it. Read the short answer first. The measurements that
support it follow.

The NAS-local numbers were measured on September 20, 2026, and the pod numbers on
September 26. The NAS RAM (12× 32 GB at 1600 MT/s) and its bandwidth were measured again
on November 3. Those results are in the
[fleet inventory](inventory/2026-11-03-fleet-inventory.md).

## The short answer

The NAS is good for bulk files and slow for databases.

- **How fast is it?** On the NAS itself, the BigTank HDD pool reads large files at
  480 MB/s and writes them at 203 MB/s. Data that is already in the RAM cache reads at
  more than 5 GB/s. Small random reads from the HDDs reach only about 98 per second.
- **What does an app see?** A pod on a 2.5 GbE host reads a large file over NFS at
  204 MB/s. It creates only 52 small files per second and does 111 durable writes per
  second. A local Longhorn volume does 493 and 464.
- **What limits it?** HDD seek time limits small reads and every durable write. The
  client's network link limits cached reads: a 10 GbE client cannot pass 1.25 GB/s and a
  2.5 GbE client cannot pass 312.5 MB/s. The CPU is not a limit. Its 72-hour mean load was
  1.51%.
- **What should you put on it?** Put bulk, read-mostly files on it. Do not put databases,
  Docker or overlay storage, or search indexes on it. The
  [disk map](domains/storage/disk-map.md#where-should-new-data-go) has the placement table.
- **What should you buy?** Keep the 384 GB of RAM. Improve cooling before anything else.
  Do not buy an L2ARC or SLOG device because a graph shows the RAM cache is full. Measure
  a representative week before any purchase. See
  [purchase priorities](#purchase-priorities).

The SSD pool, ai-pool, reads fast but has no redundancy. One dead disk loses the pool.
Use it only for data that you can download again.

| Workload | Verdict from this run | What to consider |
|---|---|---|
| Large files, media, backup copies on BigTank | Reasonable HDD-class throughput: 480 MB/s reads, 203 MB/s flushed writes | Keep it. Schedule competing backups and judge actual completion windows |
| Random uncached VM/database access on BigTank | Slow relative to SSDs: 98 QD1 read IOPS, 108.5 ms read p99; 61 fsync writes/s | Prefer a measured, redundant SSD path for latency-sensitive state |
| Repeated hot reads | Very fast locally: 5.34–5.50 GB/s from RAM | Keep RAM now. Network clients cannot receive data faster than their link |
| Large model files on ai-pool | Good measured aggregate read rate: 1.07 GB/s | The current stripe suits only data you can lose or re-download. The 396 MB/s writes deserve a longer representative test if write speed matters |
| Backup10T | Plausible single-HDD result: 203 MB/s reads, 171 MB/s writes | Capacity/staging tier, not high-availability primary storage |

The terms used on this page:

- ARC is the ZFS cache in RAM. A "warm ARC read" is a read of data that is already in RAM.
- `fsync` is the call an app makes to force a write onto the disk. A "durable write" is a
  write followed by `fsync`.
- IOPS is the number of read or write operations per second.
- QD1 means queue depth one: one request at a time, each waiting for the previous one.
- p99 latency is the time that 99% of requests finish within.

## From a Kubernetes pod over NFS

This is the path that apps use. The test pod ran on the hp-sff worker (2.5 GbE) with a
fresh `truenas-nfs` volume (BigTank, `sync=standard`). A fresh local `longhorn` volume on
the same node gives the comparison. Each test ran once, on September 26.

| Test | NFS on the NAS | Longhorn (local SSD) |
|---|---:|---:|
| Create 2,000 files of 30 KB | 52 files/s | 493 files/s |
| Read those files back | 2,207 files/s | 25,533 files/s |
| Sequential write, 1 MiB direct | 30 MB/s | 71 MB/s |
| Sequential read, 1 MiB direct | 204 MB/s | 110 MB/s |
| 4 KiB random read, one at a time | 2,449 IOPS | 855 IOPS |
| 4 KiB random write + `fsync`, one at a time | 111 IOPS | 464 IOPS |

The NAS wins at reads, because it serves them from its RAM cache. It loses at file
creation and durable writes, because each one waits for the HDD mirrors. The NAS suits
read-mostly bulk data and does not suit databases.

The host's network link caps a pod's NFS speed. The NAS has one 10 GbE port, but only the
Threadripper host also has 10 GbE. hp-sff and hp-elite connect at 2.5 GbE, which is about
312 MB/s at most. The bare-metal mini PCs and the shed host connect at 1 GbE.

## Measured on the NAS: September 20

These tests ran on the NAS itself, on new scratch datasets. They used no raw devices, no
boot-pool writes, no production files, no global cache flushes and no ARC limit changes.
They do not measure the whole Kubernetes, SMB, NFS or iSCSI path.

All sequential runs processed 4 GiB, with one job and queue depth one. MB/s uses decimal
megabytes. These are short, matched workload measurements. They are not steady-state
ratings or ratings at maximum concurrency. The verdicts compare against drive-class
specifications, not against a matched industry-average benchmark. The source links and the
limits of that comparison are in
[the drive comparison](#compared-with-the-drive-specifications).

| Pool | Write + final flush | Disk read, direct | Disk read, prefetch | Warm RAM ARC read | Verdict / industry reference |
|---|---:|---:|---:|---:|---|
| BigTank | 203.4 MB/s | 254.9 MB/s | 480.4 MB/s | 5.34 GB/s | **Normal HDD bulk speed**; writes modest for two mirrors. HGST rates one He10 at ~249 MB/s sustained. |
| ai-pool | 396.3 MB/s | 274.1 MB/s | 1,066.0 MB/s | 5.50 GB/s | **Fast reads, modest writes**. One HP/Samsung SATA SSD is rated ~550 MB/s read / ~520 MB/s write. |
| Backup10T | 170.5 MB/s | 190.5 MB/s | 203.5 MB/s | 5.50 GB/s | **Normal single-HDD speed**. Read is ~80% of Seagate's 254 MB/s best-case transfer rating. |

The physical disk counters confirmed about 4 GiB of disk reads in each sequential
disk-read phase. They showed zero physical reads in each warm ARC repeat. BigTank's write
phase produced about 8.1 GiB of physical writes, which matches two copies in mirrors.

### Small random requests and durable writes

| Pool | 4 KiB disk read IOPS | Read p99 latency | Write + fsync IOPS | Mean write + fsync cycle | Verdict / industry reference |
|---|---:|---:|---:|---:|---|
| BigTank | 97.9 | 108.53 ms | 61.2 | 16.34 ms | **Slow for busy VMs/databases**; mean read ~10.2 ms is mechanical-class, p99 is long. HGST: 8 ms seek + 4.16 ms rotation. |
| ai-pool | 1,502.5 | 1.02 ms | 415.9 | 2.40 ms | **Much faster than HDDs**; raw Samsung QD1 reference is 10K read IOPS, but does not include this 128 KiB record amplification. |
| Backup10T | 130.3 | 19.79 ms | 123.3 | 8.11 ms | **HDD-limited**; Seagate's 170/370 read/write IOPS is QD16, not a matched QD1/fsync comparison. |

These requests access 128 KiB ZFS records, so a 4 KiB read can cause a much larger
physical read. Do not compare these numbers directly with a drive vendor's raw 4 KiB
benchmark. The write IOPS include an `fsync` after every operation. The separate fsync
latency in the raw results is not the whole write cycle.

Warm ARC random reads reached 173,072 IOPS on BigTank, 177,745 on ai-pool and 166,158 on
Backup10T, with no physical reads. That shows that caching works for this 4 GiB working
set. It does not show that every installed gigabyte is necessary.

[Download compact results](assets/nas-benchmarks/2026-09-20/summary.json) ·
[Full fio output and exact arguments](assets/nas-benchmarks/2026-09-20/results.jsonl)

### Four simultaneous bulk streams

A follow-up test ran at 17:58:44–17:59:51 UTC with four new 1 GiB files on a new BigTank
scratch dataset. The reader comparison used those same four files, 4 GiB in total for each
pass. Data caching stayed disabled, and the disk counters verified the physical reads. The
conditions matched the first suite except for the number of jobs and files.

| Test | Aggregate MB/s | Per-stream MB/s |
|---|---:|---:|
| One reader across four files | 434.3 | 434.3 |
| Four concurrent readers | 522.4 | 130.6–135.4 |
| Four concurrent writers, final fsync per job | 202.1 | 50.5–51.5 |

Four readers raised total throughput by about 20%. Four writers shared about the same
total bandwidth as the single writer in the first suite. Aggregate throughput divides
total bytes by the longest fio job runtime. The wall-clock rates that include startup were
416.2, 493.5 and 198.0 MB/s respectively.

For 1 MiB requests, read p99 rose from 31.9 ms with one reader to 95.9–106.4 ms with four.
Concurrent buffered writes showed 1.08-second p99 stalls, and the test did not isolate
their cause. These are latencies of bulk requests, not application response times. This
was not a mixed read and write test, an SMB test or a test of a supported user count.

The scratch dataset was deleted, and a separate check confirmed its absence. All pools
stayed healthy. [Concurrency summary](assets/nas-benchmarks/2026-09-20/concurrency/summary.json)
· [Raw results](assets/nas-benchmarks/2026-09-20/concurrency/results.jsonl)
· [Executed script](assets/nas-benchmarks/2026-09-20/concurrency/run-remote.py).

## Compared with the drive specifications

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
These are comparisons against specifications. They are not an industry percentile or a
matched lab test.

The network can be the bottleneck. A 10 GbE link has an arithmetic ceiling of 1.25 GB/s
before overhead. The earlier 1,119 MB/s TCP result equals 8.95 Gb/s. The SSD disk result
is close to that ceiling, and warm ARC reads exceed it. A 2.5 GbE client has an arithmetic
ceiling of 312.5 MB/s.

### Translating speeds into users

"User" is not a storage workload. Ten people who watch cached video, ten people who copy
large files and ten database writers need different resources. The rows below are
bandwidth budgets. They are not load-tested limits on simultaneous users.

| Example | Aggregate demand | Reading the result |
|---|---:|---|
| 10 direct-play streams at 100 Mb/s each | 125 MB/s | ~26% of BigTank's single-stream prefetch result; concurrent seek patterns, network, and transcoding still need testing |
| 40 direct-play streams at 25 Mb/s each | 125 MB/s | Same bandwidth; four times the independent requests may alter disk behavior |
| 4 file readers at 50 MB/s each | 200 MB/s | ~42% of the sequential read result; client links and concurrency matter |
| 2 file writers at 50 MB/s each | 100 MB/s | ~49% of the flushed sequential write result; leave room for backups and other traffic |
| Small database transactions or Kubernetes control-plane writes | No reliable users-per-second conversion | Use measured durable-write latency, real query/app tests and the workload's latency target |

These examples leave substantial headroom. They do not model seeks across many files,
cache misses, mixed reads and writes, transcoding CPU or application locks. For
consolidation planning, use the
[Proxmox and Kubernetes capacity assessment](inventory/2026-09-20-capacity-and-benchmarks.md).

## ARC is RAM; L2ARC is a separate device

**No L2ARC is installed.** L2ARC is a second-level read cache on an SSD. The pool topology
has no cache vdevs, and the kernel reported `l2_ndev=0` and `l2_size=0`. A comparison of
"L2ARC on" with "L2ARC off" would need hardware that this NAS does not have.

The useful comparison here is disk reads against RAM ARC reads. For the disk tests, the
dataset-local setting `primarycache=metadata` keeps file data out of ARC. Metadata caching
stays enabled. The warm-cache test changes only the scratch dataset to `primarycache=all`,
reads the file once, then reads it again. All tests set `secondarycache=none`.

L2ARC caches reads. It does not speed up writes. A separate log device (SLOG) has a
different job, which is to log the intent of synchronous writes. Do not buy either device
only because a graph shows that the RAM cache is full.
[OpenZFS caching reference](https://openzfs.github.io/openzfs-docs/Basic%20Concepts/Pool%20Structure/Caching.html).

A disk read with prefetch enabled can record ARC demand hits while the app consumes the
prefetched data. The physical disk-byte counters separate those reads from warm RAM reads.
A high demand-hit count alone is not evidence of a RAM read.

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

Pool capacities are ZFS pool figures. They do not promise the same writable dataset
capacity. BigTank reported 27% fragmentation and kept mappings from an earlier vdev
removal. Those facts do **not** establish the cause of a throughput limit. Do not rebuild
a pool because of that correlation alone.

Device names such as `/dev/sda` changed between inspections. Match disks by persistent
identifier or model and by the current `zpool status -P`, not by an old letter. All four
pools were ONLINE with no known pool data errors before the tests.

## How much RAM is needed?

**384 GB is useful today. The smallest acceptable replacement size is not measured.**
A repeated read shows that caching helps. It does not show that the real working set needs
every gigabyte of the current cache.

| Observation | What it establishes |
|---|---|
| 17:16 UTC snapshot: 341.4 GiB ARC, 13.8 GiB other allocations, 22.3 GiB free | Most available memory is cache. "Other" includes OS, apps, kernel and other caches |
| 72-hour CPU mean 1.51%, p95 2.43% across ten-minute buckets | Substantial CPU headroom in the observed workload; averages hide short spikes |
| 72-hour demand-data hit rate 99.917% | Most counted demand requests hit cache; this is not a byte-weighted hit rate |
| RustFS about 3.2 GiB at inspection; peak ten-minute average 7.46 GiB | Reserve app peaks before allocating a future RAM budget to ARC |
| About 11 hours with ARC below 128 GiB and very high demand hits | A clue that some activity fits in less cache. The workload differed, so it is not a 128 GB replacement test |

Tailscale and monitoring used about 0.14 GiB combined. One configured 8 GB VM was stopped.
The five-minute passive sample showed no memory-pressure stalls and no ARC throttling, and
no swap was configured. These are observations of the existing workload. They are not a
stress test at maximum concurrency.

### Purchase priorities

1. **Keep the current RAM and improve cooling first.** The first BigTank HDD temperatures
   were 58, 55, 54 and 43–44°C. Check the airflow and watch the temperatures under
   comparable workloads. The tests showed no failure caused by temperature.
2. **Choose the drive layout for the workload.** Large media and backups need different
   storage from small durable VM and database requests. Use the sequential results for the
   first and the random results for the second. The SSD stripe is not redundant VM storage.
3. **Treat 128–256 GB only as candidates for an expandable replacement.** Reserve memory
   for the OS and for app peaks. Keep 384 GB as the measured baseline. A 64 GB system
   gives up more cache, and nothing here validates it.
4. **Measure a representative week before you buy.** Include backup, restore, Steam iSCSI,
   file opens and concurrent users. Compare task duration, disk latency, memory peaks and
   cache misses. Do not compare cache occupancy alone.
5. **Test a smaller cache budget in a separate planned test.** Define acceptable task
   times and record the original setting. Warm up comparable workloads. Restore the
   original budget if latency or memory pressure exceeds the target. An ARC cap only
   approximates a machine with less physical RAM.

The HP S700 had 816 lifetime CRC errors and the Samsung 860 EVO had four. The inspection
found no matching recent kernel I/O errors. Compare counter changes over time before you
diagnose an active cable or controller fault. A passing SMART result does not guarantee
future reliability.

## Test method and how to repeat it

The suite ran 17:45:56–17:54:58 UTC with the `fio` that was already on the NAS. Each data
pool received one new, uniquely named scratch dataset with an 8 GiB quota,
`compression=off`, `sync=standard`, `recordsize=128K` and `atime=off`. All three scratch
datasets were deleted, and a separate check confirmed their absence. Production properties
and global ARC limits did not change.

1. Write an allocated 4 GiB file, 1 MiB blocks, `psync`, one job, `end_fsync=1`.
2. Read it with `direct=1`, then with buffered prefetch. Keep data caching disabled with
   `primarycache=metadata` and `secondarycache=none`.
3. Run 15 seconds of 4 KiB direct random reads and 10 seconds of 4 KiB writes
   with `fsync=1` on the same scratch file.
4. Set only the scratch dataset's `primarycache=all`. Warm the file, repeat the
   sequential read, then run 10 seconds of cached random reads.
5. Delete only the scratch dataset that this run created. Verify pool health,
   unchanged production properties and the absence of all three scratch datasets.

`end_fsync` requests persistence at the end. `fsync=1` requests it after each write. One
synchronous `psync` job is QD1 even if you request a larger `iodepth`.
[Fio option definitions](https://fio.readthedocs.io/en/latest/fio_doc.html) and
[ZFS dataset properties](https://openzfs.github.io/openzfs-docs/man/master/7/zfsprops.7.html).

The file is too small to prove long-run SSD behavior beyond the device write caches. The
final flush is part of the write runtime that fio reports. The physical-counter brackets
include process startup and occasional SMART polling, so do not divide fio throughput by
those longer brackets. Production traffic continued during the tests, so counter changes
can include that traffic and mirror copies.

Before you start a repeat run, you need SSH access with suitable NAS permissions, healthy
pools, enough free space and a quiet, agreed test window. Read the
[executed script](assets/nas-benchmarks/2026-09-20/run-remote.py) as a dated record. Review
its device mappings and choose a new unique dataset name for another run.
**Never substitute a production path or a raw device for its scratch files.**

Stop the run on any of these conditions: new pool errors, a fio failure, a 180-second wall
timeout, or a SMART HDD temperature of 60°C. That temperature is a conservative limit for
testing, not a manufacturer failure threshold. Check temperatures before and after each
phase, and during longer phases.

Expect allocated data, successful final flushes, physical reads in the disk phases and
near-zero physical reads in the warm-cache repeats. A sparse file or unexpected cache
behavior makes the comparison invalid.

If the run fails, stop the workload and record the error. Remove only the exact scratch
dataset that the run created, after you verify its identity. No production setting needs
a rollback. The script's cleanup tracks the names it created and refuses to adopt a
benchmark dataset that already existed.
[Independent final verification](assets/nas-benchmarks/2026-09-20/verification.json).

## Earlier measurements

These figures have no raw run artifacts and no exact collection time on this page.
**They are not September 20 results, and they are not controlled baselines for a
regression check.**

| Earlier path | Read MB/s | Write MB/s | Limitation |
|---|---:|---:|---|
| Raw TCP, Proxmox `.14` ↔ NAS, one stream | 1,119 | n/a | No storage involved; MTU 1500 |
| NFS v4.2, one stream + readahead | 463 | 218 | `BigTank/k8s`, `sync=disabled` |
| NFS v4.2, four streams | 645 | 230 | Different concurrency from this pass |
| SMB 3.1.1, one stream + readahead | 634 | 141 | `BigTank/virtual-machines`, `sync=standard` |
| SMB 3.1.1, four streams | 408 | 174 | Different concurrency from this pass |

The NFS and SMB write rows do not isolate the cost of the protocol, because the datasets
had different sync policies. The read results also mix mount options, concurrency and
cache state. Nothing here shows that NFS should accept a 4 MiB `rsize`, or that one mount
option closes the gap. Do not use these rows as a tuning plan. The Kubernetes
`truenas-nfs` StorageClass uses `nconnect=16`. A hand-made mount without it does not
describe that path.

Earlier local sequential writes were BigTank 168 MB/s, Backup10T 203 MB/s and
ai-pool 243 MB/s. Earlier BigTank disk reads were 408 MB/s. Earlier cache reads were
2.49, 2.47 and 2.89 GB/s respectively. The files and the method differed, so these numbers
do not show an improvement or a regression against the September 20 test.

The first September 20 sample only read existing files. A 1 GiB direct read gave
96.7 MB/s, a 1 GiB first buffered read gave 273.9 MB/s, and its cached repeat gave
4.84 GB/s. A 256 MiB SMB read from `.14` that bypassed the client cache gave 219.7 MB/s.
Those samples were small. Do not use 96.7 MB/s as BigTank's maximum or 4.84 GB/s as its
disk speed.

## Sources of truth

- Read the current layout and health with `zpool status -P` and `zpool list` on the NAS.
- Read the current properties with `zfs get` on the exact dataset. Inheritance matters.
- Read the share definitions with `midclt call sharing.smb.query` and `sharing.nfs.query`.
- [Storage architecture](storage-architecture.md) and
  [how kopiur backup and restore work](domains/storage/kopiur-backup-architecture.md)
  own the Kubernetes storage and recovery rules.
- The [TrueNAS special-vdev stall runbook](truenas-special-vdev-stall-runbook.md)
  covers the failure where NFS stalls and the NAS looks dead.

## Sharing and permissions

This section says who can reach which data on the NAS, and why. Use it when you add a
device or debug why a user cannot read a file. The September 20 benchmark did not check
every account, ACL or share again. Check the live permissions before you change them. The
benchmark datasets do not use these shares.

### The model

Two groups define two tiers. **Only an account's group membership separates the tiers.**

| Account | UID | Groups | Reaches |
|---|---|---|---|
| `vanillax` | 3000 | `nas-public` + `nas-private` | everything |
| `k8-smb-user` | 3001 | `nas-public` + `nas-private` | everything |
| `proxmox` | 3002 | `nas-public` + `nas-private` | everything |
| `media-server` | 3003 | none | public tier, read-only |
| `truenas_admin` | 950 | not an SMB user | UI / SSH / API only |

`media-server` (TVs and appliances) is in no `nas-*` group on purpose. It reads the public
tier through the directory "other" bits. It cannot reach the private tier, because those
directories have no "other" bits at all.

The appliance account is in no group, not in `nas-public`, for this reason: POSIX mode
bits cannot tell two members of the same group apart. If the appliance were in
`nas-public`, one of two things would follow. Either the group has write and a TV can
delete your media, or the group has no write and your own account loses write too. With
the appliance outside every group, group members are the writers and everyone else is a
reader.

### Tiers

| Tier | Group | Mode | Datasets |
|---|---|---|---|
| Public | `nas-public` (3100) | `2775` | `k8s/jellyfin-media`, `k8s/tubearchivist`, `k8s/kiwix`, `k8s/versatiles`, and the `BigTank/k8s` parent |
| Private | `nas-private` (3101) | `2770` | `General`, `backup`, `photos`, `organized_backups`, `virtual-machines`, `proxmox`, `users`, `k8s/{frigate,ollama,rustfs,vanillax,volsync-kopia-nfs,llama-cpp-archive}`, `ai-pool/{comfyui,llama-cpp,vllm}` |

Mode `2770` hides the data. With no "other" permission, an account outside the group
cannot enter the directory. Mode `2775` gives the group write and everyone else read. The
leading `2` is setgid, so a file created inside inherits the directory's group, not the
creator's private group. That keeps the tiers consistent as data is written.

### Verified behavior

The inspection ran commands as each account. It did not only read the modes.

| | `media-server` | `vanillax` | `k8-smb-user` |
|---|---|---|---|
| Public tier | read | write | write |
| Private tier | **no access** | write | write |

### Rules

- To add a device, make one decision: which groups does it join? An appliance joins none.
  A trusted machine joins both. There is no configuration for each share.
- `BigTank/k8s` holds both public and private children.
  **Never apply a recursive `chmod` or `chgrp` at that level.** It opens the private
  children again. Always apply the change to the individual leaf dataset.
- Keep the parent of a public dataset traversable. `BigTank/k8s` is `nas-public` for that
  reason. If it were private, appliances could not enter the public datasets under it.
- `aclinherit` is `passthrough` on every pool. Do not set it back to `discard`. With
  `discard`, new files stop inheriting and the tiers drift apart with no error.

### Set permissions through the API

`filesystem.setperm` rejects four-digit modes ("Please supply a value between
000 and 777"), so it cannot apply setgid. Use two passes:

```bash
# 1. group + base mode (recursive, strips stale ACLs)
midclt call -j filesystem.setperm \
  '{"path": "<path>", "uid": <uid>, "gid": 3101, "mode": "770",
    "options": {"stripacl": true, "recursive": true}}'

# 2. setgid on directories
sudo find <path> -type d -exec chmod g+s {} +
```

`stripacl: true` discards existing NFSv4 ACLs. That is intended here, because it gives a
predictable baseline based on mode bits. It also removes hidden grants. `BigTank/General`
once showed mode `770 vanillax:vanillax` while a different account had write through an
NFSv4 ACL that the mode did not show.
**On an `nfsv4` dataset, the mode you see is not necessarily the rule that is enforced.**

### Known inconsistencies

- Two ACL models exist side by side. BigTank and its children use `acltype=nfsv4`.
  Backup10T, ai-pool and `BigTank/backup` use `acltype=posix`. Do not change `acltype` on
  a populated dataset without a plan. Leave this as it is.
- The `Backup10T` root was `readonly=off` on September 20. Inspect each replica dataset
  before you assume that it is protected from ordinary writes.
- Two unrelated locations are called "photos". The SMB share `photos` serves
  `/mnt/BigTank/organized_backups/photos`. The NFS export `/mnt/BigTank/photos/All` serves
  the separate `BigTank/photos` dataset.
- `jellyfin-media` is empty. The public tier exists, but this NAS has no film library yet.
