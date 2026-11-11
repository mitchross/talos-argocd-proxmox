# Storage benchmark: every path, one method — November 11

**Status:** measured 2026-11-10 to 2026-11-11 for #3665. Raw data:
[`results.jsonl`](../assets/storage-bench/2026-11-11/results.jsonl). The
[storage tiers page](../domains/storage/storage-tiers.md#measured-numbers) uses these numbers.

## Method

- One pod per run in the `storage-bench` namespace: 2 CPU, 2 GiB RAM (guaranteed QoS), a
  20 GiB scratch PVC, Alpine 3.22 by digest with fio 3.39. Job files and the run script are in
  [`my-apps/system/storage-bench`](https://github.com/mitchross/talos-argocd-proxmox/tree/main/my-apps/system/storage-bench).
- Five profiles, each run three times; the tables show the median.

| # | Profile | fio | Answers |
|---|---|---|---|
| A | Database commit | 4k random write, iodepth 1, `fsync` after each, 30 s | commits per second, p50/p99 |
| B | Random read | 4k random read, iodepth 32, direct, 30 s | read IOPS on a cache miss |
| C | Bulk write | 1M sequential write, iodepth 8, direct, 8 GiB, `end_fsync` | MB/s |
| D | Bulk read | 1M sequential read, iodepth 8, direct, 8 GiB | MB/s |
| E | Small files | 20,000 × 16 KiB files, `fsync` on close, 64 open | files per second |

- Each run has a 180 s cap. A run that hits it ends that pod, so the later runs of that
  profile are missing. `n=1` marks a median of one run. The driver also stops on an unhealthy Longhorn volume or a NAS disk at
  60 °C (the maximum seen was 55 °C).
- One writer at a time on the flash disks: the PostHog copies (#3663) and the benchmark never
  overlapped.
- Not collected: the NAS-side `zpool iostat`. Nobody had a NAS shell during the window.

## Results

Pod nodes: `jxfkdr` is the GPU worker (10 GbE), `gen12` is hp-elite-gen12 (bare metal,
1 GbE), `h76ncc` is the hp-sff worker (2.5 GbE), `01` is `truenas-worker-01` (the VM on the NAS).

| Path | Pod node | A fsync/s (p50 / p99) | B read IOPS | C write MB/s | D read MB/s | E files/s |
|---|---|---|---|---|---|---|
| p1-flash-local | jxfkdr | 346 (3.2 / 6.5 ms) | 10,003 | 169 | 610 | 221 |
| p2-flash-remote | gen12 | 319 (3.5 / 6.7 ms) | 15,860 | 110 | 111 | 233 |
| p3-longhorn-2copy | h76ncc | 192 (4.3 / 16.3 ms) | 6,069 | 104 | 226 | 171 |
| p4-truenas-ssd | 01 | 863 (0.7 / 3.9 ms) | 13,685 | 205 | 624 | 351 |
| p4-truenas-ssd | jxfkdr | 185 (5.3 / 7.7 ms) | 10,564 | 170 | 482 | 159 |
| p5-flash-2copy | gen12 | 237 (4.0 / 11.3 ms) | 16,584 | 56 | 109 | 223 |
| p5-flash-2copy | jxfkdr | 186 (5.2 / 8.7 ms) | 9,567 | 155 | 544 | 143 (n=1), 1 run hit 180 s |
| p6-nfs-bigtank | gen12 | 108 (7.4 / 45.9 ms) | 27,785 | 56 | 117 | —, 1 run hit 180 s |
| p6-nfs-bigtank | jxfkdr | 103 (8.0 / 59.0 ms) | 38,540 | 67 | 561 | —, 1 run hit 180 s |
| p7-nfs-aipool | jxfkdr | 270 (3.1 / 41.2 ms) | 30,846 | 316 | 816 | 164 |
| p8-emptydir | jxfkdr | 2126 (0.4 / 1.0 ms) | 64,668 | 1971 | 598 | 776 |

Where the copies sat:

| # | Path | Class | Copies |
|---|---|---|---|
| 1 | Longhorn flash, local copy | `longhorn-flash` | `ssd-flash` (GPU worker) |
| 2 | Longhorn flash, remote engine | `storage-bench-ssd-flash` | `ssd-flash` (GPU worker) |
| 3 | Longhorn, two copies | `longhorn` | `gpu-bulk` (GPU worker, consumer SATA) + `truenas-ssd` |
| 4 | Longhorn on the NAS VM | `storage-bench-truenas-ssd` | `truenas-ssd` (Intel S3700, PLP) |
| 5 | Longhorn, two `flash` copies | `storage-bench-flash-2` | `ssd-flash` + `truenas-ssd` |
| 6 | NFS on BigTank (HDD mirrors) | `truenas-nfs` | NAS dataset, `sync=standard` |
| 7 | NFS on ai-pool (striped consumer SSDs) | `nfs-comfyui-10g` | NAS dataset |
| 8 | Node-local `emptyDir` | none | the GPU worker's ephemeral disk |

Path 3 did not land on the consumer `hp-sff` disks as planned: Longhorn put both copies on
other nodes. It measures two remote copies from a 2.5 GbE node.

## Copy and restore

**Copy speed (path 12).** Pending. Two scratch volumes hold 10 GiB of random data each.
Mitch runs the two commands on #3665: one adds a third `longhorn` copy, one rebuilds the
`truenas-ssd` copy of a `flash` volume over 10 GbE. A watcher records the time until the
volume is healthy. This section gets the numbers in a follow-up commit.

**Restore (path 13, speed part).** The latest kopiur snapshot of
`paperless-ngx/paperless-postgres-data` restored into a new PVC on three classes. Each copy
then started Postgres with no Service, ran `pg_amcheck --all --heapallindexed` and counted rows.

| Target class | Copies | Restore time | `pg_amcheck` | Tables | DB size |
|---|---|---:|---|---:|---:|
| `longhorn-flash` | `ssd-flash` + `truenas-ssd` | 26 s | pass | 143 | 22 MB |
| `longhorn` | `gpu-bulk` + `hp-sff-ssd2` | 26 s | pass | 143 | 22 MB |
| `storage-bench-truenas-ssd` | `truenas-ssd` | 37 s | pass | 143 | 22 MB |

All three copies pass `pg_amcheck` and match production: 143 tables, 0 documents, a 22 MB
database. The volume is too small for a speed number: the time is mover start-up, not data.
A restore rate needs a larger volume. The restore-canary drill (the "proof" part of path 13)
deletes a PVC, so it waits for Mitch; the commands are on #3665.

## What the numbers say

- **Commit latency is set by the network hop, not the disk.** The S3700 does 863 commits/s
  from a pod on the NAS VM, but 185/s from the GPU worker over 10 GbE. `ssd-flash` does
  346/s locally.
- **A remote copy costs little for commits.** A pod on gen12 with its only copy on the GPU
  worker (path 2) does 319 commits/s, against 346/s with the copy local (path 1). Bulk
  transfer is capped by gen12's 1 GbE link at about 110 MB/s. Databases like PostHog can
  move between nodes without a big commit penalty.
- **A second synchronous copy halves the commit rate.** Path 5 drops to 186-237 commits/s and
  small files to about 143-223/s. One small-file run on the GPU worker went past 180 s. That
  is the cost of the two-copy databases from #3663.
- **NFS on BigTank confirms the old rule.** About 105 commits/s with a p99 of 46-59 ms, and
  the small-file profile never finished inside 180 s. Keep databases and many-small-file
  workloads off `truenas-nfs`.
- **ai-pool is fast and unprotected.** 316 MB/s write, 816 MB/s read, 270 commits/s, but one
  dead disk loses the pool. Keep it for re-downloadable files.
- **The upper bound** is the node's own disk (path 8): 2,126 commits/s at a p99 of 1 ms.

## Limits

- Three runs per profile per path, on one day. No other load was controlled.
- Paths 9-11 (the NAS flash mirror over Longhorn, NFS and iSCSI) wait on the #3666 drives;
  see #3705.
- No failure tests (node reboot, NAS reboot, detach/reattach) ran yet.
- The first path-2 run overlapped the 06:07Z Kubernetes 1.37.2 upgrade and is marked
  `tainted` in the raw data. The tables use the rerun.
