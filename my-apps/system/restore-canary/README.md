# restore-canary

Continuous backup health plus an isolated target for proving that the
**kopiur** restore-before-bind path still works. A daily snapshot and weekly
quick verification run automatically. The destructive, byte-for-byte restore
drill is intentionally operator-triggered; it is not honest to call the daily
snapshot itself continuous restore proof.

- **Drill**: write and hash a sentinel, force/wait for a successful snapshot,
  delete the `restore-canary-data` PVC **and the `restore-canary-data-restore`
  Restore CR**, let Argo recreate both, then verify the restored sentinel
  byte-for-byte. Record the result using the namespace annotations documented in
  the DR runbook. The old VolSync-specific helper was removed; do not reuse it
  for kopiur.
- **Deleting the Restore CR is mandatory, not optional.** A `Restore` resolves
  its source **once, at admission, and never re-resolves** — `offset: 0` means
  "latest as of admission", not "latest now". Delete only the PVC and the
  populator re-hydrates from whatever snapshot the Restore pinned the first time
  it ran, so the drill replays a frozen snapshot and passes no matter how
  broken (or healthy) backups actually are. This silently invalidated every
  drill between 2026-08-03 and 2026-08-13, which restored a 2026-06-10 sentinel
  while reporting `RestoreSucceeded`.
- **Gate the verdict on the pin, not just the bytes.** Before trusting a PASS,
  confirm the Restore re-resolved to the snapshot you just took:
  `kubectl -n restore-canary get restore restore-canary-data-restore \
  -o jsonpath='{.status.resolved.pinnedAt} {.status.resolved.kopiaSnapshotID}'`
  A `pinnedAt` older than the drill snapshot means the result is meaningless.
  A healthy drill goes `Pending -> Restoring -> Bound`; a PVC that binds
  instantly never ran the populator.
- **Full documentation**: `docs/disaster-recovery.md` (what it proves, what it
  does not, bootstrap procedure, failure interpretation, cleanup).
- **Hard rule**: destructive actions are scoped to namespace `restore-canary`
  and PVC `restore-canary-data` only. Nothing here touches production PVCs.
