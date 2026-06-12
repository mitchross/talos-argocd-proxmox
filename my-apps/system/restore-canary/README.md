# restore-canary

Continuous proof that the pvc-plumber v4 + VolSync/Kopia restore path still
works: a known sentinel file is backed up, the canary PVC is deleted, Git/Argo
recreate it with its `dataSourceRef`, the VolSync populator restores it, and
the sentinel is verified byte-for-byte.

- **Drill script**: `scripts/restore-canary-drill.sh` (read-only `status` by
  default; `--seed` writes sentinel + first backup; `--live-run` performs the
  destructive delete/restore drill — canary PVC only).
- **Full documentation**: `docs/disaster-recovery.md` (what it proves, what it
  does not, bootstrap procedure, failure interpretation, cleanup).
- **Hard rule**: destructive actions are scoped to namespace `restore-canary`
  and PVC `restore-canary-data` only. Nothing here touches production PVCs.
