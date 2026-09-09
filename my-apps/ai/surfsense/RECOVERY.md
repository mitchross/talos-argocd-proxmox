# Redis incident recovery

The September 9, 2026 live recheck still reports a malformed incremental AOF at
byte 36151654 with a 10659-byte tail. The Deployment's Recreate strategy stops the
old writer before its init container checks or changes files. Healthy and absent
AOFs are left alone. Only that exact checker-reported incident qualifies for
repair; another failure stops init for inspection.

Before `redis-check-aof --fix`, the script exclusively creates
`/data/redis-aof-recovery-20260909/original`, copies **all** AOF files and the
manifest, compares every copy byte-for-byte, records SHA-256 hashes and syncs the
filesystem. It requires 64 MiB free beyond the copy size. No archive is ever
removed or overwritten. Copy, validation and space errors stop startup.

The repair discards **10659 bytes** after the last valid AOF command. That bounds
bytes, not tasks: queued work, acknowledgements or results represented there may
be lost or replayed. PostgreSQL and the knowledge/object store are untouched.
Redis is intentionally backup-exempt. If queue continuity is more important
than resuming service, inspect the retained tail or recover an independently
verified storage snapshot instead; there is no Kopiur Redis backup to restore.

An interrupted repair with an archive already present fails closed if the AOF is
still corrupt. Inspect its hashes and repair log; do not delete the archive to
force a retry. A healthy repaired AOF bypasses recovery on subsequent startups.
Retain the archive until work queues and application results have been reconciled
and an operator deliberately removes it in a later maintenance change.

Acceptance: Redis passes readiness, the API/worker pod becomes 2/2 Ready, and a
small document upload finishes ingestion and becomes searchable. The worker's
readiness now asks **that worker** to respond through the broker; a running
process with a dead broker is not Ready. Broker failures do not trigger a new
liveness restart loop. This control reply proves responsiveness, not successful
completion of every task; retain queue-depth and task-failure monitoring.

Rollback requires stopping Redis before replacing its AOF set from the retained
originals (which reproduces the pre-repair failure). Never copy old AOF files over
a running Redis or blindly replay tasks with non-idempotent external effects.

Upstream behavior: [Redis persistence and AOF recovery](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/).
