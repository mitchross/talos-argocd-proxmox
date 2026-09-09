# Immich PostgreSQL 17 security patch

**Purpose:** patch the PostgreSQL server while retaining the existing vector extensions and database. **Status:** Git-declared repair; rollout and production acceptance remain separate. The database stays PostgreSQL 17, with `vchord` 0.4.3 and `vector` 0.8.1. This changes neither the Immich application image nor its schema.

PostgreSQL versions before 17.11 are affected by [CVE-2026-14669](https://www.postgresql.org/support/security/CVE-2026-14669/). The previously pinned Immich image contains PostgreSQL 17.6. Moving to an image with a newer VectorChord would combine two upgrades unnecessarily.

## How the container starts

The [Deployment](deployment.yaml) uses three ordered steps:

1. An init container from the pinned official `postgres:17.11-bookworm` image copies its stock extension SQL/control files into a bounded, ephemeral directory.
2. An init container from the previously pinned Immich image copies only the existing VectorChord/pgvector SQL/control files and two shared libraries into that directory.
3. The PostgreSQL 17.11 container starts with those files mounted read-only. Other server libraries and built-in extension binaries come from the patched official image.

Both images use Debian 12 and PostgreSQL 17. The donor does **not** start PostgreSQL, receive database credentials, or mount the database PVC. Vulnerability scanners can still report its old PostgreSQL package because the donor image contains it; the running database executable is from the patched image. Treat this as a compatibility bridge until an upstream image supplies a patched server with the required extension versions.

The two init containers run as UID/GID 999, without capabilities, with read-only root filesystems and a 128 MiB memory limit. The shared staging volume is limited to 256 MiB and is rebuilt on each new Pod. No packages are downloaded at startup. The [staging script](../scripts/stage-postgres-extensions.sh) and [PostgreSQL config](postgresql.conf) are hash-suffixed ConfigMaps, so edits trigger a new Pod template.

The config preserves the previous Immich SSD settings, including preloading `vchord.so`, 512 MiB shared buffers, WAL compression and the existing `PGDATA/postgresql.override.conf` include. PGDATA, user, secret, checksums, service, PVC and hourly kopiur policy remain the same.

## Before rollout

- Verify a recent successful `immich-postgres-data` kopiur snapshot and a healthy attached volume. Restore-before-bind does not replace an existing Bound PVC during this update.
- Confirm the existing database uses PostgreSQL 17 and the expected extensions. A different major version or extension set requires a separate compatibility review.
- Schedule a short Immich database outage: the single-replica Deployment uses `Recreate` for its RWO PVC. No parallel database Pod or dump/restore is required for this minor update.

```sh
kubectl -n immich exec deploy/immich-postgres -c postgres -- sh -c \
  'psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SHOW server_version; SELECT extname, extversion FROM pg_extension ORDER BY extname;"'
kubectl -n immich get snapshots.kopiur.home-operations.com
kubectl -n immich get pvc immich-postgres-data
```

## Reproduce the compatibility check without the cluster

Requires Python with PyYAML and a local Docker daemon. The script reads both image pins from the Deployment, starts containers with no published ports, and uses only generated data. The initial run may pull those images. It removes its own containers and scratch directories afterward.

```sh
python3 my-apps/media/immich/tests/check_postgres_upgrade.py
```

The test initializes the old image with all eight extension types observed in production, inserts 1,000 synthetic vectors and creates a real VectorChord index. It then cleanly stops PostgreSQL, reopens the same data directory under the patched image, checks unchanged extension versions and indexed search results, performs a new write and reindex, and checks fresh initialization separately. It runs the database as UID/GID 999 with all capabilities dropped. Expected final output starts with `PASS`.

This validates extension loading and representative index compatibility; it is not a restore of the production photo catalog or a substitute for application acceptance.

## After rollout

```sh
kubectl -n immich rollout status deployment/immich-postgres --timeout=5m
kubectl -n immich exec deploy/immich-postgres -c postgres -- sh -c \
  'psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SHOW server_version; SHOW shared_preload_libraries; SHOW data_checksums; SELECT extname, extversion FROM pg_extension ORDER BY extname;"'
kubectl -n immich logs deploy/immich-postgres -c postgres --tail=80
```

Expected: PostgreSQL 17.11 or a later reviewed 17.x security patch, preload `vchord.so`, checksums `on`, and unchanged `vchord` 0.4.3/`vector` 0.8.1. Open Immich, load the timeline and thumbnails, run a semantic search and open a face search. Check for extension loading, index or collation errors. Verify the next hourly backup succeeds.

The new exporter connects to `127.0.0.1` with the existing credentials. Its dedicated metrics Service exposes port 9187; its ServiceMonitor selects **Service metadata labels**. Check Prometheus has the `immich-postgres-metrics` target with `up=1` and `pg_up=1`. The exporter has no readiness probe, so a scrape error cannot independently mark an otherwise running database Pod unready; exporter process crashes can still affect Pod readiness. Its VPA policy is explicitly `Off`.

## Failure and rollback

If extension staging, startup, SQL checks or searches fail, preserve the existing PVC and inspect both init-container logs and the PostgreSQL logs. Do not delete the PVC, initialize a replacement database or run `ALTER EXTENSION UPDATE` to bypass an error.

Use the PR workflow to revert the database image, staging/config mounts and init containers together to the prior pinned Immich image. This restores the old startup arrangement and reintroduces the security vulnerability, so use it only as a temporary recovery measure. The minor update does not intentionally change extension versions or migrate the catalog, but rollback acceptance still requires checking the application and backup. If data recovery is required, follow the canonical [kopiur recovery procedure](../../../../docs/disaster-recovery.md) with a verified snapshot rather than overwriting the current volume.
