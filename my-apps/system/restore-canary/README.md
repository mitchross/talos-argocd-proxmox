# restore-canary

Continuous backup health plus an isolated target for proving that the
**kopiur** restore-before-bind path still works. A daily snapshot and weekly
quick verification run automatically. The destructive, byte-for-byte restore
drill is intentionally operator-triggered; it is not honest to call the daily
snapshot itself continuous restore proof.

- **Drill**: write and hash a sentinel, force/wait for a successful snapshot,
  delete only the `restore-canary-data` PVC, let Argo recreate it, then verify
  the restored sentinel byte-for-byte. Record the result using the namespace
  annotations documented in the DR runbook. The old VolSync-specific helper
  was removed; do not reuse it for kopiur.
- **Full documentation**: `docs/disaster-recovery.md` (what it proves, what it
  does not, bootstrap procedure, failure interpretation, cleanup).
- **Hard rule**: destructive actions are scoped to namespace `restore-canary`
  and PVC `restore-canary-data` only. Nothing here touches production PVCs.
