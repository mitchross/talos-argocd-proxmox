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
