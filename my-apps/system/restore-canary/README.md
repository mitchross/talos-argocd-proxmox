# restore-canary

Continuous proof that the **kopiur** restore-before-bind path still works: a
known sentinel file is backed up by the `SnapshotPolicy`/`SnapshotSchedule`, the
canary PVC is deleted, Git/Argo recreate it with its `dataSourceRef` → `Restore`,
the kopiur populator rehydrates it, and the sentinel is verified byte-for-byte.

- **Drill**: delete only the `restore-canary-data` PVC and let Argo recreate it;
  the `Restore` populator restores from the latest snapshot. (The old
  `scripts/restore-canary-drill.sh` was removed 2026-06-27.)
- **Full documentation**: `docs/disaster-recovery.md` (what it proves, what it
  does not, bootstrap procedure, failure interpretation, cleanup).
- **Hard rule**: destructive actions are scoped to namespace `restore-canary`
  and PVC `restore-canary-data` only. Nothing here touches production PVCs.
