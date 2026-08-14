Create a new database for `$ARGUMENTS`.

## Default path: plain Postgres + kopiur (since 2026-07-09)

New databases are **ordinary Postgres Deployments inside the owning app's
directory**, backed up by kopiur like every other PVC. Zero-touch DR
(restore-before-bind), no operator, no overlay dance. Reference
implementation: `my-apps/development/gitea/postgres/`. Full pattern +
rationale: `docs/domains/cnpg/plain-postgres-migration.md`.

### Steps

1. Copy `my-apps/development/gitea/postgres/` (deployment/service/pvc) into
   `my-apps/<category>/<app>/postgres/` and rename `gitea` → `<app>`
   throughout.
2. Copy the kopiur stub to `kopiur/<app>-postgres-data.yaml`: mover stays
   `999:999` (official postgres image uid), retention stays the **hourly
   tier**, and the cron minute must be **distinct across ALL schedules**
   (`grep -rn "cron:" my-apps --include=*.yaml`).
3. Declare the database in the Deployment env: `POSTGRES_DB` /
   `POSTGRES_USER` / `POSTGRES_PASSWORD` (from an ExternalSecret) — created
   on first empty-volume boot; restored data always wins afterward. The image
   does not reconcile users or passwords on an existing/restored data dir.
4. Pin the image to a `postgres:<MAJOR.MINOR>` tag. Renovate handles
   patches/minors; **never auto-merge a MAJOR** (data dirs are not
   major-compatible — majors need a manual dump/restore).
5. List everything in the app `kustomization.yaml` (+ the
   `../../common/kopiur-backup` component if not already present) and ensure
   the namespace carries the `kopiur.home-operations.com/repo: cluster-kopia`
   label.
6. Keep a generous `startupProbe` using `pg_isready` (the Gitea reference
   allows about five minutes) so liveness does not kill Postgres during WAL
   replay after a restore.
7. After deploy, verify the first backup before trusting DR:
   `kubectl -n <app> get snapshot` → `Succeeded` with non-zero files.

### Critical rules

- The app's PVC restore-point is the last snapshot (~1h with the hourly
  tier) — restores land on the last snapshot, not a point in time.
- The password stored inside a restored database is restored state. Never
  rotate only the 1Password item: connect with the current credential, run
  `ALTER ROLE ... PASSWORD ...`, then update 1Password and restart consumers
  as one controlled rotation. Keep the old credential until the app verifies.
- Special images where needed (e.g. immich requires
  `ghcr.io/immich-app/postgres` with VectorChord).

## What about PITR / CNPG?

CNPG was fully retired 2026-08-13 (operator, Barman plugin, and recovery
script deleted; history in `docs/domains/cnpg/plain-postgres-migration.md`).
Every database uses the plain pattern above. If a future workload genuinely
needs point-in-time recovery, that is a new architecture decision — raise it
explicitly rather than resurrecting the old manifests.

## Reference

- **Plain Postgres reference:** `my-apps/development/gitea/postgres/`
- **Migration/pattern doc:** [`docs/domains/cnpg/plain-postgres-migration.md`](../../docs/domains/cnpg/plain-postgres-migration.md)
- **Operator guide (plain English):** [`docs/domains/cnpg/run-postgres-plain-english.md`](../../docs/domains/cnpg/run-postgres-plain-english.md)
- Two-database example (initdb script + schema-hook sync waves): `my-apps/development/temporal/postgres/`
