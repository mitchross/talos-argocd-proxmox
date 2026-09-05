# Storage tiers

**Status:** current placement contract, checked against the September 5 audit.
Historical experiments are summarized separately below. The
[hardware and placement review](../../audits/2026-09-05-hardware-and-placement-review.md)
contains proposed changes; they are not deployed by this document.

Choose storage by access pattern, durability and required recovery behavior.
The class name alone does not describe the physical device or prove availability.

| Class | Current backing / selection | Appropriate use and limitation |
|---|---|---|
| `longhorn` (default) | One V1 replica on an eligible Longhorn disk. Live claims span Threadripper, SFF, Elite and Dell; the latter three use dedicated data disks, not their Talos boot filesystems. | Small app state and caches with an explicit one-copy availability trade-off. Kopiur protects enrolled state, but a backup does not provide immediate failover. |
| `longhorn-flash` | One replica selected by disk tag `flash`; currently the Threadripper's 300 GB guest disk on two mirrored HPE SATA SSDs with PLP and thick LVM | Selected write-heavy state and noisy local I/O. The mirror survives one member disk loss; it does not survive loss of the Threadripper host. |
| `longhorn-wired-ha` | Two replicas with hard node/zone/disk separation on Longhorn nodes tagged `wired-storage` | Selected state that needs a surviving live copy. Requires healthy replicas, a working control plane, eligible compute and the rest of the application's dependencies. |
| `truenas-nfs` | TrueNAS BigTank, HDD-backed, RWX | Shared files and bulk data where NAS downtime is accepted. Measure small-file and synchronous-write workloads before moving them here. |
| Static NFS / SMB classes | The specific NAS share named in each PV | Media, model files and shared data. Inspect the backing dataset: BigTank and the unmirrored AI SSD pool have different failure behavior. |

`longhorn-kopiur-staging-local` is a separate, disposable restore/backup staging
mechanism. Do not select it for authoritative application data. Its
WaitForFirstConsumer behavior and the existing Longhorn overprovisioning allowance
support the Kopiur workflow; capacity planning must include staging claims.

## Placement and ownership

The active Omni template configures Longhorn data disks on SFF, Elite, Dell and
Threadripper. The shed's disks are registered but have scheduling disabled. Dell
is wired; the HP Micro in the shed is the machine behind the Wi-Fi media bridge.
See the [dated physical inventory](../../audits/2026-09-05-inventory.md).

The `wired-storage` tag currently includes SFF, Elite and Dell. Temporal Postgres
is the existing two-copy user; at the audit snapshot its copies were on Dell and
Elite. The proposed design moves durable responsibility toward SFF/Elite after
qualification and a healthy replacement copy. That migration is not complete.

The Omni `node.longhorn.io/default-node-tags` annotation initializes Longhorn
nodes whose tag list is empty. It does not continuously reconcile tags on an
already tagged Longhorn node. Any placement change must handle existing Longhorn
node state through a reviewed GitOps mechanism and verify actual replica locations.

Read-only inspection:

```sh
kubectl -n longhorn-system get nodes.longhorn.io -o custom-columns='NAME:.metadata.name,TAGS:.spec.tags'
kubectl get nodes -L topology.kubernetes.io/zone
```

Expected current tags include the three wired workers above. The SFF's two Talos
VMs share the `hp-sff` physical-host zone. A node tag is eligibility, not proof
that an individual volume has two healthy copies.

Changing a StorageClass does not migrate existing PVCs. Use the
[PVC migration runbook](pvc-storageclass-migration.md) and preserve Kopiur backup
identity. Do not delete a PVC merely because its only replica is temporarily
unreachable. The [storage evidence collector](collecting-storage-evidence.md)
joins claims to actual volumes, replicas and physical-zone labels.

## Performance and durability

Separate three questions: whether reads are cached, whether durable writes have
acceptable tail latency, and whether another host retains the data after failure.
A large ARC helps repeated reads. PLP can improve durable-write behavior. A
second Longhorn replica adds a separate host copy and a synchronous network write.
None of these is a substitute for the other two.

The Threadripper flash pool deliberately uses thick LVM after earlier thin-LVM
fsync results were poor. Keep that arrangement until an equivalent end-to-end
measurement justifies a change. The live flash tier also absorbs Radar NG,
PostHog and monitoring I/O. Do not treat its local mirror as multi-host HA.

NAS bulk streaming and small random I/O have different costs. The historical
HDD-backed small-file test performed poorly and helped motivate the Radar storage
move. That is useful workload-specific evidence, not proof that every database
or every network storage protocol must perform badly. Ten-gigabit bandwidth alone
does not establish synchronous-write latency.

At the audit snapshot, `BigTank/k8s` used `sync=disabled` for inspected app
NFS/iSCSI descendants, while `BigTank/k8s/rustfs` explicitly used `sync=standard`.
Choose a dataset's durability contract before comparing database performance.
Accepting service stalls while the NAS is off does not automatically accept loss
of acknowledged writes. No ZFS property was changed during the audit.

Longhorn RWO can be mounted by multiple pods on the same Kubernetes node; it is
not a multi-node shared filesystem. Use the repository's Recreate convention for
ordinary RWO Deployments to avoid cross-node overlapping rollout attachments.
Longhorn also supports RWX through share-manager infrastructure, but that is not
what these one-copy RWO classes declare. Keep NAS RWX for the existing shared-file
use cases unless a separate migration is justified.

## Historical experiment: NAS flash over NVMe/TCP

An earlier experiment used three HPE 480 GB drives in a NAS RAIDZ1 flash pool,
exported through NVMe/TCP. The driver attached successfully, but the recorded
end-to-end synchronous workload delivered about 437 IOPS versus about 259 on
that Longhorn comparison path. The run also encountered filesystem inconsistency
after reattachment, missing dataset mounts and leaked exports. The corruption
cause was not conclusively isolated. That combination did not justify adoption.

The original write-up mixed raw-device, filesystem and end-to-end measurements,
including latency values that should not be treated as interchangeable inverses
of the reported IOPS. It also made general claims about all network databases
that the experiment did not establish. Raw history remains in Git; repeat a
controlled test before relying on a precise speedup or assigning a root cause.

The current physical layout is two HPE drives in the Threadripper mirror and
one HPE in the NAS boot mirror. There is no current three-drive worker flash
pool or automatic 2.44 TB local-storage expansion. Do not recreate the retired
NVMe/TCP experiment from historical prose.

## Sources of truth

- [Longhorn values](https://github.com/mitchross/talos-argocd-proxmox/blob/main/infrastructure/storage/longhorn/values.yaml)
- [Flash class](https://github.com/mitchross/talos-argocd-proxmox/blob/main/infrastructure/storage/longhorn/storageclass-flash.yaml)
- [Wired two-copy class](https://github.com/mitchross/talos-argocd-proxmox/blob/main/infrastructure/storage/longhorn/storageclass-wired-ha.yaml)
- [Omni disk declarations](https://github.com/mitchross/talos-argocd-proxmox/blob/main/omni/cluster-template/cluster-template-prod-v2.yaml)
- [Kopiur backup contract](kopiur-backup-architecture.md)
- [Disaster recovery](../../disaster-recovery.md)
