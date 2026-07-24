# PostHog on Kubernetes — Agent Guide

This directory is a **working, self-hosted PostHog on Kubernetes** (product
analytics, session replay, feature flags, LLM analytics) built from plain
Deployments + Kustomize. Upstream does not support self-hosting and ships the
only reference as a single-box docker-compose; these manifests are the
Kubernetes translation. Human walkthrough: `docs/posthog-self-host-k8s.md`.
Upgrade procedure: `UPGRADE.md` (this directory).

## File map

| Path | What it is |
|---|---|
| `posthog-env.env` | Shared env → hash-suffixed ConfigMap; any edit rolls every consumer |
| `externalsecret.yaml` | All secrets (SECRET_KEY, ENCRYPTION_SALT_KEYS, DB, S3) from 1Password |
| `httproute.yaml` | Path routing: which URL prefix hits which service (SDK ingest surface) |
| `data-layer/` | postgres, valkey, redpanda, single-node clickhouse (Recreate, RWO PVCs) |
| `config/clickhouse/` | The single-node ClickHouse config that makes upstream migrations pass |
| `core/clickhouse-init.yaml` | Bootstraps `sharded_events` + migration tables before migrate |
| `core/jobs.yaml` | kafka-init (topics) + posthog-migrate (Django → CH → async `--check` gate) |
| `core/*.yaml` | App tier: web, worker, plugin-server modes, rust capture/flags services |
| `kopiur/postgres-data.yaml` | Backup of the identity layer (see DR below) |

## Invariants — do not break these

1. **`posthog/posthog` and `posthog/posthog-node` digests move in lockstep.**
   The migrate Job runs the monolith image; web/worker/plugin-server must match.
2. **Before any monolith bump, run `UPGRADE.md`.** Both historical outages here
   were upstream config drift, not code: a missing `named_collections` entry,
   and a never-bootstrapped `sharded_*` table. The checklist catches both.
3. **`config.d/default.xml` must mirror upstream's named_collections and define
   all nine cluster names** (`posthog`, `posthog_single_shard`,
   `posthog_migrations`, `posthog_writable`, `posthog_primary_replica`,
   `ai_events`, `aux`, `ops`, `sessions`) — all pointing at the one node.
   `migrate_clickhouse` hard-fails on any missing name.
4. **Sync-wave order is load-bearing**: namespace/secrets (-1) → data layer (0)
   → kafka-init + clickhouse-init (1) → migrate (2) → apps (3). The
   `run_async_migrations --check` gate fails the deploy before app pods roll —
   never remove it.
5. **Worker concurrency stays capped** (`WEB_CONCURRENCY=4` +
   `CELERY_MAX_TASKS_PER_CHILD`/`CELERY_MAX_MEMORY_PER_CHILD`). Unset, celery
   forks one child per core with no recycling and leaks to tens of GiB.
6. **Data layer uses `strategy: Recreate`** (RWO PVCs; RollingUpdate deadlocks)
   and only moves versions when upstream's `docker-compose.base.yml` pins move.
7. **Renovate**: all PostHog images arrive as ONE grouped weekend PR
   (`posthog images`), never automerged — review it against `UPGRADE.md`.

## DR model (why only Postgres is backed up)

Postgres holds the identity layer — project API keys (`Team.api_token`, the
`phc_` key SDKs embed), personal API keys, users, dashboards, flag/cohort
definitions. It is ~165 MB and kopiur-backed with restore-before-bind
(`kopiur/postgres-data.yaml` + the PVC `dataSourceRef`). ClickHouse/Kafka/Redis
are intentionally exempt: event history rebuilds empty from migrations. Net: a
cluster rebuild keeps every API key and dashboard, restores in seconds, and
only analytics history restarts. `SECRET_KEY`/`ENCRYPTION_SALT_KEYS` must live
in an external secret store or encrypted Postgres fields are unreadable after
restore.

## Porting this elsewhere

Change: hostnames in `httproute.yaml` + `posthog-env.env` (SITE_URL,
CSRF/ALLOWED_HOSTS, TRUSTED_PROXIES), the S3 endpoint/bucket (any
S3-compatible store; `OBJECT_STORAGE_*`, `SESSION_RECORDING_V2_S3_*`,
`AI_S3_*`), the secrets source (any ExternalSecret backend or a plain Secret
with the same keys), and the storageClassName. Keep: everything under
`config/clickhouse/`, the init/migrate Jobs, the wave order, and the env
baseline. Full walkthrough with expected results: `docs/posthog-self-host-k8s.md`.
