# Immich - Photo Management

Self-hosted photo/video management running on Kubernetes with CloudNativePG.

## Architecture

```
immich-server (v2.5.5)     -> Postgres (CNPG) -> Longhorn PVC (20Gi)
                            -> Valkey (Redis)
                            -> ML service
immich-machine-learning     -> ML cache PVC (10Gi Longhorn)
Both pods                   -> library PVC (50Gi Longhorn) - thumbnails/previews
                            -> NFS photos PVC (read-only)  - original photos
```

## External Library (NAS Photos)

Photos are stored on TrueNAS NFS and indexed by Immich **without duplication**.
Originals stay on NFS read-only; only thumbnails and ML embeddings are stored locally.

- **NFS server**: `192.168.10.133`
- **NFS path**: `/mnt/BigTank/photos/All`
- **Container mount**: `/mnt/photos` (read-only on both server and ML pods)

### Storage breakdown

| Data | Location | Size |
|------|----------|------|
| Original photos/videos | TrueNAS NFS (read-only) | ~1.27 TiB |
| Thumbnails + previews | `library` PVC (Longhorn) | 50Gi |
| ML models (CLIP, face) | `immich-ml-cache` PVC (Longhorn) | 10Gi |
| DB (metadata, embeddings) | Postgres PVC (Longhorn) | 20Gi |

### Setup after deploy

1. Go to **Administration > External Libraries > Create Library**
2. Add import path: `/mnt/photos`
3. Set periodic scan schedule (inotify doesn't work over NFS)
4. Click **Scan** - first run takes hours/days for ML processing

### Gotchas

- **No file watching over NFS** - use periodic scan (cron) to pick up new photos
- **Read-only mount** - edits (rotate, delete) in Immich UI won't touch originals on NAS
- **Moving files on NAS breaks associations** - Immich tracks by path, not content hash
- **First ML scan is heavy** - face detection + CLIP embeddings for all photos takes time

## Database

CloudNativePG (CNPG) manages the database at `infrastructure/database/cloudnative-pg/immich/`.

- Image: `ghcr.io/tensorchord/cloudnative-vectorchord:17.2-0.5.3` (Postgres 17 + VectorChord)
- Extensions: vchord (CASCADE installs pgvector), vector, earthdistance (CASCADE installs cube)
- Service: `immich-database-rw.cloudnative-pg.svc.cluster.local:5432`
- Credentials: ExternalSecret from 1Password (`immich-db-credentials` in immich ns, `immich-app-secret` in cnpg ns)
- S3 backups via Barman to RustFS (`192.168.10.133:30293`)
- Daily scheduled backup at 2am

### Why CNPG over CrunchyData PGO

PGO uses Patroni for HA which is overkill for single-replica homelab. Patroni's DCS (leader election)
gets corrupted when pods are hard-killed, causing unrecoverable standby loops. CNPG is simpler —
no Patroni, no leader election, just a postgres instance with backup management.

## Networking

- **HTTPRoute**: `photos.vanillax.me` via `gateway-internal` (HTTPS)
- **Cilium policy**: NFS traffic to TrueNAS (port 2049) is allowed in `block-lan-access.yaml`

## PVCs

| PVC | Size | StorageClass | Backup |
|-----|------|--------------|--------|
| `library` | 50Gi | longhorn | Enable after stable |
| `immich-ml-cache` | 10Gi | longhorn | No (re-downloadable) |
| `nfs-photos` | 2Ti | `nfs-immich-photos` (CSI, read-only) | N/A (source of truth) |

## NFS StorageClass

The `nfs-immich-photos` StorageClass is defined in `infrastructure/storage/csi-driver-nfs/storage-class.yaml`.
It uses `nfs.csi.k8s.io` provisioner with `ro` mount option pointing to `192.168.10.133:/mnt/BigTank/photos/All`.
