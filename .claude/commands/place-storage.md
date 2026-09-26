Decide where the data for `$ARGUMENTS` should live, and how big its PVC should be.

Read `docs/domains/storage/disk-map.md` first. It lists every physical disk, what it
holds, and the placement table this command applies.

## 1. Classify the data

Answer from the app's docs or source, not from its name:

- **Database?** (Postgres, MySQL, SQLite, Redis with persistence) → `longhorn`.
  Use `longhorn-wired-ha` only if the app must survive a node loss. Never NFS.
- **Heavy writer?** (ClickHouse, time-series, tile renderers, anything writing
  GBs per hour) → `longhorn-flash`, the only enterprise drive.
- **Bulk, read-mostly files the app creates?** (photo libraries, downloads,
  archives) → `truenas-nfs`, `ReadWriteMany`. It creates only ~50 files/s, so not
  for constant small-file churn.
- **Existing files already on the NAS?** → a static NFS/SMB PV
  (`infrastructure/storage/csi-driver-nfs/storage-class.yaml`).
- **A cache that rebuilds itself?** → `longhorn`, small, `backup-exempt` with the
  fully-qualified `storage.vanillax.dev/backup-exempt-reason` annotation.
- **Docker/overlay storage or an embedded search engine?** → `longhorn`. They
  don't work reliably on NFS.

## 2. Size it

Request what the app really uses plus headroom (for example 2× current use), not
"big to be safe". Longhorn books the full request on a disk; oversized volumes
fill the backup-clone disk on paper and hang backups. Check real use with
`kubectl -n <ns> exec <pod> -- df -h <mount>`.

A bound PVC cannot shrink. To shrink one that rebuilds itself, **rename** it in
git (for example `photon-data` → `photon-index`): ArgoCD creates the new PVC and
prunes the old one.

## 3. Backups

- `longhorn*` classes: the normal kopiur stub (`.claude/commands/add-backup.md`).
- `truenas-nfs`: the same stub plus a kustomization patch setting
  `copyMethod: Direct` and removing `volumeSnapshotClassName`/`staging`
  (reference: `my-apps/media/immich/kustomization.yaml`). Give the mover no
  `fsGroup`: the NAS maps every client to root, and `fsGroup` would re-chown every
  file on each run.

## 4. Report

Tell the user which class, size and backup mode you chose, and why, in one short
paragraph. If the data does not fit any row, ask instead of guessing.
