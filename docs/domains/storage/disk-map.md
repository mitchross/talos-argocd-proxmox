# Disk map: which disk holds what

This page answers two questions for every machine in the lab: which physical disk holds a
given piece of data, and where new data should go. Use it when you place a PVC, add a
disk, or rebuild a host.

The layout was last checked against the live machines on October 15, 2026. Update this
page after every disk change. The [fleet inventory](../../inventory/2026-11-03-fleet-inventory.md)
lists the machines and their RAM. The [full inventory](../../inventory/2026-10-15-full-inventory.md)
has dated capacities and health observations.

## How the layers fit

A byte that an app writes passes through several layers before it reaches a drive. Each
column in the tables below is one layer:

```
Physical drive ─► Proxmox storage ─► VM disk ─► Talos mount ─► Longhorn disk ─► PVC (your app)
 (the SSD)         (LVM on that SSD)   (scsiN)     (/var/mnt/…)    (name + tag)
```

- A Proxmox storage is a named pool of space on one host drive. You create it by hand on
  the host, once. Omni, the tool that creates the Talos VMs, only selects it by name
  (`storage_selector` in `omni/machine-classes/`). See
  [rebuild prerequisites](#rebuild-prerequisites).
- VM disks come from `additional_disks` in the machine class. Omni creates them when it
  creates the VM. A change to the class does not add a disk to a running VM.
- Talos mounts come from `UserVolumeConfig` patches in
  `omni/cluster-template/cluster-template-prod-v2.yaml`. Each patch selects its disk by
  exact size, so every data disk on a node has a different size.
- Longhorn disks register from the `node.longhorn.io/default-disks-config` annotation in
  the same template. Longhorn reads that annotation **once**, when the node first joins.
  On an existing node, also add the disk to the Longhorn node object (see
  [adding a disk](#adding-a-disk-to-a-running-node)).
- Bare-metal workers have no Proxmox layers. Talos runs directly on the drive.

Consumer SSDs wear out from writes. Enterprise SSDs with power-loss protection (PLP)
survive far more writes. The tables mark the class of each drive, so you can put heavy
writers on the right one.

## Proxmox hosts

### Threadripper `.14`, GPU worker (VM 100)

| Physical drive | Class | Proxmox storage | VM disk | Talos mount | Longhorn disk | Holds |
|---|---|---|---|---|---|---|
| PNY CS900 1 TB (`sda`) | consumer SATA | host root + `tr-sda-vmstore` (thick LVM) | `scsi4` 800 GiB | `/var/mnt/longhorn-gpu-bulk` | `gpu-bulk` (tag `gpu-bulk`) | ordinary app volumes for GPU-node pods (photon, project-nomad, small databases) |
| 2× HPE MK000480GWCEV 480 GB (`sdb`+`sdc`, mdadm mirror) | **enterprise, PLP** | `ssd-ent` (thick LVM) | `scsi3` 440 GiB | `/var/mnt/longhorn-ssd-flash` | `ssd-flash` (tags `flash`, `clone-ok`) | heavy writers (`longhorn-flash` class: PostHog, radar-ng, product-bench) and **every kopiur backup clone** |
| EDILOCA EN605 512 GB (`nvme0`) | consumer NVMe | `nvme0-vmstore` (thin) | `scsi0` 16 GiB + `scsi1` 434 GiB | Talos boot + `EPHEMERAL` (`/var`) | `talos-ephemeral` (scheduling **off**) | container images, logs, `emptyDir` |
| EDILOCA EN605 512 GB (`nvme1`) | consumer NVMe | `nvme1-vmstore` (thin) | `scsi2` 450 GiB | `/var/mnt/ai-model-cache` | — | vLLM model cache (`ai-model-cache-local` PV) |

### HP SFF `.21`, control plane (VM 101) + worker

| Physical drive | Class | Proxmox storage | VM disk | Talos mount | Longhorn disk | Holds |
|---|---|---|---|---|---|---|
| Intel DC S3610 400 GB (serial `BTHC650308T8400VGN`) | **enterprise, PLP** | `hp-sff-cp-vmstore` (VG `hp-sff-cp`, thick LVM) | `scsi0` 100 GiB (control plane) | `STATE` + `ETCD` (`/var/lib/etcd`) + `EPHEMERAL` | — | **etcd only.** Never add Longhorn here: it is the only control plane. |
| PNY CS900 1 TB (serial `…01C1`) | consumer SATA | host root + `hp-prodesk-vmstore` (thick LVM) | 128 GiB + 690 GiB (worker) | `/var` + `/var/mnt/longhorn-hp-sff-ssd` | `hp-sff-ssd` (node tag `wired-storage`) | ordinary volumes, second copies |
| PNY CS900 1 TB (serial `…01C5`) | consumer SATA | `hp-sff-ssd2-vmstore` (VG `hp-sff-ssd2`, thick LVM) | 920 GiB (worker) | `/var/mnt/longhorn-hp-sff-ssd2` | `hp-sff-ssd2` (tags `hp-sff-ssd2`, `clone-ok`; `wired-storage`) | ordinary volumes, second copies, backup clones |

The `sdX` letters on this host change when a drive is added. Identify drives by their `/dev/disk/by-id/` serials, not by `sdX`.

### HP Micro `.20`, shed worker (Wi-Fi link)

| Physical drive | Class | Proxmox storage | VM disk | Talos mount | Longhorn disk | Holds |
|---|---|---|---|---|---|---|
| SK hynix BC501 256 GB (`nvme0`) | consumer NVMe | host root + `local-lvm` | 128 GiB | `/var` | — | Talos system |
| PNY CS900 1 TB (`sda`) | consumer SATA | `hp-ssd-vmstore` | 850 GiB | `/var/mnt/longhorn-hp-micro-ssd` | `hp-micro-ssd` (scheduling **off**) | nothing: a Wi-Fi link is too slow and flaky for replicas |

## Bare-metal workers (no Proxmox)

These mini PCs boot from the network into Omni through
[booter](https://github.com/mitchross/talos-argocd-proxmox/blob/main/omni/pi-services/booter/README.md),
which runs on the Raspberry Pi. Talos installs on the NVMe drive that the template selects
with `install.diskSelector` on `disk.serial`. `hp-elite-gen13` and
`mini-pc-dell-ultra-worker` also have a Longhorn disk. `hp-elite-gen12` is compute-only.

| Node | Physical drive | Class | Talos mount | Longhorn disk | Holds |
|---|---|---|---|---|---|
| `mini-pc-dell-ultra-worker` (Dell Pro Micro) | KIOXIA BG7 256 GB NVMe (serial `3GTCT3A8Z438`) | consumer NVMe | system + `/var` | — | Talos system, images, logs, `emptyDir` |
| `mini-pc-dell-ultra-worker` | APPLE SSD SM0256 256 GB SATA (no serial; matched by model) | consumer SATA | `/var/mnt/longhorn-dell-ultra-ssd` | `dell-ultra-ssd` (`wired-storage`) | ordinary volumes |
| `hp-elite-gen12` (HP Elite Mini 800 G9) | Samsung MZVL2256 256 GB NVMe (serial `S63XNA0TC92107`) | consumer NVMe | system + `/var` | — | Talos system, images, logs, `emptyDir` |
| `hp-elite-gen13` (HP Elite Mini 600 G9) | WD SN530 256 GB NVMe (serial `22245M458316`) | consumer NVMe | system + `/var` | — | Talos system, images, logs, `emptyDir` |
| `hp-elite-gen13` | Intel 660p 512 GB NVMe (serial `BTNH9154019K512A`) | consumer **QLC**, past its rated writes | `/var/mnt/longhorn-hp-elite-nvme` | `hp-elite-nvme` (`wired-storage`) | ordinary volumes. **Replace this drive first.** |

## TrueNAS `.133`

The NAS has one 10 GbE port. Only the Threadripper also has 10 GbE. The other
Proxmox hosts reach the NAS at 2.5 GbE. The bare-metal mini PCs and the shed reach it at
1 GbE. [NAS performance and RAM](../../nas-performance.md) has the measurements.

| Pool | Disks | Redundancy | Good for | Not for |
|---|---|---|---|---|
| **BigTank** | 4× HGST 10 TB HDD as two mirrors | survives one disk per mirror | bulk and read-mostly files: media, immich library, project-nomad downloads, the kopiur repo (RustFS) | databases, anything that creates or `fsync`s many small files |
| **ai-pool** | 3 consumer SATA SSDs, striped | **none**. One dead disk loses the pool | model files that can be re-downloaded | anything you can't re-create |
| **Backup10T** | 1× Seagate 10 TB HDD | none | replicated copies of BigTank datasets | primary data |

The NAS also has a mirrored boot pool (T-FORCE 512 GB and HPE 480 GB).
A Samsung 850 EVO 500 GB was visible as `sdk`, outside the imported pools,
on October 15. It is retired, because it failed load tests.

ARC, the ZFS RAM cache, caches reads across all pools. The October 15 sample held
83.3 GiB. The cache size varies with workload and uptime. File creation and `fsync` still
go to the disks. Measured from a pod, NFS created about 50 small files per second and did
about 110 `fsync` writes per second. A local Longhorn volume did about 490 and 460.

## Where should new data go?

| The data is… | Put it on | Why |
|---|---|---|
| A database (Postgres, MySQL, SQLite, Redis with persistence) | `longhorn` (two copies) | databases wait on every write; NFS makes each one slow |
| A heavy writer (ClickHouse, Kafka, tile renderers) | `longhorn-flash` | only the enterprise drive can take that write volume |
| Bulk, read-mostly files (media, downloads, archives, photo libraries) | `truenas-nfs` | lots of space, no SSD wear, served from the NAS RAM cache |
| A cache that rebuilds itself | `longhorn`, sized to what it really uses | small and local; never back it up |
| Anything that runs Docker/overlay storage or an embedded search engine | `longhorn` | overlay filesystems and search-index locking don't work well on NFS |

Size each PVC to what the app uses plus headroom. Do not make it large "to be safe".
Longhorn reserves the full requested size on a disk, so oversized volumes use up a disk's
reservations long before the disk is physically full.
[Pick a StorageClass](storage-tiers.md) describes each class.

## Rebuild prerequisites

A cluster rebuild keeps the Proxmox hosts, so their storages survive. A Proxmox
reinstall on a host does not keep them. After you **reinstall Proxmox** on a host,
recreate its storages before Omni creates VMs there. If you do not, Omni fails with
"no matching storage".

On the Threadripper, the Proxmox installer creates a `local-lvm` thin pool on the PNY boot
SSD (`sda`, VG `pve`). Replace it with thick LVM:

```bash
# On 192.168.10.14 as root. Removes the empty installer thin pool; check `lvs` first.
pvesm remove local-lvm
lvremove -y pve/data
pvesm add lvm tr-sda-vmstore --vgname pve --content images
pvesm status | grep tr-sda-vmstore     # expected: active
```

Every other storage name that the machine classes select must also exist with that exact
name: `nvme0-vmstore`, `nvme1-vmstore`, `ssd-ent`, `hp-sff-cp-vmstore`,
`hp-prodesk-vmstore`, `hp-sff-ssd2-vmstore`, `hp-ssd-vmstore` and `local-lvm`. Check each
host with `pvesm status`.

## Adding a disk to a running node

1. Create the Proxmox storage on the host, as in the section above. Add the disk to
   `additional_disks` in the machine class, so a rebuilt VM gets it.
2. Attach the disk to the running VM. The class change alone does not attach it.
   `qm set <vmid> --scsiN <storage>:<GiB>,aio=io_uring,cache=none,discard=on,iothread=1,ssd=1`
3. Add a `UserVolumeConfig` and the Longhorn disk entry to the node's section of the
   cluster template, **at the end of that section**. Patch IDs are numbered by position,
   so an entry in the middle renames the existing patches. VM disks report no serial.
   Select the disk by a minimum size that no existing disk on the node meets, for example
   `disk.size >= 900u * GB`. Run `omnictl cluster template diff`, then `sync`.
4. Register the disk on the live Longhorn node. The annotation applies only to new nodes.
   ```bash
   kubectl -n longhorn-system edit nodes.longhorn.io <node>   # add it under spec.disks
   ```
5. Confirm that Talos lists the volume for its weekly trim, which needs no configuration:
   `talosctl -n <node> get volumetrimschedules`.

## Moving a volume to another disk on the same node

To move a one-copy volume, add a second copy on the target disk, wait until the volume
is healthy, then remove the old copy. Two settings block this when both disks are on the
same node:

- Longhorn is set to never keep two copies of a volume on one node
  (`replica-soft-anti-affinity: false`). It refuses the second copy with
  "tags not fulfilled". Allow two copies on one node for that one volume during the move.
- When the copy count goes back to 1, Longhorn chooses which copy to delete, and it can
  choose the copy on the target disk. Delete the **old** copy yourself first, then lower
  the count.

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

Longhorn refuses to delete the last healthy copy. A mistake in this order therefore
stops the move and does not lose data.

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

## Related

- [Pick a StorageClass](storage-tiers.md) describes each class.
- [Disk writes](disk-writes.md) lists the rules that limit SSD wear.
- [Storage architecture](../../storage-architecture.md) covers placement, copy counts and the backup summary.
- [NAS performance and RAM](../../nas-performance.md) has the NAS measurements.
