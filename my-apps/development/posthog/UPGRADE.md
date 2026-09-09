# PostHog Image Bump Checklist

Upstream ships continuously from `master` with zero self-host support; two past
outages came from config drift, not code. Before bumping the monolith/node/Rust
digests, check all five:

1. **ClickHouse config drift** — diff upstream
   [`docker/clickhouse/config.d/default.xml`](https://github.com/PostHog/posthog/blob/master/docker/clickhouse/config.d/default.xml)
   against `config/clickhouse/config.d/default.xml`. New `named_collections`,
   `remote_servers` clusters, or `CLICKHOUSE_SATELLITE_CLUSTERS` entries must be
   mirrored locally or `migrate_clickhouse` fails.
2. **New sharded tables** — grep new upstream `posthog/clickhouse/migrations/`
   for `sharded_*` tables. Single-node CH needs each one bootstrapped in
   `core/clickhouse-init.yaml` (same failure mode as `sharded_events`).
3. **Newly-required env** — grep upstream `docker-compose.base.yml` + `.env.services`
   for env vars web/worker/plugins now require; add to `posthog-env.env`.
4. **Server entrypoint** — check `bin/docker-server-unit` still honors
   `NGINX_UNIT_APP_PROCESSES` / whether `USE_GRANIAN` became the default.
5. **Replay retention compatibility** — review the new image's
   `TeamSerializer._verify_update_session_recording_retention_period` against
   `scripts/patch-replay-retention.py`. Its method hash fails the migration
   hook before a changed validator reaches web. Remove the patch when upstream
   accepts the unlicensed self-hosted 30-day option; otherwise update the
   reviewed fixture/hash and run
   `python3 -m unittest discover -s my-apps/development/posthog/tests -v`
   from the repository root. Preserve cloud and existing entitlement checks.

Rules: bump `posthog/posthog` and `posthog/posthog-node` digests **in lockstep**
(migrate job must match web/worker). Data-layer images (postgres, valkey,
redpanda, clickhouse) only move when upstream's compose pins move. Gate =
`run_async_migrations --check` in the migrate hook; a failed check fails the
sync before app pods roll.


## PostgreSQL security exception (September 2026)

The live inspection found PostgreSQL 15.12 vulnerable to
[CVE-2026-14669](https://www.postgresql.org/support/security/CVE-2026-14669/).
Upstream Compose still pins 15.12. The repair uses the fixed **15.19-alpine**
image, pinned by digest, as a narrow same-major security exception to the
Compose-pin rule above. Application images, schema hooks and preload settings
remain compatible with the existing deployment.

Before merge, confirm a recent successful PostgreSQL Kopiur snapshot. Argo uses
Recreate, so expect a brief database interruption. After rollout, verify
`SHOW server_version`, `SELECT count(*) FROM pg_stat_statements`, login and a
representative dashboard/feature-flag operation. The corrected Service labels
must also produce a successful PostgreSQL scrape.

A local isolated 15.12 data directory reopened on 15.19 with 1,000 fixture rows,
an identical ordered content checksum and a working pg_stat_statements
extension. This validates the image transition, not restoration of production
identity data. A fresh isolated restore remains a follow-up. On startup failure,
preserve the PVC and inspect logs; do not delete or initialize over it. A Git
revert can restore the previous same-major image but reintroduces the security
exposure. Never switch PostgreSQL major versions against this data directory.
