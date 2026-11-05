# PostHog image bump checklist

Upstream ships continuously from `master` with zero self-host support. Two past
outages came from config drift, not code. Before bumping the monolith, node, and Rust
digests, check all six:

1. **ClickHouse config drift.** Diff upstream
   [`docker/clickhouse/config.d/default.xml`](https://github.com/PostHog/posthog/blob/master/docker/clickhouse/config.d/default.xml)
   against `config/clickhouse/config.d/default.xml`. New `named_collections`,
   `remote_servers` clusters, or `CLICKHOUSE_SATELLITE_CLUSTERS` entries.
   Mirror them locally or `migrate_clickhouse` fails.
2. **New sharded tables.** Grep new upstream `posthog/clickhouse/migrations/`
   for `sharded_*` tables. Single-node ClickHouse needs each one bootstrapped in
   `core/clickhouse-init.yaml`. The failure mode matches `sharded_events`.
3. **Newly required env.** Grep upstream `docker-compose.base.yml` + `.env.services`
   for env vars that web, worker, and plugins now require. Add them to `posthog-env.env`.
4. **Server entrypoint.** Check that `bin/docker-server-unit` still honors
   `NGINX_UNIT_APP_PROCESSES`, and whether `USE_GRANIAN` became the default.
5. **Replay retention compatibility.** Review the new image's
   `TeamSerializer._verify_update_session_recording_retention_period` against
   `scripts/patch-replay-retention.py`. Its method hash fails the migration
   hook before a changed validator reaches web. Remove the patch when upstream
   accepts the unlicensed self-hosted 30-day option; otherwise update the
   reviewed fixture/hash and run
   `python3 -m unittest discover -s my-apps/development-infra/posthog/tests -v`
   from the repository root. Preserve cloud and existing entitlement checks.
6. **Migration 0353 compatibility.** Review
   `0353_flag_evaluations_person_columns.py` against
   `scripts/patch-flag-evaluations-migration.py`. Its AST hash guards upstream changes.
   The patch separates ADD and MODIFY statements because the legacy analyzer
   rejects both operations on a new column. Preserve table placement and Kafka/MV
   recreation order. Run the PostHog tests above after updating the fixture and hash.

Rules:

- Bump `posthog/posthog` and `ghcr.io/posthog/posthog-node` digests **in lockstep**. The migrate job must match web and worker.
- Bump `ghcr.io/posthog/posthog/sqlx-migrate` in the same PR when upstream adds files under `rust/cyclotron-node-migrations/`.
- Move data-layer images (postgres, valkey, redpanda, clickhouse) only when upstream's compose pins move.
- The gate is `run_async_migrations --check` in the migrate hook. A failed check fails the sync before app pods roll.
