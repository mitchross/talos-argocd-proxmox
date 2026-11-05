# Storage model: RWO vs RWX, truenas-csi, and capacity sizing

Storage-class decisions and capacity sizing across the core repo
(`talos-argocd-proxmox`, production Talos) and the multicluster fork
(`talos-argocd-proxmox-multicluster-test`, OpenShift/SNO).

## TL;DR

- **Static SMB/NFS shares stay on the plain CSI drivers** (`csi-driver-nfs`,
  `csi-driver-smb`). They hold real data you browse and edit by hand. Keep them
  human-readable and decoupled from the TrueNAS API. `truenas-csi`
  (`csi.truenas.io`) is for **dynamic provisioning only**. It supports
  **iSCSI, NVMe-oF, and NFS, but not SMB**.
- **Talos:** **Longhorn is the default for RWO** (block, node-local). Use
  truenas-csi **NFS (`truenas-nfs`) for RWX**. Use **`truenas-flash` (NVMe-oF)
  for write-latency-sensitive RWO**, such as databases. Rationale (measured
  2026-07-13): Longhorn's backing disks are consumer EDILOCA NVMe at **259 fsync
  IOPS @ 1.25ms**. The flashpool SSDs do **14,484 @ 0.064ms**. Even with ~0.15ms
  of 10GbE round-trip, that is ~6x better for the fsync-per-commit workload
  databases run. Longhorn still wins for read-heavy volumes and RWX-via-share.
- **Do not add truenas-csi *iSCSI* on Talos.** The reason previously given here
  was wrong. `siderolabs/iscsi-tools` is in fact **already installed on all
  three machine sets**, and `CONFIG_ISCSI_TCP=y` is built into the Talos 1.13
  kernel. The real blocker is that upstream never reads `iscsi.global.basename`
  (truenas-csi#41). This appliance still has the FreeNAS-era base name
  `iqn.2005-10.org.freenas.ctl`. A mismatch fails every stage with `failed to
  find device path: []` *and* bakes the wrong IQN into the PV at provision time.
  NVMe-oF avoids the problem. TCP 3260 stays blocked in Cilium. TCP 4420 is now
  allowed.
- **OpenShift/SNO:** no Longhorn. Use `vanillax-local-rwo` for RWO and DBs
  (`csi.truenas.io` **iSCSI**, block, safe for databases). Use `truenas-nfs-csi`
  (NFS) for RWX. Use `local-path` (node-local) for regenerable caches.

## How to decide RWO vs RWX

> **Count the pods that mount the same `claimName`. One means RWO. Two or more means RWX.**

Signals, in order of reliability:

1. **Same `claimName` in 2+ different pods or Deployments.** Use RWX. Grep the
   app for the claim name. Example: radar-ng `tiles`/`grids`/`state` are mounted
   by `tile-server` (3 replicas) **and** `temporal-worker` (3 replicas), which is
   6 pods.
2. **Workload kind.** A `Deployment replicas:1` or a one-off `Job` uses RWO.
   A `StatefulSet` uses RWO, because each replica gets its *own* volume via
   `volumeClaimTemplates`. A StatefulSet is not RWX. A `Deployment replicas:2+`
   sharing one PVC uses RWX.
3. **Data type.** Databases (Postgres/MySQL/ClickHouse/Redis/SQLite) are
   **always RWO**, never NFS. Shared media libraries used by multiple apps are
   RWX.

Default to **RWO**. Choose RWX only when you can name the second pod that needs the
same files. In a homelab ~99% of apps are RWO. RWX is the media-stack exception.

## Per-cluster storage class map

| Need | Talos (core) | OpenShift (fork) |
|------|--------------|------------------|
| RWO / block / DBs | `longhorn` (or portable `vanillax-local-rwo` → Longhorn) | `vanillax-local-rwo` = `csi.truenas.io` iSCSI |
| RWX / shared | `truenas-nfs` (`csi.truenas.io` NFS) | `truenas-nfs-csi` (`csi.truenas.io` NFS) |
| Static media/models (browseable) | `csi-driver-nfs` / `csi-driver-smb` | `csi-driver-nfs` / `csi-driver-smb` |
| Regenerable node-local cache | (Longhorn) | `local-path` |

Both clusters configure `csi.truenas.io` the same way. A `truenas-csi-config`
ConfigMap holds the connection, `defaultPool: BigTank`, and
`nfsServer`/`iscsiPortal`. StorageClasses add `pool` and `datasetPath` as
parameters. Core's `truenas-nfs` nests under `BigTank/k8s/nfs/v` with
`reclaimPolicy: Retain`.

## TrueNAS layout (192.168.10.133)

Pools: `BigTank` (the CSI `defaultPool`), `ai-pool`, `Backup10T`, `backuptank`.

- Kubernetes data lives under **`BigTank/k8s`** (children: comfyui, frigate, iscsi,
  jellyfin-media, …). Path: `BigTank/k8s` (Sync DISABLED, ZSTD).
- **Important:** some static model shares live on **`ai-pool`, not BigTank**.
  For example, comfyui/swarmui models both mount the same export
  `192.168.10.133:/mnt/ai-pool/comfyui`. These do **not** count against BigTank.

### Static vs dynamic (and the GUID question)

- **Dynamic** volumes are named after the PV UID, as zvol or dataset
  `BigTank/pvc-<uuid>`. The name is opaque, so do not hand-edit it. The PV's
  `volumeHandle` (in etcd) links the GUID to the app, not the name.
- `reclaimPolicy: Delete` destroys the TrueNAS dataset when the PVC is deleted.
  `Retain` keeps it. The PV goes `Released` and needs manual `claimRef` clearing
  to rebind.
- **Restore is a separate layer from the CSI driver.** On Talos, kopiur restores
  *contents* into a fresh GUID volume, keyed by PVC name and namespace.
  **OpenShift has no kopiur**, so dynamic volumes there have **no backup**. For
  OpenShift DR, use **TrueNAS native ZFS snapshot tasks** on a parent dataset.
  Nest dynamic volumes under, for example, `BigTank/k8s/csi`, so one recursive
  snapshot protects all `pvc-*` regardless of GUID.

## Capacity sizing

These are **requests**, not usage (ZFS is thin-provisioned).

| Bucket | Capacity | Notes |
|--------|----------|-------|
| RWO block (full app catalog) | ~1.11 TiB | On **Talos this is Longhorn**, not BigTank. Only counts against BigTank on **OpenShift** (iSCSI). |
| RWX static shares | ~4.48 TiB | Already exist on the box; some on **ai-pool** (comfyui/swarmui/llama models), not BigTank. |
| RWX dynamic (radar-ng → NFS) | ~205 GiB | `truenas-nfs` on Talos / `truenas-nfs-csi` on OpenShift. |
| Grand total of requests | ~5.75 TiB | Excludes the 250Gi swarmui/comfyui double-count. |

New provisioning that hits BigTank:

- OpenShift: ~1.2 TiB (RWO iSCSI + radar-ng NFS, with ~112Gi of caches on
  `local-path`).
- Talos: ~205 GiB (radar-ng NFS; everything else is Longhorn).

Both fit well under BigTank's 8.54 TiB free. Static ai-pool shares do not count
against BigTank. The swarmui/comfyui double-count is excluded.

### `local-path` candidates (OpenShift)

These are regenerable, node-local, and have no TrueNAS dependency: `gitea-actions` docker-cache
(50Gi), `swarmui-dlbackend` (40Gi), `immich` ml-cache (20Gi), `project-nomad`
embeddings (2Gi), which is ~112Gi off TrueNAS. Further optional candidates: posthog
redis/kafka/clickhouse (disposable), searxng-redis, perplexica-data.

## radar-ng RWX PVCs

radar-ng's 5 RWX PVCs (`tiles`, `grids`, `state`, `openmeteo-data`, `pmtiles`) use
`truenas-nfs`, not `longhorn`, so there are no per-volume Longhorn share-manager
pods. The data is backup-exempt and rebuildable. `storageClassName` is
**immutable** on a bound PVC, so recreate the PVC to change class:

```bash
kubectl delete pvc tiles grids state openmeteo-data pmtiles -n radar-ng
# ArgoCD recreates on truenas-nfs; data regenerates
```

Prerequisites: the NFS service is up and the `BigTank/k8s/nfs/v` dataset exists.
The `truenas-nfs` class deploys via the infrastructure-appset.

## Open decisions (not yet applied)

1. **Reclaim policy.** OpenShift default class is `Delete`. Core `truenas-nfs` is
   `Retain`. With no backups on OpenShift, consider `Retain` there.
2. **Dataset nesting on OpenShift.** Add `datasetPath` (like core's `k8s/nfs/v`) so
   dynamic volumes nest under `BigTank/k8s` and can be group-snapshotted for DR.
3. **More `local-path`.** Use it for disposable DBs (posthog) if desired.
