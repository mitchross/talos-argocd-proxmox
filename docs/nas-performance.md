# NAS hardware and performance reference

**Purpose:** the single place that records what the TrueNAS box *is* and what it
actually *does* — hardware inventory, pool layout, measured throughput on disk
and across the network, and the client configuration that produced those
numbers.

**Status:** current state. Every figure on this page was measured on the running
system with `fio`, not estimated or taken from a vendor sheet.

**Scope:** this page describes the storage server and the network paths into it.
It does not cover Kubernetes-side storage policy — see
[Storage architecture](storage-architecture.md) for that, and
[kopiur backup architecture](domains/storage/kopiur-backup-architecture.md) for
backups.

---

## 1. The one-paragraph summary

The 10 gigabit network is not a bottleneck and cannot become one at current pool
speeds: a single TCP stream reaches **1119 MB/s (9.39 Gbit/s)** at standard MTU
1500, and nothing storage-related has ever come close to that. Writes land
between **141 and 243 MB/s on every path measured** — local, NFS, or SMB —
because the pools, not the wire, set that ceiling. Reads are entirely a question
of what caches them: **2.5–2.9 GB/s** when ARC serves them from RAM, **408–645
MB/s** across the network with readahead or parallel streams, and as low as
**224 MB/s** when prefetch is defeated.

```text
READ                                0        1000      2000      3000 MB/s
                                    |    ¦    |         |         |
ai-pool   ARC (RAM)          2891   ██████████████████████████████████████████████
BigTank   ARC (RAM)          2490   ████████████████████████████████████████
NFS       4 streams           645   ██████████
SMB       1 stream+readahead  634   ██████████
NFS       1 stream+readahead  463   ███████
BigTank   cold disk, prefetch 408   ██████
SMB       4 streams           408   ██████
BigTank   disk, no prefetch   224   ███
                                    |    ¦
                                    |    ¦ 10G line rate, 1119 — nothing reaches it
```

```text
WRITE                               0      100       200     250 MB/s
                                    |       |         |    ¦
ai-pool   local, 3x SSD       243   ███████████████████████████████████
NFS       buffered, 10G       218   ███████████████████████████████
Backup10T local, 1 disk       203   █████████████████████████████
SMB       parallel, 10G       174   █████████████████████████
BigTank   local, 4 disks      168   ████████████████████████
SMB       buffered, 10G       141   ████████████████████
                                    |       |         |    ¦
                                    |       |         |    ¦ calomel 4x raid10, 226
```

Note the scale change between the two blocks: 0–3000 for reads, 0–250 for
writes. Plotted on one axis the entire write story would be invisible.

---

## 2. Hardware

| Component | Value |
|---|---|
| OS | TrueNAS SCALE 26.0 Community |
| ZFS | OpenZFS 2.4.3-1 |
| CPU | Intel Xeon E5-2680 v4 — 14 cores / 28 threads @ 2.40 GHz |
| RAM | 377 GB |
| ARC | 275 GB in use, `c_max` 404 GB, hit rate 99.96% |
| NIC | 10 GbE, MTU 1500 |

The CPU matters when reading general NAS advice: commentary about consumer NAS
units bottlenecking on weak ARM/N100/Celeron processors does not apply here.
This box has never been CPU-bound in any measurement on this page.

### Disks

| Device | Model | Size | Type | Pool |
|---|---|---|---|---|
| `sdi` | HGST HUH721010AL4200 | 10 TB | 7200 rpm SAS | BigTank — mirror-0 |
| `sdj` | HGST HUH721010AL4200 | 10 TB | 7200 rpm SAS | BigTank — mirror-0 |
| `sdk` | HGST HUH721010AL4200 | 10 TB | 7200 rpm SAS | BigTank — mirror-1 |
| `sdl` | HGST HUH721010AL4200 | 10 TB | 7200 rpm SAS | BigTank — mirror-1 |
| `sda` | Seagate ST10000NM0096 | 10 TB | 7200 rpm | Backup10T |
| `sdd` | P3-512 | 512 GB | SATA SSD | ai-pool |
| `sde` | HP SSD S700 500GB | 500 GB | SATA SSD | ai-pool |
| `sdf` | Samsung 860 EVO 1TB | 1 TB | SATA SSD | ai-pool |
| `sdg` | T-FORCE 512GB | 512 GB | SATA SSD | boot-pool mirror |
| `sdh` | MK000480GWCEV | 480 GB | SATA SSD | boot-pool mirror |
| `sdb`, `sdc` | T-FORCE 512GB | 512 GB | SATA SSD | unused, no partitions |

---

## 3. Pools

| Pool | Topology | Raw | Used | Frag | Role |
|---|---|---|---|---|---|
| **BigTank** | 2 × 2-way mirror, striped (RAID10) | 18.2 TB | 53% | 25% | Primary data. Backs all NFS and SMB shares. |
| **Backup10T** | single disk | 9.08 TB | 68% | 1% | Holding/staging disk. Replication target for `BigTank/General,backup,photos`. Single-disk by design. |
| **ai-pool** | 3 × single-disk stripe | 1.82 TB | 50% | 2% | LLM model weights. **No redundancy, deliberately** — contents are re-downloadable. |
| **boot-pool** | 2-way mirror | 222 GB | 50% | 26% | Boot. |

Two properties of BigTank explain its write behaviour and should not be
forgotten when reading section 4:

- **25% fragmentation** at 53% capacity.
- **A removed vdev.** `zpool status` reports `Removal of vdev 3 copied 325G`
  with `18.8M memory used for removed device mappings`. Every block lookup on
  this pool passes through that indirection table for the life of the pool.

---

## 4. Measured throughput

### Local, straight to the pools

Compression was set to `off` and the payload was incompressible, so these are
true disk figures rather than compression artefacts.

| Pool | Write, 1 stream | Write, 4 streams | Read from ARC | Read from disk |
|---|---|---|---|---|
| BigTank (4 disks) | 168 MB/s | 164 MB/s | 2490 MB/s | **408 MB/s** |
| Backup10T (1 disk) | 203 MB/s | 158 MB/s | 2466 MB/s | — |
| ai-pool (3 SSDs) | 243 MB/s | 179 MB/s | 2891 MB/s | — |

**BigTank's four disks write slower than Backup10T's one disk.** A striped
mirror should write at roughly twice a single drive; it writes at 0.8×. Adding
parallel streams does not help — 4 streams were *slower* than 1 on every pool.

Per-disk instrumentation during a write shows both mirrors loaded evenly, so
striping itself is working, and the disks burst to roughly 490 MB/s aggregate
raw. But sustained per-disk throughput sits at 120–130 MB/s against roughly 250
MB/s these drives do sequentially. That gap is consistent with the 25%
fragmentation and the removed-vdev indirection turning a sequential write into a
scattered one. This is the single clearest improvement target on the box.

### Across the network

Client is Proxmox `pve` at 192.168.10.14 over 10 GbE, reading and writing
BigTank.

| Path | Read | Write |
|---|---|---|
| Raw TCP, 1 stream (no storage involved) | **1119 MB/s** | — |
| NFS v4.2, 1 stream + readahead | 463 MB/s | 218 MB/s |
| NFS v4.2, 4 parallel streams | 645 MB/s | 230 MB/s |
| SMB 3.1.1, 1 stream + readahead | 634 MB/s | 141 MB/s |
| SMB 3.1.1, 4 parallel streams | 408 MB/s | 174 MB/s |
| 2.5 GbE workstation, raw TCP | 256 MB/s | — |

Read it against the two ceilings. NFS write (218) lands within 30% of BigTank's
local write (168) — writes are pool-bound end to end, and no network change will
move them. Reads never exceed 645 MB/s against a 1119 MB/s wire, so the network
has headroom nothing is using.

**The NFS-vs-SMB write comparison in that table is not valid and must not be
quoted as a protocol result.** The NFS figures were taken against
`BigTank/k8s`, which has `sync=disabled`; the SMB figures against
`BigTank/virtual-machines`, which has `sync=standard`. That measures the sync
setting, not the protocol. Treat 218 vs 141 as "sync off vs sync on".

The read difference **is** real but is a mount-option effect, not a protocol
one: the SMB mount negotiated `rsize=4194304` (4 MB) against NFS's
`rsize=1048576` (1 MB), so SMB makes a quarter as many round trips. NFS at
`rsize=4M` would be expected to close most of the gap.

The ad-hoc NFS mount used for these tests had no `nconnect`. The cluster's real
`truenas-nfs` storageClass **does** mount with `nconnect=16`, so the
single-stream NFS numbers above understate the production path.

---

## 5. Against calomel's reference table

[calomel.org's ZFS RAID speed and capacity table](https://calomel.org/zfs_raid_speed_capacity.html)
is the usual yardstick for "is my pool normal?". It benchmarked 24 × WD Black
4 TB 7200rpm SAS on an LSI 9207-8i, FreeBSD 10.2, with `bonnie++` on a 16 GB
file and compression disabled.

Their **4 × raid10** — two 2-drive mirrors striped — is exactly BigTank's
topology, which makes it the one row worth comparing against.

| Metric | calomel, WD Black 4 TB | BigTank, HGST He10 10 TB | Delta |
|---|---|---|---|
| Sequential write | 226 MB/s | 168 MB/s | **−26%** |
| Sequential read | 644 MB/s | 408 MB/s | **−37%** |

| Metric | calomel 1 × single | Backup10T, 1 disk | Delta |
|---|---|---|---|
| Sequential write | 108 MB/s | 203 MB/s | **+88%** |

**The comparison is not symmetric, and that is the point.** calomel ran
`bonnie++ -b` — synchronous writes with the drive cache disabled — on freshly
created, unfragmented pools. That is a *harsher* write test than the buffered
`--end_fsync=1` used here. Backup10T beating their single-drive number by 88%
is about what an easier test plus a newer, denser platter should produce.

BigTank landing 26% *below* their figure despite the easier test, on drives a
generation newer and 2.5× larger, is the anomaly. It is the same finding as
section 4 arrived at from a different direction, and the causes are the same:
25% fragmentation and the removed-vdev indirection layer.

For reference, the rest of calomel's spinning-disk table, useful when sizing a
future pool:

| Configuration | Write | Read |
|---|---|---|
| 1 × single | 108 | 204 |
| 2 × mirror | 106 | 488 |
| 4 × raid10 | 226 | 644 |
| 4 × raidz1 | 225 | 619 |
| 4 × raidz2 | 204 | 183 |
| 6 × raid10 | 389 | 655 |
| 6 × raidz2 | 429 | 488 |

Their numbers are not directly portable to this box — different drives, OS, ZFS
version, and test tool — so treat them as shape rather than target. The useful
signal is relative: adding spindles buys write throughput roughly linearly, and
`raidz2` at four drives collapses on reads.

---

## 6. How to read these numbers correctly

Four traps produced wrong answers during measurement. They will produce wrong
answers again on any re-run.

**Cache-defeating is mandatory on a 377 GB machine.** With a 275 GB ARC, no
practical file size defeats the cache. Use `fio --direct=1` (OpenZFS 2.3+ has
real O_DIRECT and every dataset here is `direct=standard`), or read a cold
region of a file far larger than ARC.

**O_DIRECT disables prefetch, so it understates sequential reads.** BigTank
reads 224 MB/s under O_DIRECT and 408 MB/s buffered with prefetch — an
83% difference on identical hardware. O_DIRECT answers "is ARC involved?"; it
does not answer "how fast is this pool?" Comparisons against published
reference tables such as
[calomel.org's ZFS RAID speed table](https://calomel.org/zfs_raid_speed_capacity.html)
must use the buffered figure, because that is what `dd`-based tests measure.

**Client page cache can invent throughput above line rate.** Four buffered
streams reading one file reported 1596 MB/s over NFS and 2486 MB/s over SMB.
Both are impossible on a 10 GbE link, because jobs 2–4 were served from the
client's RAM. Always sanity-check a network result against measured raw TCP;
anything above it is a measurement artefact. Parallel tests must use
`--direct=1` and a separate file per job.

**Compression turns benchmarks into fiction.** `fio` must write incompressible
data, or set `compression=off` on the test dataset. Note `--refill_buffers`
regenerates random data per I/O and becomes its own CPU bottleneck; a single
random buffer is already incompressible and is enough.

One more artefact worth knowing: `zfs_vdev_direct_write_verify=1` makes ZFS read
back and verify every O_DIRECT write, which showed up as an absurd 82 MB/s.
O_DIRECT writes are not a meaningful measurement here — ARC is a read cache, so
measure writes buffered with `--end_fsync=1`.

---

## 7. Tuning observations

Not yet applied. Recorded here so the reasoning is not lost.

- **`zfs_dirty_data_max` is 4 GB on a 377 GB machine.** ZFS caps this default at
  4 GB regardless of RAM. Writes are visibly bursty — disks idle, then flush at
  ~490 MB/s. Raising it lets ZFS absorb more before throttling. Test before
  adopting; a larger dirty buffer also lengthens txg flush pauses.
- **NFS has no `nconnect`.** Every mount is one TCP connection, which is why 1
  stream reaches 463 MB/s while 4 reach 645. `nconnect=4` would let a single
  mount use multiple connections.
- **Jumbo frames would gain nothing.** Single-stream TCP already reaches 94% of
  theoretical 10 GbE at MTU 1500. This is the most commonly suggested tuning
  knob and the least useful one here — and a partially applied MTU change across
  a path breaks connectivity in ways that are tedious to diagnose.
- **BigTank fragmentation and vdev indirection** are the real write limit. Both
  are properties of the pool's history; neither is fixable by tuning. Only
  rewriting the data into a freshly created pool clears them.

---

## 8. Client configuration

Mount options in effect when the section 4 numbers were taken.

**SMB** — Proxmox storage `truenas-smb`, share `virtual-machines` on
`/mnt/BigTank/virtual-machines`:

```
vers=3.1.1,cache=strict,rsize=4194304,wsize=4194304,bsize=1048576,actimeo=1
```

**NFS** — export `/mnt/BigTank/k8s`:

```
vers=4.2,rsize=1048576,wsize=1048576,proto=tcp,hard,timeo=600,retrans=2,sec=sys
```

NFS exports differ in root mapping, which decides whether a client's `root` can
write. `/mnt/BigTank/proxmox` squashes root; `/mnt/BigTank/k8s` and
`/mnt/ai-pool/vllm` set `maproot_user: root`. A "permission denied" as root on
an NFS mount is usually this, not a filesystem permission.

---

## 9. Identity, sharing, and permissions

**Purpose:** who can reach which data, and why. This is the model to reason from
when adding a device or debugging "why can't this user read that file".

**Status:** current state, implemented. Replaces an earlier arrangement in which
every account sat in its own private group and cross-account access was
structurally impossible.

### The model in one sentence

Two groups define two tiers, and **the only thing separating the tiers is which
groups an account belongs to.**

| Account | UID | Groups | Reaches |
|---|---|---|---|
| `vanillax` | 3000 | `nas-public` + `nas-private` | everything |
| `k8-smb-user` | 3001 | `nas-public` + `nas-private` | everything |
| `proxmox` | 3002 | `nas-public` + `nas-private` | everything |
| `media-server` | 3003 | **none** | public tier, read-only |
| `truenas_admin` | 950 | not an SMB user | UI / SSH / API only |

`media-server` (TVs and appliances) is deliberately in **no** `nas-*` group. It
reads the public tier through the directory "other" bits and is blocked from the
private tier because those directories have no "other" bits at all.

**Why the appliance account is in no group rather than in `nas-public`:** POSIX
mode bits cannot distinguish two members of the same group. If the appliance
were in `nas-public`, then either the group has write — and a TV can delete your
media — or it does not, and your own account loses write too. Leaving the
appliance out of every group yields *group = writers, other = readers*, which is
exactly the intent.

### Tiers

| Tier | Group | Mode | Datasets |
|---|---|---|---|
| **Public** | `nas-public` (3100) | `2775` | `k8s/jellyfin-media`, `k8s/tubearchivist`, `k8s/kiwix`, `k8s/versatiles`, and the `BigTank/k8s` parent |
| **Private** | `nas-private` (3101) | `2770` | `General`, `backup`, `photos`, `organized_backups`, `virtual-machines`, `proxmox`, `users`, `k8s/{frigate,ollama,rustfs,vanillax,volsync-kopia-nfs,llama-cpp-archive}`, `ai-pool/{comfyui,llama-cpp,vllm}` |

`2770` is what does the hiding: no "other" permission means an account outside
the group cannot even traverse into the directory. `2775` grants the group write
and everyone else read. The leading `2` is setgid, so files created inside
inherit the directory's group instead of the creator's private group — that is
what stops the arrangement drifting apart as data is written.

### Verified behaviour

Tested by running as each account rather than by reading modes:

| | `media-server` | `vanillax` | `k8-smb-user` |
|---|---|---|---|
| Public tier | read | write | write |
| Private tier | **no access** | write | write |

### Rules

- **Adding a device is one decision: which groups does it join?** An appliance
  joins none. A trusted machine joins both. There is no per-share configuration.
- **`BigTank/k8s` is a mixed container** — it holds public *and* private children.
  Never apply a recursive `chmod`/`chgrp` at that level; it will re-open the
  private children. Always scope to the individual leaf dataset.
- **The parent of a public dataset must stay traversable.** `BigTank/k8s` is
  `nas-public` for exactly this reason: if it were private, appliances could not
  traverse into the public datasets beneath it.
- `aclinherit` is `passthrough` on every pool. Do not set it back to `discard` —
  that stops new files inheriting and the tiers decay silently.

### Setting permissions through the API

`filesystem.setperm` **rejects four-digit modes** ("Please supply a value between
000 and 777"), so setgid cannot be applied through it. Two passes are required:

```bash
# 1. group + base mode (recursive, strips stale ACLs)
midclt call -j filesystem.setperm \
  '{"path": "<path>", "uid": <uid>, "gid": 3101, "mode": "770",
    "options": {"stripacl": true, "recursive": true}}'

# 2. setgid on directories
sudo find <path> -type d -exec chmod g+s {} +
```

`stripacl: true` discards existing NFSv4 ACLs. That is intended here — it
establishes a predictable mode-based baseline — but be aware it removes hidden
grants. Before this work, `BigTank/General` showed mode `770 vanillax:vanillax`
while a different account had write through an invisible NFSv4 ACL. **On an
`nfsv4` dataset the mode you see is not necessarily the rule being enforced.**

### Known remaining inconsistencies

- **Two ACL models coexist.** `acltype=nfsv4` on BigTank and children;
  `acltype=posix` on Backup10T, ai-pool, and `BigTank/backup`. `acltype` cannot
  be changed casually on a populated dataset, so this is left as-is.
- **`Backup10T` is intentionally `readonly=on`.** It is the second copy of
  personal data. ZFS replication (`zfs recv`) still writes to a read-only
  dataset, but humans and processes cannot — which is the correct protection for
  a replica. Do not turn it off.
- **Two unrelated locations are called "photos"**: the SMB share `photos` serves
  `/mnt/BigTank/organized_backups/photos`, while the NFS export
  `/mnt/BigTank/photos/All` serves the separate `BigTank/photos` dataset.
- **`jellyfin-media` is empty.** The public tier is real, but there is no film
  library on this NAS yet.

---

## 10. Reproducing these measurements

Requires SSH to the NAS and a client. `midclt` and read-only `zpool` commands
work as `truenas_admin` without sudo; `zfs set` does not, so change dataset
properties through the API instead.

Create a scratch dataset, own it, and disable compression:

```bash
# on the NAS
midclt call pool.dataset.create '{"name": "<pool>/_bench", "type": "FILESYSTEM"}'
midclt call -j filesystem.setperm \
  '{"path": "/mnt/<pool>/_bench", "uid": 950, "gid": 950, "mode": "755", "options": {"stripacl": true}}'
midclt call pool.dataset.update "<pool>/_bench" '{"compression": "OFF"}'
```

`midclt call -job` fails to parse on this build — use `-j`.

Sequential write, and read as ARC would serve it:

```bash
fio --name=w --filename=/mnt/<pool>/_bench/f --rw=write --bs=1M --size=24G \
    --direct=0 --ioengine=psync --end_fsync=1 --group_reporting
fio --name=r --filename=/mnt/<pool>/_bench/f --rw=read --bs=1M --size=24G \
    --direct=0 --ioengine=psync --invalidate=0 --group_reporting
```

True disk read, using a cold region of a file much larger than ARC. **`--readonly`
is required** when pointing `fio` at production data:

```bash
fio --name=cold --filename=<large-file> --rw=read --bs=1M --size=32G \
    --offset=120G --direct=0 --ioengine=psync --readonly --group_reporting
```

Confirm it really came from disk — watch `zpool iostat <pool> 5` for read
bandwidth during the run, and check that ARC misses climbed:

```bash
awk '/^misses/{print $3}' /proc/spl/kstat/zfs/arcstats
```

Remove the scratch dataset afterwards:

```bash
midclt call pool.dataset.delete "<pool>/_bench"
```

Raw network ceiling, with no storage in the path, needs only `python3` on both
ends. Listen on the NAS, then send from the client, and compare the result to
every network figure in section 4:

```python
# receiver: python3 - (bind 0.0.0.0:5201, recv until EOF, report bytes/elapsed)
# sender:   python3 - (connect, sendall a 4 MiB buffer N times, report bytes/elapsed)
```

---

## 11. Source of truth

- Pool topology and health: `zpool status` on the NAS — authoritative over any
  table here.
- Share definitions: `midclt call sharing.smb.query` / `sharing.nfs.query`.
- Kubernetes-side storage policy: [Storage architecture](storage-architecture.md).
- A pool that disappears from the Storage dashboard: see
  [TrueNAS special-vdev stall runbook](truenas-special-vdev-stall-runbook.md).
  Note that an OFFLINE pool with a null topology blanks the entire Storage
  dashboard — `zpool list` is the reliable check, and exporting the dead pool
  with `destroy: false` restores the UI without touching data.
