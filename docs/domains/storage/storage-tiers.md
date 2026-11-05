# Storage tiers

**Status:** current placement contract, checked against the September 5 audit.
Historical experiments are summarized separately below. The
[hardware and placement review](../../audits/2026-09-05-hardware-and-placement-review.md)
proposes changes. This document does not deploy them.

Choose storage by access pattern, durability and required recovery behavior.
The class name does not describe the physical device or prove availability.

| Class | Current backing / selection | Appropriate use and limitation |
|---|---|---|
| `longhorn` (default) | Two V1 replicas on different Longhorn nodes tagged `wired-storage` (no data locality) | App state and databases. One node can fail and the volume stays up. Volumes created before the two-copy default keep the count set on the live Volume. |
| `longhorn-flash` | One replica selected by disk tag `flash`; currently the Threadripper's 440 GiB guest disk on two mirrored HPE SATA SSDs with PLP and thick LVM | Selected write-heavy state and noisy local I/O. The mirror survives one member disk loss; it does not survive loss of the Threadripper host. |
| `longhorn-wired-ha` | Two replicas with hard node/zone/disk separation on Longhorn nodes tagged `wired-storage` | Selected state that needs a surviving live copy. Requires healthy replicas, a working control plane, eligible compute and the rest of the application's dependencies. |
| `truenas-nfs` | TrueNAS BigTank, HDD mirrors behind a large RAM cache, RWX; each PVC is its own dataset with `sync=standard` | Bulk, read-mostly data where NAS downtime is accepted: the immich library, project-nomad downloads. Measured from a pod: fast repeated reads, but only about 50 file creates and 110 `fsync` writes per second, so never databases, Docker/overlay storage or search indexes. |
| Static NFS / SMB classes | The specific NAS share named in each PV | Media, model files and shared data. Inspect the backing dataset: BigTank and the unmirrored AI SSD pool have different failure behavior. |

`longhorn-kopiur-staging-local` is a separate, disposable restore and backup staging
class. Do not select it for authoritative application data. Its clones
land only on disks tagged `clone-ok`: the Threadripper flash disk and `hp-sff-ssd2`. Either disk can take any clone. A dead host no longer blocks clones, but a volume whose only copy is on that host cannot be backed up. Its
WaitForFirstConsumer behavior and the existing Longhorn overprovisioning allowance
support the Kopiur workflow. Include staging claims in capacity planning.

## Placement and ownership

The active Omni template sets up Longhorn data disks on SFF (two disks),
Threadripper, `hp-elite-gen13` and `mini-pc-dell-ultra-worker`. The shed's disks are
registered but have scheduling disabled. The HP Micro in the shed is the machine
behind the Wi-Fi media bridge. `hp-elite-gen12` is compute-only: it has no Longhorn disk.
See the [fleet inventory](../../inventory/2026-11-03-fleet-inventory.md).

The `wired-storage` tag includes SFF, Threadripper, `hp-elite-gen13` and the Dell. The [disk map](disk-map.md) lists once which physical disk holds
what. [Storage architecture](../../storage-architecture.md#two-copies-for-data-that-cant-be-re-created) lists which volumes keep two
copies.

The Omni `node.longhorn.io/default-node-tags` annotation initializes Longhorn
nodes whose tag list is empty. It does not reconcile tags on an
already tagged Longhorn node. For any placement change, handle existing Longhorn
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
identity. Do not delete a PVC because its only replica is temporarily
unreachable. The [storage evidence collector](collecting-storage-evidence.md)
joins claims to actual volumes, replicas and physical-zone labels.

## Performance and durability

Keep three questions apart: are reads cached, do durable writes have
acceptable tail latency, and does another host keep the data after a failure.
A large ARC helps repeated reads. PLP can improve durable-write behavior. A
second Longhorn replica adds a separate host copy and a synchronous network write.
None of these substitutes for the other two.

The Threadripper flash pool uses thick LVM on purpose, after earlier thin-LVM
fsync results were poor. Keep that arrangement until an equivalent end-to-end
measurement justifies a change. The live flash tier also carries Radar NG,
PostHog and monitoring I/O. Do not treat its local mirror as multi-host HA.

NAS bulk streaming and small random I/O have different costs. The historical
HDD-backed small-file test performed poorly and helped motivate the Radar storage
move. That is workload-specific evidence. It does not prove that every database
or every network storage protocol performs badly. Ten-gigabit bandwidth alone
does not establish synchronous-write latency.

At the audit snapshot, `BigTank/k8s` used `sync=disabled` for inspected app
NFS/iSCSI descendants, while `BigTank/k8s/rustfs` explicitly used `sync=standard`.
Choose a dataset's durability contract before comparing database performance.
Accepting service stalls while the NAS is off does not mean accepting loss
of acknowledged writes. The audit changed no ZFS property.

Multiple pods on the same Kubernetes node can mount a Longhorn RWO volume. It is
not a multi-node shared filesystem. Use the repository's Recreate convention for
ordinary RWO Deployments, so rollouts don't attach a volume on two nodes at once.
Longhorn also supports RWX through share-manager pods, but these one-copy RWO classes
don't declare it. Keep NAS RWX for the existing shared-file
use cases unless a separate migration is justified.

## Historical experiment: NAS flash over NVMe/TCP

An earlier experiment used three HPE 480 GB drives in a NAS RAIDZ1 flash pool,
exported through NVMe/TCP. The driver attached, but the recorded
end-to-end synchronous workload delivered about 437 IOPS versus about 259 on
that Longhorn comparison path. The run also hit filesystem inconsistency
after reattachment, missing dataset mounts and leaked exports. The run did not isolate the corruption
cause. That combination did not justify adoption.

The original write-up mixed raw-device, filesystem and end-to-end measurements,
including latency values that are not interchangeable inverses
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
