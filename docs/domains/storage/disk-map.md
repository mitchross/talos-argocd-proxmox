# Disk map: every disk, what it holds, and where data should go

**Purpose:** one page that answers "which physical disk is this data on?" for
every machine in the lab, and "where should new data go?".
**Status:** current layout. Update this page in the same PR as any disk change.

## How the layers fit

A byte written by an app passes through up to five layers. Each column in the
tables below is one of them:

```
Physical drive ─► Proxmox storage ─► VM disk ─► Talos mount ─► Longhorn disk ─► PVC (your app)
 (the SSD)         (LVM on that SSD)   (scsiN)     (/var/mnt/…)    (name + tag)
```

- **Proxmox storage** is created by hand on the host, once. Omni only *picks* it
  by name (`storage_selector` in `omni/machine-classes/`). See
  [rebuild prerequisites](#rebuild-prerequisites).
- **VM disks** come from `additional_disks` in the machine class. Omni creates them
  when it creates the VM; changing the class does not add a disk to a running VM.
- **Talos mounts** come from `UserVolumeConfig` patches in
  `omni/cluster-template/cluster-template-prod-v2.yaml`. Each selects its disk by
  exact size, which is why every data disk on a node has a different size.
- **Longhorn disks** are registered from the `node.longhorn.io/default-disks-config`
  annotation in the same template. That annotation is read **once**, when the node
  first joins Longhorn; on an existing node, add the disk to the Longhorn node object
  too (see [adding a disk](#adding-a-disk-to-a-running-node)).

Consumer SSDs wear out from writes. Enterprise SSDs (with power-loss protection,
"PLP") survive far more. The tables mark each drive so heavy writers land on the
right one.

## Proxmox hosts

### Threadripper `.14` — GPU worker (VM 100)

| Physical drive | Class | Proxmox storage | VM disk | Talos mount | Longhorn disk | Holds |
|---|---|---|---|---|---|---|
| PNY CS900 1 TB (`sda`) | consumer SATA | host root + `tr-sda-vmstore` (thick LVM) | `scsi4` 800 GiB | `/var/mnt/longhorn-gpu-bulk` | `gpu-bulk` (tag `gpu-bulk`) | ordinary app volumes for GPU-node pods (photon, project-nomad, small databases) |
| 2× HPE MK000480GWCEV 480 GB (`sdb`+`sdc`, mdadm mirror) | **enterprise, PLP** | `ssd-ent` (thick LVM) | `scsi3` 440 GiB | `/var/mnt/longhorn-ssd-flash` | `ssd-flash` (tags `flash`, `clone-ok`) | heavy writers (`longhorn-flash` class: PostHog, radar-ng, Prometheus, Loki) and **every kopiur backup clone** |
| EDILOCA EN605 512 GB (`nvme0`) | consumer NVMe | `nvme0-vmstore` (thin) | `scsi0` 16 GiB + `scsi1` 434 GiB | Talos boot + `EPHEMERAL` (`/var`) | `talos-ephemeral` (scheduling **off**) | container images, logs, `emptyDir` |
| EDILOCA EN605 512 GB (`nvme1`) | consumer NVMe | `nvme1-vmstore` (thin) | `scsi2` 450 GiB | `/var/mnt/ai-model-cache` | — | vLLM model cache (`ai-model-cache-local` PV) |

### HP SFF `.21` — control plane (VM 101) + worker

| Physical drive | Class | Proxmox storage | VM disk | Talos mount | Longhorn disk | Holds |
|---|---|---|---|---|---|---|
| PNY CS900 1 TB (`sda`) | consumer SATA | `hp-sff-cp-vmstore` | 100 GiB (control plane) | `EPHEMERAL` + `ETCD` | — | **etcd only.** Never add Longhorn here: it is the only control plane. |
| PNY CS900 1 TB (`sdb`) | consumer SATA | host root + `hp-prodesk-vmstore` (thick LVM) | 128 GiB + 690 GiB (worker) | `/var` + `/var/mnt/longhorn-hp-sff-ssd` | `hp-sff-ssd` (node tag `wired-storage`) | ordinary volumes, second copies |

### HP Elite `.22` — worker

| Physical drive | Class | Proxmox storage | VM disk | Talos mount | Longhorn disk | Holds |
|---|---|---|---|---|---|---|
| WD SN530 256 GB (`nvme1`) | consumer NVMe | host root + `local-lvm` | 128 GiB | `/var` | — | Talos system |
| Intel 660p 512 GB (`nvme0`) | consumer **QLC**, past its rated writes | `hp-elite-vmstore` | 440 GiB | `/var/mnt/longhorn-hp-elite-nvme` | `hp-elite-nvme` (`wired-storage`) | ordinary volumes, Home Assistant. **Replace this drive first.** |

### Dell `.16` — worker

| Physical drive | Class | Proxmox storage | VM disk | Talos mount | Longhorn disk | Holds |
|---|---|---|---|---|---|---|
| Apple SM0256G (`sdb`) | consumer SATA | host root + `local-lvm` | 128 GiB | `/var` | — | Talos system |
| Samsung 850 EVO 500 GB (`sda`) | consumer SATA | `dell-ssd-vmstore` | 400 GiB | `/var/mnt/longhorn-dell-ssd` | `dell-ssd` (`wired-storage`) | ordinary volumes, second copies |

### HP Micro `.20` — shed worker (Wi-Fi link)

| Physical drive | Class | Proxmox storage | VM disk | Talos mount | Longhorn disk | Holds |
|---|---|---|---|---|---|---|
| SK hynix BC501 256 GB (`nvme0`) | consumer NVMe | host root + `local-lvm` | 128 GiB | `/var` | — | Talos system |
| PNY CS900 1 TB (`sda`) | consumer SATA | `hp-ssd-vmstore` | 850 GiB | `/var/mnt/longhorn-hp-micro-ssd` | `hp-micro-ssd` (scheduling **off**) | nothing: a Wi-Fi link is too slow and flaky for replicas |

## TrueNAS `.133`

The NAS has one 10 GbE port. Only the Threadripper also has 10 GbE; the other
hosts reach it at 2.5 GbE (the shed at 1 GbE).

| Pool | Disks | Redundancy | Good for | Not for |
|---|---|---|---|---|
| **BigTank** | 4× HGST 10 TB HDD as two mirrors | survives one disk per mirror | bulk and read-mostly files: media, immich library, project-nomad downloads, the kopiur repo (RustFS) | databases, anything that creates or `fsync`s many small files |
| **ai-pool** | 3 consumer SATA SSDs, striped | **none** — one dead disk loses the pool | model files that can be re-downloaded | anything you can't re-create |
| **Backup10T** | 1× Seagate 10 TB HDD | none | replicated copies of BigTank datasets | primary data |

About 346 GB of RAM cache (ZFS ARC) sits in front of all pools, so repeated reads are fast
even from the HDDs. File creation and `fsync` still go to the disks: measured
from a pod, NFS created about 50 small files per second and did about 110
`fsync` writes per second, against about 490 and 460 for a local Longhorn volume.

## Where should new data go?

| The data is… | Put it on | Why |
|---|---|---|
| A database (Postgres, MySQL, SQLite, Redis with persistence) | `longhorn` (or `longhorn-wired-ha` if it must survive a node loss) | databases wait on every write; NFS makes each one slow |
| A heavy writer (ClickHouse, time-series, tile renderers) | `longhorn-flash` | only the enterprise drive can take that write volume |
| Bulk, read-mostly files (media, downloads, archives, photo libraries) | `truenas-nfs` | lots of space, no SSD wear, served from the NAS RAM cache |
| A cache that rebuilds itself | `longhorn`, sized to what it really uses | small and local; never back it up |
| Anything that runs Docker/overlay storage or an embedded search engine | `longhorn` | overlay filesystems and search-index locking don't work well on NFS |

Size PVCs to what the app uses plus headroom, not "big to be safe". Longhorn
reserves the full requested size on a disk, and oversized volumes are what fill a
disk's bookings long before it is physically full.

## Rebuild prerequisites

Nuking and rebuilding the cluster keeps the Proxmox hosts, so their storages
survive. After **reinstalling Proxmox** on a host, recreate its storages before
Omni provisions VMs there, or provisioning fails with "no matching storage".

Threadripper, PNY boot SSD (`sda`, VG `pve`): Proxmox's installer creates a
`local-lvm` thin pool here. Replace it with thick LVM:

```bash
# On 192.168.10.14 as root. Removes the empty installer thin pool; check `lvs` first.
pvesm remove local-lvm
lvremove -y pve/data
pvesm add lvm tr-sda-vmstore --vgname pve --content images
pvesm status | grep tr-sda-vmstore     # expected: active
```

Every other storage name the machine classes select (`nvme0-vmstore`,
`nvme1-vmstore`, `ssd-ent`, `hp-sff-cp-vmstore`, `hp-prodesk-vmstore`,
`hp-elite-vmstore`, `dell-ssd-vmstore`, `hp-ssd-vmstore`, `local-lvm`) must also
exist with that exact name. Check each host with `pvesm status`.

## Adding a disk to a running node

1. Create the Proxmox storage on the host (as above) and add the disk to the
   machine class `additional_disks`, so a rebuilt VM gets it.
2. Attach it to the running VM (the class change alone does not):
   `qm set <vmid> --scsiN <storage>:<GiB>,aio=io_uring,cache=none,discard=on,iothread=1,ssd=1`
3. Add a `UserVolumeConfig` (unique exact size) and the Longhorn disk entry to the
   node's section of the cluster template, **at the end of that section** — patch
   IDs are numbered by position, so inserting in the middle renames existing patches.
   Then `omnictl cluster template diff`, then `sync`.
4. Register the disk on the live Longhorn node (the annotation only applies to new nodes):
   ```bash
   kubectl -n longhorn-system edit nodes.longhorn.io <node>   # add it under spec.disks
   ```
5. If the disk is on the GPU node, add its mount to
   `infrastructure/storage/talos-fstrim/scripts/trim-node-filesystems.sh`.

## Moving a volume to another disk on the same node

Most volumes have one copy. To move it, add a second copy on the new disk, wait
until the volume is healthy, then remove the old copy. Two settings get in the way
when both disks are on the **same node**:

- Longhorn is set to never keep two copies of a volume on one node
  (`replica-soft-anti-affinity: false`), so the second copy is refused with
  "tags not fulfilled". Allow it for that one volume during the move.
- When the copy count drops back to 1, Longhorn chooses which copy to delete, and
  it may pick the new one. Delete the **old** copy yourself first, then lower the count.

```bash
V=$(kubectl -n <ns> get pvc <pvc> -o jsonpath='{.spec.volumeName}')
kubectl -n longhorn-system patch volumes.longhorn.io $V --type merge \
  -p '{"spec":{"diskSelector":["gpu-bulk"],"replicaSoftAntiAffinity":"enabled","numberOfReplicas":2}}'
kubectl -n longhorn-system get volumes.longhorn.io $V -o jsonpath='{.status.robustness}'   # wait for: healthy
kubectl -n longhorn-system get replicas.longhorn.io -l longhornvolume=$V                  # note the OLD copy's name
kubectl -n longhorn-system delete replicas.longhorn.io <old-copy>
kubectl -n longhorn-system patch volumes.longhorn.io $V --type merge \
  -p '{"spec":{"numberOfReplicas":1,"replicaSoftAntiAffinity":"ignored"}}'
```

Longhorn refuses to delete the last healthy copy, so a mistake in this order
cannot lose data. It just stops.

## Check the live layout

```bash
# Longhorn disks, their tags, and how much is booked vs. free
kubectl -n longhorn-system get nodes.longhorn.io -o json | jq -r '.items[] as $n
  | $n.spec.disks | to_entries[] | "\($n.metadata.name) \(.key) tags=\(.value.tags) sched=\(.value.allowScheduling)"'

# Disks as Talos sees them on one node (through Omni)
talosctl -n <node> get disks
talosctl -n <node> get discoveredvolumes

# Proxmox side
ssh root@<host> 'pvesm status; lvs; qm config <vmid> | grep ^scsi'
```

Related: [storage tiers](storage-tiers.md) (classes), [disk writes](disk-writes.md)
(write budget), [storage architecture](../../storage-architecture.md) (backups),
[NAS performance](../../nas-performance.md).
