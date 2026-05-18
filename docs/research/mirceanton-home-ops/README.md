# Research: mirceanton/home-ops — backup & storage study

Author: research (study mode)
Date: 2026-05-18
Source: `github.com/mirceanton/home-ops` @ main (analyzed from an uploaded
snapshot) + two of the author's videos:
- *"How I Back Up My Kubernetes Cluster"* (VolSync walkthrough)
- *"From 3 to 1: Why I 'Downgraded' My Homelab"* (storage rationale)

## Scope and rules of this study

- **Study mode.** This documents *his* design end-to-end so we fully
  understand it. It is an external reference only.
- **No compare/contrast yet.** Nothing here judges or maps onto
  `talos-argocd-proxmox`. That comparison is a deliberate later step.
- **Grounded.** Every claim is tied to a real file path in his repo or a
  transcript line, not inferred.

## Documents

| File | Covers |
|---|---|
| `01-backup-restore-end-to-end.md` | The complete backup *and* restore data flow: component, schedule, mover, secrets, jitter, both restore paths, manual tasks |
| `02-openebs-zfs-storage.md` | The storage layer the backup system sits on: why he left Ceph, OpenEBS ZFS-LocalPV, the two pools, snapshot class, scrub, Talos enablement |

## Open questions to resolve later (tracked, not answered here)

- The ZFS pools (`data-pool`, `cache-pool`) are referenced by StorageClasses
  but **created out-of-band on the Talos host** — confirm where/how he
  documents pool creation (not in Git in this snapshot).
- Component default `VOLSYNC_CACHE_SNAPSHOTCLASS:=openebs-zfs` vs. the
  existence of a dedicated `openebs-zfs-cache` StorageClass — the cache
  PVC defaults to the *data* pool, not the cache pool. Intentional?
