# Storage Model: RWO vs RWX, truenas-csi, and Capacity Sizing

Storage-class decisions and capacity sizing across the core repo
(`talos-argocd-proxmox`, production Talos) and the multicluster fork
(`talos-argocd-proxmox-multicluster-test`, OpenShift/SNO).

## TL;DR

- **Static SMB/NFS shares stay on the plain CSI drivers** (`csi-driver-nfs`,
  `csi-driver-smb`). They hold real data you browse/edit by hand; keep them
  human-readable and decoupled from the TrueNAS API. `truenas-csi`
  (`csi.truenas.io`) is for **dynamic provisioning only**, and v1.0.4 does
  **iSCSI + NFS only — no SMB**.
- **Talos:** use **Longhorn for RWO** (block). Do **not** add truenas-csi iSCSI on
  Talos — it would need the `siderolabs/iscsi-tools` system extension + a Cilium
  TCP 3260 egress rule, and Longhorn does block RWO better here (node-local
  replication). Use truenas-csi **NFS (`truenas-nfs`) for RWX** only.
- **OpenShift/SNO:** no Longhorn. RWO/DBs → `vanillax-local-rwo`
  (`csi.truenas.io` **iSCSI**, block, safe for databases). RWX →
  `truenas-nfs-csi` (NFS). Regenerable caches → `local-path` (node-local).

## How to decide RWO vs RWX

> **Count the pods that mount the same `claimName`. One → RWO. Two+ → RWX.**

Signals, in order of reliability:

1. **Same `claimName` in 2+ different pods/Deployments** → RWX. (Grep the app for
   the claim name.) Example: radar-ng `tiles`/`grids`/`state` are mounted by
   `tile-server` (3 replicas) **and** `temporal-worker` (3 replicas) = 6 pods.
2. **Workload kind:** `Deployment replicas:1` or one-off `Job` → RWO.
   `StatefulSet` → RWO (each replica gets its *own* volume via
   `volumeClaimTemplates`; StatefulSet ≠ RWX). `Deployment replicas:2+` sharing one
   PVC → RWX.
3. **Data type:** databases (Postgres/MySQL/ClickHouse/Redis/SQLite) → **always
   RWO**, never NFS. Shared media libraries touched by multiple apps → RWX.

Default to **RWO**. Only choose RWX when you can name the second pod that needs the
same files. For a homelab ~99% of apps are RWO; RWX is the media-stack exception.

## Per-cluster storage class map

| Need | Talos (core) | OpenShift (fork) |
|------|--------------|------------------|
| RWO / block / DBs | `longhorn` (or portable `vanillax-local-rwo` → Longhorn) | `vanillax-local-rwo` = `csi.truenas.io` iSCSI |
| RWX / shared | `truenas-nfs` (`csi.truenas.io` NFS) | `truenas-nfs-csi` (`csi.truenas.io` NFS) |
| Static media/models (browseable) | `csi-driver-nfs` / `csi-driver-smb` | `csi-driver-nfs` / `csi-driver-smb` |
| Regenerable node-local cache | (Longhorn) | `local-path` |

`csi.truenas.io` config style (both clusters): a `truenas-csi-config` ConfigMap
holds connection + `defaultPool: BigTank` + `nfsServer`/`iscsiPortal`;
StorageClasses add `pool` + `datasetPath` as parameters (core's `truenas-nfs` nests
under `BigTank/k8s/nfs/v`, `reclaimPolicy: Retain`).

## TrueNAS layout (192.168.10.133)

Pools: `BigTank` (the CSI `defaultPool`), `ai-pool`, `Backup10T`, `backuptank`.

- Kubernetes data lives under **`BigTank/k8s`** (children: comfyui, frigate, iscsi,
  jellyfin-media, …). Path: `BigTank/k8s` (Sync DISABLED, ZSTD).
- **Important:** some static model shares live on **`ai-pool`, not BigTank** — e.g.
  comfyui/swarmui models both mount the same export
  `192.168.10.133:/mnt/ai-pool/comfyui`. These do **not** count against BigTank.

### Static vs dynamic (and the GUID question)

- **Dynamic** volumes are named after the PV UID: zvol/dataset
  `BigTank/pvc-<uuid>`. Opaque (not for hand-editing). The PV's `volumeHandle`
  (in etcd) links the GUID to the app — not the name.
- `reclaimPolicy: Delete` destroys the TrueNAS dataset when the PVC is deleted.
  `Retain` keeps it but the PV goes `Released` and needs manual `claimRef` clearing
  to rebind.
- **Restore is a separate layer from the CSI driver.** On Talos, kopiur restores
  *contents* into a fresh GUID volume, keyed by PVC name+namespace. **OpenShift has
  no kopiur** → dynamic volumes there have **no backup**. For OpenShift DR, use
  **TrueNAS native ZFS snapshot tasks** on a parent dataset (nest dynamic volumes
  under e.g. `BigTank/k8s/csi` so one recursive snapshot protects all `pvc-*`
  regardless of GUID).

## Capacity sizing

These are **requests**, not usage (ZFS is thin-provisioned).

| Bucket | Capacity | Notes |
|--------|----------|-------|
| RWO block (full app catalog) | ~1.11 TiB | On **Talos this is Longhorn**, not BigTank. Only counts against BigTank on **OpenShift** (iSCSI). |
| RWX static shares | ~4.48 TiB | Already exist on the box; some on **ai-pool** (comfyui/swarmui/llama models), not BigTank. |
| RWX dynamic (radar-ng → NFS) | ~205 GiB | `truenas-nfs` on Talos / `truenas-nfs-csi` on OpenShift. |
| Grand total of requests | ~5.75 TiB | Excludes the 250Gi swarmui/comfyui double-count. |

**New provisioning that actually hits BigTank:**
- OpenShift: ~1.2 TiB (RWO iSCSI + radar-ng NFS, with ~112Gi of caches on
  `local-path`).
- Talos: ~205 GiB (radar-ng NFS; everything else is Longhorn).

Comfortably under BigTank's 8.54 TiB free. Static ai-pool shares do not count
against BigTank; the swarmui/comfyui double-count is excluded.

### `local-path` candidates (OpenShift)

Regenerable, node-local, no TrueNAS dependency: `gitea-actions` docker-cache
(50Gi), `swarmui-dlbackend` (40Gi), `immich` ml-cache (20Gi), `project-nomad`
embeddings (2Gi) = ~112Gi off TrueNAS. Further optional candidates: posthog
redis/kafka/clickhouse (disposable), searxng-redis, perplexica-data.

## radar-ng RWX PVCs

radar-ng's 5 RWX PVCs (`tiles`, `grids`, `state`, `openmeteo-data`, `pmtiles`) use
`truenas-nfs`, not `longhorn` — no per-volume Longhorn share-manager pods. Data is
backup-exempt/rebuildable. Because `storageClassName` is **immutable** on a bound
PVC, change class by recreating:

```bash
kubectl delete pvc tiles grids state openmeteo-data pmtiles -n radar-ng
# ArgoCD recreates on truenas-nfs; data regenerates
```

Prereqs: NFS service up + `BigTank/k8s/nfs/v` dataset exists (the `truenas-nfs`
class deploys via the infrastructure-appset).

## Open decisions (not yet applied)

1. **Reclaim policy:** OpenShift default class is `Delete`; core `truenas-nfs` is
   `Retain`. With no backups on OpenShift, consider `Retain` there.
2. **Dataset nesting on OpenShift:** add `datasetPath` (like core's `k8s/nfs/v`) so
   dynamic volumes nest under `BigTank/k8s` and can be group-snapshotted for DR.
3. **More `local-path`** for disposable DBs (posthog) if desired.
