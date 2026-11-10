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
| `longhorn-flash` | One replica selected by disk tag `flash`; currently the Threadripper's 440 GiB guest disk on two mirrored HPE SATA SSDs with PLP and thick LVM | Selected write-heavy state and noisy local I/O. The mirror survives one member disk loss; it does not survive loss of the Threadripper host. |
| `longhorn-wired-ha` | Two replicas with hard node/zone/disk separation on Longhorn nodes tagged `wired-storage` | Selected state that needs a surviving live copy. Requires healthy replicas, a working control plane, eligible compute and the rest of the application's dependencies. |
| `truenas-nfs` | TrueNAS BigTank, HDD mirrors behind a large RAM cache, RWX; each PVC is its own dataset with `sync=standard` | Bulk, read-mostly data where NAS downtime is accepted: the immich library, project-nomad downloads. Measured from a pod: fast repeated reads, but only about 50 file creates and 110 `fsync` writes per second, so never databases, Docker/overlay storage or search indexes. |
| Static NFS / SMB classes | The specific NAS share named in each PV | Media, model files and shared data. Inspect the backing dataset: BigTank and the unmirrored AI SSD pool have different failure behavior. |

Terms in the table: a replica is one full copy of a Longhorn volume on one node. PLP is
power-loss protection, which lets an SSD finish its writes when power fails. RWX means
several nodes can mount the volume at once. RWO means one node at a time.

For the common cases, use this short list. The disk map has the
[full placement table](disk-map.md#where-should-new-data-go).

- A database or ordinary app state goes on `longhorn`.
- A heavy writer, such as ClickHouse or Kafka, goes on `longhorn-flash`.
- Bulk, read-mostly files go on `truenas-nfs`.

Do not use `longhorn-kopiur-staging-local` for application data. kopiur uses it for the
temporary volume clones that backups and restores read. Its clones land only on disks
tagged `clone-ok`: the Threadripper flash disk and `hp-sff-ssd2`. Either disk can take any
clone, so one dead host does not block backups. A volume whose only copy is on the dead
host still cannot be backed up. The class uses `WaitForFirstConsumer` binding, and it
depends on the Longhorn overprovisioning allowance. Count the staging clones when you plan
capacity.

## Which nodes hold Longhorn data

The Omni cluster template sets up Longhorn data disks on the HP SFF worker (two disks),
the Threadripper, `hp-elite-gen13` and `mini-pc-dell-ultra-worker`. Those four nodes carry
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
