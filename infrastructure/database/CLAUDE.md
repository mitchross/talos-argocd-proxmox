# Database Guidelines

**Databases do NOT live in this directory.** Every database is a plain
Postgres Deployment inside the owning app's directory, backed up by kopiur:

- Pattern + operator guide:
  [`docs/domains/cnpg/run-postgres-plain-english.md`](../../docs/domains/cnpg/run-postgres-plain-english.md)
- Reference implementation: `my-apps/development/gitea/postgres/`
- Two-database example (initdb script + schema-hook sync waves):
  `my-apps/development/temporal/postgres/`
- Create one with `/project:new-database <app>`

CNPG (CloudNativePG) was **fully retired 2026-08-13** — operator, Barman
plugin, recovery script, and the AppSet manual-sync gates were all deleted
(history: [`docs/domains/cnpg/plain-postgres-migration.md`](../../docs/domains/cnpg/plain-postgres-migration.md)).
Do not resurrect it. The old Barman buckets age out via
`infrastructure/storage/rustfs-lifecycle/`.

## What IS here

`infrastructure/database/*/*` is discovered by the Database AppSet (Wave 4,
fully automated: auto-sync + prune, no self-heal):

| Directory | Purpose |
|---|---|
| `redis/` | Shared Redis instance (backup-exempt disposable data — do not add kopiur CRs) |

Use this directory only for shared database *support* services consumed by
multiple apps. A database owned by one app belongs in that app's directory.
