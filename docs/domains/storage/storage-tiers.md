# Pick a StorageClass

This page tells you which StorageClass to put on a new PVC, the request an app makes for
a disk. A StorageClass is the named recipe that Kubernetes uses to create the volume. Read
this page before you add a PVC or move one.

Choose a class by how the app reads and writes, how many copies the data needs, and how
the data must come back after a failure. The class name does not tell you which physical
drive holds the data. The [disk map](disk-map.md) does.

## The classes

| Class | Current backing / selection | Appropriate use and limitation |
|---|---|---|
| `longhorn` (default) | Two V1 replicas on different Longhorn nodes tagged `wired-storage` (no data locality) | App state and databases. One node can fail and the volume stays up. Volumes created before the two-copy default keep the count set on the live Volume. |
| `longhorn-flash` | One replica selected by disk tag `flash`. Two disks carry the tag: the Threadripper's 440 GiB `ssd-flash` (two mirrored HPE SATA SSDs with PLP, thick LVM) and the 229 GiB `truenas-ssd` (one Intel S3700 with PLP) | Selected write-heavy state and noisy local I/O. One copy does not survive the loss of its host, and a drain must copy it first. Existing volumes can be raised to two copies one by one. |
| `longhorn-flash-ha` | Two replicas selected by disk tag `flash`, one on each `flash` disk, no data locality | New databases that need enterprise flash. A reboot of either node needs no copy. `truenas-ssd` sits on one drive and is small: check its free space before you add a volume. |
| `longhorn-wired-ha` | Two replicas with hard node/zone/disk separation on Longhorn nodes tagged `wired-storage` | Selected state that needs a surviving live copy. Requires healthy replicas, a working control plane, eligible compute and the rest of the application's dependencies. |
| `truenas-nfs` | TrueNAS BigTank, HDD mirrors behind a large RAM cache, RWX; each PVC is its own dataset with `sync=standard` | Bulk, read-mostly data where NAS downtime is accepted: the immich library, project-nomad downloads. Measured from a pod: fast repeated reads, but only about 50 file creates and 110 `fsync` writes per second, so never databases, Docker/overlay storage or search indexes. |
| Static NFS / SMB classes | The specific NAS share named in each PV | Media, model files and shared data. Inspect the backing dataset: BigTank and the unmirrored AI SSD pool have different failure behavior. |

Terms in the table: a replica is one full copy of a Longhorn volume on one node. PLP is
power-loss protection, which lets an SSD finish its writes when power fails. RWX means
several nodes can mount the volume at once. RWO means one node at a time.

For the common cases, use this short list. The disk map has the
[full placement table](disk-map.md#where-should-new-data-go).

- A database or ordinary app state goes on `longhorn`.
- A database that needs enterprise flash goes on `longhorn-flash-ha`.
- A heavy writer, such as ClickHouse or Kafka, goes on `longhorn-flash`.
- Bulk, read-mostly files go on `truenas-nfs`.

A disk tag that a class selects must sit on at least two disks on two nodes. The
[disk map](disk-map.md#rule-no-disk-tag-with-only-one-disk) has the rule and the current tags.

Do not use `longhorn-kopiur-staging-local` for application data. kopiur uses it for the
temporary volume clones that backups and restores read. Its clones land only on disks
tagged `clone-ok`: the Threadripper flash disk and `hp-sff-ssd2`. Either disk can take any
clone, so one dead host does not block backups. A volume whose only copy is on the dead
host still cannot be backed up. The class uses `WaitForFirstConsumer` binding, and it
depends on the Longhorn overprovisioning allowance. Count the staging clones when you plan
capacity.

## Which nodes hold Longhorn data

The Omni cluster template sets up Longhorn data disks on the HP SFF worker (two disks),
the Threadripper, `hp-elite-gen13`, `mini-pc-dell-ultra-worker` and `truenas-worker-01`. Those five nodes carry
the `wired-storage` tag. The HP Micro in the shed sits behind a Wi-Fi bridge. Its disks
are registered, but scheduling is disabled on them. `hp-elite-gen12` is compute-only and
has no Longhorn disk. The [fleet inventory](../../inventory/2026-11-03-fleet-inventory.md)
lists the machines.

[Storage architecture](../../storage-architecture.md#two-copies-for-data-that-cant-be-re-created)
lists which volumes keep two copies.

The Omni annotation `node.longhorn.io/default-node-tags` sets tags only on a Longhorn node
whose tag list is empty. It does not change the tags of a node that already has tags. To
change placement on an existing node, change the Longhorn node object through a reviewed
Git change. Then check where the replicas are.

Inspect the tags and zones. These commands only read:

```sh
kubectl -n longhorn-system get nodes.longhorn.io -o custom-columns='NAME:.metadata.name,TAGS:.spec.tags'
kubectl get nodes -L topology.kubernetes.io/zone
```

Expect `wired-storage` on the four nodes named above. The HP SFF's two Talos VMs share the
`hp-sff` zone, because they run on one physical host. A node tag makes a node eligible for
replicas. It does not prove that a given volume has two healthy copies.

## Change the class of an existing PVC

A change to a StorageClass does not move existing PVCs. Use the
[PVC migration runbook](pvc-storageclass-migration.md), which keeps the kopiur backup
identity. Do not delete a PVC because its only replica is unreachable for a while. The
[storage evidence collector](collecting-storage-evidence.md) joins each PVC to its volume,
its replicas and their zone labels.

## Performance and durability

Ask three separate questions about any storage choice:

1. Are repeated reads served from a cache?
2. How long does the slowest durable write take?
3. Does another host keep the data after a failure?

A large ZFS RAM cache (ARC) answers only the first. PLP improves the second. A second
Longhorn replica answers the third, and it adds a synchronous network write. None of the
three replaces the other two.

Keep the Threadripper flash storage (`ssd-ent`) on thick LVM. Thin LVM serializes `fsync`,
which makes `longhorn-flash` a downgrade. Change this only after an
end-to-end measurement that shows an equal result. `longhorn-flash` carries PostHog,
radar-ng and product-bench. Its local mirror protects against one failed drive, not
against a failed host.

Bulk streaming and small random I/O cost different amounts on the NAS. Small-file writes
on the HDD pool are slow, and that is one reason radar-ng uses `longhorn-flash`. That
result is for one workload. It does not show that every database is slow on every network storage
protocol. A 10 GbE link does not tell you the latency of a synchronous write.

Check the `sync` property of a dataset before you compare database performance on it.
Datasets that `truenas-nfs` creates use `sync=standard`, and so does `BigTank/k8s/rustfs`.
Older app datasets under `BigTank/k8s` were set to `sync=disabled`. With `sync=disabled`,
the NAS acknowledges a write before it reaches disk. An app that accepts a stall while the
NAS is off does not thereby accept the loss of acknowledged writes. Run
`zfs get sync <dataset>` on the NAS to read the live value.

Several pods on the same Kubernetes node can mount one Longhorn RWO volume. That is not a
shared filesystem across nodes. Use `strategy: type: Recreate` on a Deployment with an RWO
PVC, so a rollout never attaches the volume on two nodes at once. Longhorn can also serve
RWX through share-manager pods, but the classes here do not declare it. Keep NAS RWX for
shared files unless a separate migration is justified.

### Measured numbers

Median of three fio runs per path, November 11 ([full page and method](../../inventory/2026-11-11-storage-bench.md)).
"Commits/s" is 4k writes with `fsync` after each, the database case.

| Class or path | Pod on | Commits/s (p99) | Random read IOPS | Write / read MB/s | Small files/s |
|---|---|---:|---:|---:|---:|
| `emptyDir` (node disk) | GPU worker | 2,126 (1.0 ms) | 64,668 | 1,971 / 598 | 776 |
| `longhorn-flash`, local copy | GPU worker | 346 (6.5 ms) | 10,003 | 169 / 610 | 221 |
| `longhorn-flash`, remote copy | gen12 (1 GbE) | 319 (6.7 ms) | 15,860 | 110 / 111 | 233 |
| `flash`, two copies | GPU worker | 186 (8.7 ms) | 9,567 | 155 / 544 | 143 |
| `longhorn`, two copies | hp-sff | 192 (16.3 ms) | 6,069 | 104 / 226 | 171 |
| `truenas-ssd` (S3700), pod on the NAS VM | `truenas-worker-01` | 863 (3.9 ms) | 13,685 | 205 / 624 | 351 |
| `truenas-ssd` (S3700), pod remote | GPU worker | 185 (7.7 ms) | 10,564 | 170 / 482 | 159 |
| `truenas-nfs` (BigTank HDD) | GPU worker | 103 (59 ms) | 38,540 | 67 / 561 | over 180 s |
| `nfs-comfyui-10g` (ai-pool) | GPU worker | 270 (41 ms) | 30,846 | 316 / 816 | 164 |

Read the table this way: a second synchronous copy about halves the commit rate, and NFS on
BigTank is too slow for databases and small files. Read IOPS on NFS come partly from the
NAS RAM cache.

Copying a Longhorn volume to a new disk (path 12), 10 GiB of data, one volume at a time:

| Copy | New copy on | Time | MB/s |
|---|---|---:|---:|
| `longhorn`, add a third copy | `truenas-ssd` | 69 s | 162 |
| `flash`, rebuild a lost copy | `truenas-ssd` | 66 s | 169 |

So one volume copies at about 160-170 MB/s, roughly 1 minute per 10 GiB. A drain that
moves many volumes at once ran at 26-51 MB/s per volume. A kopiur restore of a small
database takes 26-37 s, mostly mover start-up.

## Do not export NAS flash over NVMe/TCP

Do not recreate a NAS flash pool exported to the cluster over NVMe/TCP. A test used three
HPE 480 GB drives in a NAS RAIDZ1 pool. The synchronous workload delivered about 437 IOPS,
against about 259 on the Longhorn path it was compared with. The same test hit filesystem
inconsistency after reattachment, missing dataset mounts and leaked exports. The test did
not isolate the cause of the corruption. The gain did not justify those risks.

Repeat a controlled test before you rely on a precise speedup or name a root cause. The
recorded numbers mixed raw-device, filesystem and end-to-end measurements.

Today two HPE drives are in the Threadripper mirror and one is in the NAS boot mirror.
There is no three-drive flash pool on any worker, and no 2.44 TB local-storage expansion.

## Sources of truth

- [Longhorn values](https://github.com/mitchross/talos-argocd-proxmox/blob/main/infrastructure/storage/longhorn/values.yaml)
- [Flash class](https://github.com/mitchross/talos-argocd-proxmox/blob/main/infrastructure/storage/longhorn/storageclass-flash.yaml)
- [Wired two-copy class](https://github.com/mitchross/talos-argocd-proxmox/blob/main/infrastructure/storage/longhorn/storageclass-wired-ha.yaml)
- [Omni disk declarations](https://github.com/mitchross/talos-argocd-proxmox/blob/main/omni/cluster-template/cluster-template-prod-v2.yaml)
- [How kopiur backup and restore work](kopiur-backup-architecture.md)
- [Disaster recovery](../../disaster-recovery.md)
