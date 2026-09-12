# Immich — Self-Hosted Photos

Photo and video library. The originals live on the TrueNAS archive and are
mounted read-only as an Immich **external library** — Immich never writes to
them. It owns only thumbnails, transcodes, ML embeddings and database rows.

## Architecture

```
 User → https://photos.vanillax.me (gateway-internal, LAN only)
       │
       ▼
 immich-server ──────── reads /mnt/photos (read-only NFS, the originals)
       │                writes /library   (thumbnails, previews, transcodes)
       │
       ├── immich-postgres ── plain Postgres Deployment, Longhorn PVC
       ├── immich-valkey ──── cache, ephemeral
       └── immich-machine-learning ── CLIP + face recognition
                                      runs on the Intel iGPU via OpenVINO
```

The server and ML pods run on **different nodes**. ML is pinned to the node
holding the passed-through Intel iGPU; the server stays where the CPU is. They
talk over the ClusterIP Service — ML receives image bytes in the HTTP request
and never touches the media filesystem.

> **Do not mount `library` or `nfs-photos` into the ML pod.** Upstream gives
> machine-learning only `model-cache:/cache`. Adding the RWO `library` PVC back
> would Multi-Attach the moment the two pods land on different nodes.

## Storage

| Data | Where | Backup |
|---|---|---|
| Originals (~1.3 TB) | TrueNAS NFS, read-only static PV | NAS-side ZFS + replication; `backup-exempt` |
| Thumbnails, previews, transcodes | `library` PVC, 150Gi Longhorn | kopiur **daily** 03:37 |
| Database | `immich-postgres-data` PVC, 20Gi Longhorn | kopiur **hourly** :23, CHECKPOINT before-hook |
| ML models | `immich-ml-cache` PVC, 20Gi Longhorn | `backup-exempt` — re-downloads on demand |

Postgres has **two independent backups**. kopiur snapshots the PVC hourly, and
Immich writes its own SQL dump to `/library/backups` at 02:00 — which the daily
`library` backup then ships at 03:37. Keep that ordering: the dump must be
written before the volume that carries it is snapshotted. The snapshot restores
fast but reproduces any corruption it captured; the dump is the escape hatch.

Both PVCs use kopiur restore-before-bind: on recreate they sit `Pending` until
the populator hydrates them, then bind with data. If the repo is unreachable
they stay `Pending` rather than binding empty.

### The NFS mount

Static PV `nfs-immich-photos`, defined in
`infrastructure/storage/csi-driver-nfs/storage-class.yaml`:

- **Server / share:** `192.168.10.133:/mnt/BigTank/photos/All`
- **In-pod path:** `/mnt/photos`, read-only, `nfsvers=4.1 nconnect=16`

It is static rather than dynamic because dynamic NFS CSI provisions a *new*
subdirectory per PVC, and this mounts data that already exists. Use the CSI
driver, never the legacy `nfs:` block — that silently ignores `mountOptions`.

The export maps all clients to `k8-smb-user:nas-private` and is read-only on the
NAS side. Without that mapping the pod's root is squashed to `nobody`, and the
dataset's `2770` mode denies it — which surfaces in the Immich UI as
*"Invalid import path: Lacking read permission for folder"*.

## Database

Plain Postgres Deployment in `postgres/`, pinned image, database declared via
env. No operator, no recovery script, no manual sync gate — recovery is the same
kopiur restore every other PVC gets.

## Adding the external library

Immich does not create one for you.

1. **Administration → External Libraries → Create Library**, import path
   `/mnt/photos`
2. Set exclusion patterns for NAS and sync artifacts: `**/@eaDir/**`,
   `**/*recycle/**`, `**/*snapshot/**`, `**/.stversions/**`, `**/.stfolder/**`
3. **Settings → External Library:** library watching **off**, periodic scan
   **on**. inotify does not work over NFS — polling is the only option.
4. Scan.

Leave the **storage template disabled**. It only reorganises files Immich owns;
it never touches external-library files, and the mount is read-only regardless.

## Gotchas

- **Immich tracks assets by path, not content hash.** Renaming a folder on the
  NAS reads as "all deleted, all new" and loses albums, favourites and face
  assignments. Move within the Immich UI, or accept a full re-scan.
- **Deletes in the UI never reach the NAS.** The mount is read-only. To really
  delete, delete on the NAS and re-scan.
- **An empty `library` volume fails Immich's integrity check** once the database
  holds asset rows — it checks for `.immich` marker files rather than
  re-initialising. The init container seeds them idempotently, which is what
  makes a cold DR restore work. Do not remove it.
- **`immich-server` uses `Recreate`.** It holds the RWO `library` PVC;
  `RollingUpdate` would Multi-Attach deadlock.
- **Deleting the namespace does not delete your photos**, but it does delete the
  thumbnails and the database — albums, tags and faces included.

## Recovery

Originals survive anything short of losing the NAS. `immich-postgres-data` and
`library` restore from kopiur automatically on a rebuild, bringing back albums,
faces and the thumbnail working set. See `docs/disaster-recovery.md`.
