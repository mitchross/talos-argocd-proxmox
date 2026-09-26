# Storage audit — September 26, 2026

**What this is:** a measured snapshot of disk writes, disk space and NAS health
across Proxmox, TrueNAS and Kubernetes, taken to stop the consumer SSDs wearing
out. The current layout it produced is in the [disk map](../domains/storage/disk-map.md);
this page keeps the numbers behind it.

## Disk writes

Physical drives only (LVM `dm-*` and RAID `md*` layers excluded, NAS excluded):

| Day | TB written |
|---|---:|
| Sep 22–25 (before the write fixes took effect) | about 3.4 per day |
| Sep 25–26 | **1.3** |

The largest remaining writer is the Threadripper's enterprise mirror (about
526 GB/day on each HPE drive), a steady ~16 GB/hour from GPU-node app volumes
(open-meteo, PostHog ClickHouse, radar-ng workers). That is the drive built for it.
Proxmox itself writes only 2–3 GB/day per host.

| Consumer drive | Wear | Written last 24 h |
|---|---|---:|
| hp-elite Intel 660p (Longhorn) | 75% used, 214 TB written (rated ~200 TB) | 30 GB |
| hp-elite WD SN530 (Talos system) | 3% used | 93 GB |
| hp-sff PNY CS900 ×2 | 93% life left | 38 GB and 17 GB |
| Dell Samsung 850 EVO (Longhorn) | about 29% used | 19 GB |

## Disk space (Longhorn)

Longhorn reserves a volume's full requested size on a disk. At the audit:

- 73 volumes requested 2,081 GiB but stored only 365 GiB.
- The GPU node's enterprise disk (`ssd-flash`, 440 GiB, overprovisioning 200%)
  was booked 772 of 880 GiB. Because backup clones can only use this disk, a
  150 GiB immich clone could not be placed and that backup hung for 14 hours.
- The 11 two-replica volumes stored about 16 GiB and added roughly 25–30 GB/day
  of writes: cheap for what they protect.
- About 2.5 TB of consumer SSD was idle: the Threadripper boot SSD's 807 GB,
  hp-sff's second SSD (kept for etcd), and the shed SSD (Wi-Fi, unusable for replicas).

Changes made: the idle Threadripper space became the `gpu-bulk` Longhorn disk;
the immich library and project-nomad downloads moved to the NAS; photon,
imagery and the CI Docker cache were resized to what they use.

## NAS (TrueNAS `.133`)

| Finding | Detail |
|---|---|
| Capacity | BigTank 7.5 TB free of 18.2 TB; about 3.9 TB can be added before 80% full |
| Cache | 346 GB ARC, about 98% of reads served from RAM |
| **No off-box copy** | Nothing is replicated or synced off the NAS. The kopiur repository (RustFS) also lives on BigTank, so losing the NAS loses its data *and* every Kubernetes backup. |
| **Local replication stale** | The BigTank → Backup10T replication task has no schedule; its last run was May 2025. `organized_backups` is not on Backup10T at all. |
| ai-pool has no redundancy | 3 consumer SSDs striped. The HP S700 shows 816 UDMA CRC errors (usually a cable). |
| Boot pool | 141 of 222 GB used: about 30 old boot environments and 22 GB of model files in the admin home folder |
| HDD temperatures | 43–57 °C against a 60 °C stop threshold |
| Reclaimable datasets | `k8s/ollama` (152 GB; Ollama is not used here), `k8s/volsync-kopia-nfs` (28 GB; VolSync is retired), `k8s/llama-cpp-archive` (104 GB), `benchmark` (12 GB) |

Cleaned up the same day: the old boot environments (all but the running one and
the two before it) and the home-folder model files (boot pool now 42 GB used), and
the `ollama`, `volsync-kopia-nfs` and `benchmark` datasets with their shares.
`llama-cpp-archive` is kept on purpose.

NFS performance from a pod is in [NAS performance](../nas-performance.md#from-a-kubernetes-pod-over-nfs-measured).

## Found along the way

- The weekly GPU-node `talos-fstrim` job listed a mount that no longer exists
  (`/var/mnt/longhorn-nvme1`). Its script stops at the first error, so the
  enterprise flash disk was never trimmed. The target list is fixed.
- The TrueNAS CSI driver's ZFS snapshots and clones work, but deleting a
  VolumeSnapshot while its clone still exists leaves the ZFS snapshot behind.
  NAS-backed kopiur policies use `copyMethod: Direct` so no snapshot is taken.
