# PostHog Self-Hosting: Clean-Room Research Report

> Generated 2026-04-09 from upstream sources only (official docs, deprecated Helm chart v30.46.0, Docker Compose files, Dockerfiles, source code). No influence from existing deployment.

## Executive Summary

PostHog officially **sunsetted K8s/Helm support in May 2023** (security patches ended May 2024). The only supported self-host method is Docker Compose "Hobby". Building K8s-native manifests is an unsupported path -- we're reverse-engineering from the deprecated Helm chart (v30.46.0), Docker Compose files, Dockerfiles, and source code.

The hobby deployment runs **25+ containers** across 3 languages (Python/Django, Node.js, Rust) plus 8 infrastructure services. Minimum requirements: 4 vCPU, 16GB RAM, 30GB+ storage (GitHub issues report problems even at 8GB/2CPU).

---

## 1. Complete Component Map

### A. Infrastructure (Stateful)

| Component | Image | Ports | Volume | Required? |
|-----------|-------|-------|--------|-----------|
| **PostgreSQL** | `postgres:15.12-alpine` | 5432 | `/var/lib/postgresql/data` (20Gi) | Yes |
| **ClickHouse** | `clickhouse/clickhouse-server:25.12.8.9` | 8123(HTTP), 9000(TCP), 9181(Keeper) | `/var/lib/clickhouse` (100Gi+) | Yes |
| **Kafka (Redpanda)** | `redpandadata/redpanda:v25.1.9` | 9092(Kafka), 8081(Schema), 8082(Proxy), 9644(Admin) | `/var/lib/redpanda/data` (20Gi) | Yes |
| **Redis/Valkey** | `redis:7.2-alpine` or `valkey/valkey:8.0-alpine` | 6379 | `/data` (10Gi) | Yes |
| **MinIO (Object Storage)** | `minio/minio:RELEASE.2025-04-22T22-12-26Z` | 19000(API), 19001(Console) | `/data` | Yes (or external S3) |
| **SeaweedFS** | `chrislusf/seaweedfs:4.03` | 8333(S3), 9333(Master) | `/data` | Yes (session recording v2) |
| **ZooKeeper** | `zookeeper:3.7.0` | 2181 | 3 volumes | **No** if using ClickHouse embedded Keeper |
| **Elasticsearch** | `elasticsearch:7.17.28` | 9200 | anonymous | Only if Temporal enabled |
| **Temporal** | `temporalio/auto-setup:1.26.2` | 7233 | none | Optional (batch exports, data warehouse) |

**Key discovery: TWO separate S3-compatible stores are needed** -- MinIO for general object storage (exports, media, source maps, query cache) and SeaweedFS specifically for session recording v2 storage.

### B. Python/Django Services (image: `posthog/posthog:latest`)

| Service | Command | Ports | Purpose |
|---------|---------|-------|---------|
| **web** | `./bin/docker-server` | 8000(app), 8001(metrics) | Django web UI + API. Runs migrations on startup in hobby mode |
| **worker** | `./bin/docker-worker-celery --with-scheduler` | 8001(metrics) | Celery worker (16 queues) + RedBeat scheduler |
| **temporal-django-worker** | `./bin/temporal-django-worker` | 8596 | Temporal workflow worker for batch exports |
| **asyncmigrationscheck** | `python manage.py run_async_migrations --check` | -- | One-shot migration check |

The main Python image is based on **NGINX Unit 1.33.0** with Python 3.12.12, Node.js 24.13.0, Chromium, Playwright, ffmpeg, and GeoLite2-City MMDB embedded. Hobby mode uses **Granian ASGI server** (`USE_GRANIAN=true`, 2 workers) instead of Unit.

### C. Node.js Services (image: `posthog/posthog-node:latest`)

All run `node nodejs/dist/index.js` with different `PLUGIN_SERVER_MODE` values:

| Service | PLUGIN_SERVER_MODE | Purpose |
|---------|-------------------|---------|
| **plugins** | (default/unset) | CDP plugins, webhooks, site apps. Port 6738 |
| **ingestion-general** | `ingestion-v2-combined` | Main event ingestion pipeline |
| **ingestion-sessionreplay** | `recordings-blob-ingestion-v2` | Session recording blob ingestion |
| **recording-api** | `recording-api` | Session recording playback API |
| **ingestion-error-tracking** | `ingestion-errortracking` | Error tracking ingestion |
| **ingestion-logs** | `ingestion-logs` | Log ingestion pipeline |
| **ingestion-traces** | `ingestion-traces` | Trace ingestion pipeline |

The Helm chart also supported these split modes (all disabled by default): `ingestion`, `analytics-ingestion`, `ingestion-overflow`, `async`, `exports`, `jobs`, `scheduler`.

### D. Rust Services (separate images, each a different binary)

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| **capture** | `ghcr.io/posthog/posthog/capture:master` | 3000 | Event capture endpoint (CAPTURE_MODE=events) |
| **replay-capture** | `ghcr.io/posthog/posthog/capture:master` | 3000 | Session replay capture (CAPTURE_MODE=recordings) |
| **feature-flags** | `ghcr.io/posthog/posthog/feature-flags:master` | 3001 | Rust feature flag evaluator. **Requires GeoLite2-City.mmdb** |
| **property-defs-rs** | `ghcr.io/posthog/posthog/property-defs-rs:master` | -- | Property definition service |
| **cyclotron-janitor** | `ghcr.io/posthog/posthog/cyclotron-janitor:master` | -- | Background job cleanup |
| **cymbal** | `ghcr.io/posthog/posthog/cymbal:master` | 3302 | Error tracking symbolication. **Requires GeoLite2-City.mmdb** |
| **livestream** | `ghcr.io/posthog/posthog/livestream:master` | 8080 | Live event streaming WebSocket |
| **capture-logs** | `ghcr.io/posthog/posthog/capture-logs:master` | 4318 | OTEL log/trace ingestion |

---

## 2. Startup Order / Dependency Graph

```
Phase 0 - Infrastructure (parallel):
  PostgreSQL, Redis, ZooKeeper/ClickHouse-Keeper

Phase 1 - Message broker:
  Kafka/Redpanda (needs ZK if external ZK used)
  MinIO / Object Storage
  SeaweedFS
  Elasticsearch (only if Temporal)

Phase 2 - Analytics DB + Init:
  ClickHouse (needs Kafka for Kafka engine tables)
  kafka-init Job (creates topics: events_plugin_ingestion, exceptions_ingestion,
    clickhouse_events_json, session_recording_snapshot_item_events, etc.)
  Temporal (needs PG healthy + ES healthy; 300s start period!)

Phase 3 - Migrations:
  posthog-migrate Job:
    1. Wait for PG + CH ready
    2. python manage.py migrate --noinput (Django/PG)
    3. python manage.py migrate_clickhouse (ClickHouse schema)
    4. python manage.py run_async_migrations (non-blocking)

Phase 4 - Application (after migrations complete):
  web (Django server)
  worker (Celery + RedBeat scheduler)
  plugins (CDP/webhooks)
  ingestion-general (event processing pipeline)
  ingestion-sessionreplay (recording blob ingestion)
  recording-api (recording playback)
  capture + replay-capture (Rust capture endpoints)
  feature-flags (Rust flag evaluator)
  property-defs-rs (after kafka-init completes)
  temporal-django-worker (after Temporal healthy)

Phase 5 - Optional:
  ingestion-error-tracking, ingestion-logs, ingestion-traces
  cymbal (after kafka-init completes)
  cyclotron-janitor
  livestream
```

### Init Container Pattern (from Helm chart)

**wait-for-service-dependencies** (busybox:1.34): TCP checks on ClickHouse, PgBouncer/PG, Redis, Kafka

**wait-for-migrations** (posthog image): Runs `python manage.py migrate --check` + `python manage.py migrate_clickhouse --check`

Used by: web, worker, plugins, decide, temporal-py-worker
NOT used by: events (skips migration checks), capture services (Rust, independent)

---

## 3. Reverse Proxy Routing Map

This is what the Caddy config routes (translate to HTTPRoute rules):

| Path Pattern | Backend | Port | Notes |
|-------------|---------|------|-------|
| `/s`, `/s/*` | replay-capture | 3000 | Session replay capture |
| `/i/v0/ai`, `/i/v0/ai/*` | capture-ai | 3000 | AI capture variant |
| `/e`, `/e/*`, `/i/v0`, `/i/v0/*`, `/batch`, `/batch/*`, `/capture`, `/capture/*` | capture | 3000 | Event capture |
| `/i/v1/logs`, `/i/v1/logs/*`, `/i/v1/traces`, `/i/v1/traces/*` | capture-logs | 4318 | OTEL ingestion |
| `/flags`, `/flags/*` | feature-flags | 3001 | Flag evaluation |
| `/public/webhooks`, `/public/webhooks/*`, `/public/m/*` | plugins | 6738 | CDP webhooks |
| `/livestream`, `/livestream/*` | livestream | 8080 | WebSocket (strip prefix) |
| `/posthog`, `/posthog/*` | objectstorage | 19000 | Presigned URL passthrough |
| Everything else | web | 8000 | Django UI/API |

---

## 4. Complete Environment Variables

### Critical Secrets

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Django crypto key (56-char SHA224) |
| `ENCRYPTION_SALT_KEYS` | Data encryption (32-char hex) |
| `DATABASE_URL` | PostgreSQL connection string |
| `PGPASSWORD` | PostgreSQL password |

### Database Connections

| Variable | Default | Notes |
|----------|---------|-------|
| `DATABASE_URL` | constructed from PG* vars | Full connection string |
| `PGHOST` | `db` | |
| `PGPORT` | `5432` | |
| `PGDATABASE` | `posthog` | |
| `PGUSER` | `posthog` | |
| `PERSONS_DATABASE_URL` | same as DATABASE_URL | Separate in production |
| `BEHAVIORAL_COHORTS_DATABASE_URL` | same | Separate in production |
| `CYCLOTRON_DATABASE_URL` | same | Can point to `cyclotron` DB |
| `USING_PGBOUNCER` | `false` | `true` disables server-side cursors |
| `POSTHOG_POSTGRES_READ_HOST` | -- | Optional read replica |

### ClickHouse

| Variable | Default | Notes |
|----------|---------|-------|
| `CLICKHOUSE_HOST` | `clickhouse` | |
| `CLICKHOUSE_DATABASE` | `default` (prod) / `posthog` (dev) | |
| `CLICKHOUSE_SECURE` | `true` (prod) / `false` (dev) | TLS |
| `CLICKHOUSE_VERIFY` | `true` | TLS cert verify |
| `CLICKHOUSE_CLUSTER` | `posthog` | |
| `CLICKHOUSE_MIGRATIONS_CLUSTER` | `posthog_migrations` | |
| `CLICKHOUSE_KAFKA_NAMED_COLLECTION` | `msk_cluster` | For Kafka engine tables |

### Kafka

| Variable | Default | Notes |
|----------|---------|-------|
| `KAFKA_HOSTS` | `kafka:9092` | Comma-separated |
| `KAFKA_PREFIX` | `""` | Topic name prefix |
| `SESSION_RECORDING_KAFKA_HOSTS` | falls back to KAFKA_HOSTS | Separate cluster option |

### Redis

| Variable | Default | Notes |
|----------|---------|-------|
| `REDIS_URL` | `redis://redis7:6379/` | Required |
| Various `*_REDIS_HOST` | `redis7` | Per-service Redis config |
| `USE_REDIS_COMPRESSION` | `true` | Zstd compression |

### Object Storage

| Variable | Default | Notes |
|----------|---------|-------|
| `OBJECT_STORAGE_ENABLED` | `false` (prod) | Must enable explicitly |
| `OBJECT_STORAGE_ENDPOINT` | -- | S3 endpoint URL |
| `OBJECT_STORAGE_BUCKET` | `posthog` | |
| `OBJECT_STORAGE_ACCESS_KEY_ID` | -- | |
| `OBJECT_STORAGE_SECRET_ACCESS_KEY` | -- | |
| `SESSION_RECORDING_V2_S3_ENDPOINT` | -- | SeaweedFS endpoint |
| `SESSION_RECORDING_V2_S3_BUCKET` | -- | |
| `SESSION_RECORDING_V2_S3_FORCE_PATH_STYLE` | -- | Required for non-AWS |

### Web Server

| Variable | Default | Notes |
|----------|---------|-------|
| `USE_GRANIAN` | `true` (hobby) | Granian ASGI vs NGINX Unit |
| `GRANIAN_WORKERS` | `2` (hobby) | |
| `NGINX_UNIT_APP_PROCESSES` | `4` | If using Unit |
| `SITE_URL` | `http://localhost:8010` | Public URL |
| `DISABLE_SECURE_SSL_REDIRECT` | -- | Set behind proxy |
| `IS_BEHIND_PROXY` | -- | Trust proxy headers |
| `DEPLOYMENT` | `hobby` | Triggers hobby-mode behavior |

### Temporal (Optional)

| Variable | Default | Notes |
|----------|---------|-------|
| `TEMPORAL_HOST` | `temporal` | |
| `TEMPORAL_PORT` | `7233` | gRPC |
| `TEMPORAL_NAMESPACE` | `default` | |

### Other Important

| Variable | Default | Notes |
|----------|---------|-------|
| `PRIMARY_DB` | `clickhouse` | Set across all containers |
| `LOGGING_FORMATTER_NAME` | `json` | Structured logging |
| `POSTHOG_SKIP_MIGRATION_CHECKS` | -- | Skip on worker/events |
| `SKIP_ASYNC_MIGRATIONS_SETUP` | `1` | Skip async migration setup |
| `OPT_OUT_CAPTURE` | `false` | Disable telemetry |
| `CDP_API_URL` | `http://plugins:6738` | Plugin server URL |
| `RECORDING_API_URL` | `http://recording-api:6738` | Recording API URL |

---

## 5. ClickHouse Configuration

### Required Cluster Names (remote_servers)

ClickHouse config must define these 5 clusters (all point to same host for single-node):
- `posthog` -- main cluster
- `posthog_single_shard` -- single shard queries
- `posthog_migrations` -- migration DDL
- `posthog_writable` -- write operations
- `posthog_primary_replica` -- primary replica reads

### Named Collections

Required for Kafka engine tables:
- `msk_cluster` -> `kafka_broker_list` from env `KAFKA_HOSTS`
- `warpstream_ingestion` -> `kafka_broker_list` from env `KAFKA_HOSTS`

### User-Defined Functions (UDFs)

PostHog ships custom executable pool UDFs for funnel analysis:
- `aggregate_funnel` (steps, cohort, array variants)
- `aggregate_funnel_trends` (trends, array, cohort variants)
- `aggregate_funnel_test` (test variant)
These require the PostHog binary accessible from ClickHouse.

### Key users.xml Settings

- `enable_analyzer: 0`
- `compatibility: 25.6`
- `allow_nondeterministic_mutations: 1`
- `distributed_product_mode: global`
- `throw_on_max_partitions_per_insert_block: false`

### ClickHouse Keeper (Embedded ZK replacement)

Port 9181, eliminates external ZooKeeper dependency. Recommended for single-node.

### Init Script

Creates databases: `posthog` and `cyclotron`

---

## 6. Kafka Topics (30+)

**Core event pipeline:**
- `events_plugin_ingestion` -- main event topic (capture -> ingestion)
- `clickhouse_events_json` -- processed events (ingestion -> ClickHouse)
- `events_plugin_ingestion_overflow` -- overflow events
- `events_plugin_ingestion_historical` -- historical imports

**Session recordings:**
- `session_recording_events`, `session_recording_events2`
- `session_recording_snapshot_item_events`
- `clickhouse_session_replay_events`, `clickhouse_session_recording_events`

**Persons/Groups:**
- `clickhouse_person`, `clickhouse_person_distinct_id`
- `clickhouse_groups`, `clickhouse_precalculated_person_properties`
- `cohort_membership_changed`, `cohort_membership_changed_trigger`

**Error tracking:**
- `exceptions_ingestion`
- `clickhouse_error_tracking_*` (3 topics)

**CDP/Plugins:**
- `cdp_internal_events`, `cdp_backfill_events`
- `plugin_log_entries`

**Other:**
- `clickhouse_app_metrics`, `clickhouse_app_metrics2`
- `clickhouse_heatmap_events`, `clickhouse_ingestion_warnings`
- `events_dead_letter_queue`
- `data_warehouse_source_webhooks` (+DLQ), `data_warehouse_sources_jobs` (+DLQ)
- `log_entries`, `log_entries_v2_test`
- `clickhouse_tophog`, `notification_events`
- `clickhouse_ai_events_json`
- `document_embeddings_input`, `clickhouse_document_embeddings`
- `distinct_id_usage_events_json`, `signals_report_completed`
- `cdp_data_warehouse_source_table`

With `auto_create_topics_enabled: true` on Redpanda, most are created on demand. The kafka-init Job pre-creates critical ones.

---

## 7. Health Check Endpoints

### Django (Python) -- port 8000

- `/_livez` -- Lightweight liveness (200 if process alive)
- `/_readyz` -- Readiness with optional `?role=` parameter
- `/_readyz?role=web` -- Checks: http, postgres, cache
- `/_readyz?role=events` -- Checks: http, kafka_connected
- `/_readyz?role=worker` -- Checks: postgres, cache, celery_broker, clickhouse_connected
- `/_readyz?role=decide` -- Checks: http, cache
- `/_health` -- Deprecated alias for readyz

### Prometheus metrics -- port 8001

All Python containers expose OpenMetrics on 8001.

### Rust services

- feature-flags: `/_readiness` on port 3001
- capture: Controlled by `ADDRESS` env, no documented health path

### Infrastructure

- ClickHouse: `GET /ping` on port 8123
- Redpanda: `GET /v1/status/ready` on port 9644
- Redis: `redis-cli ping`
- PostgreSQL: `pg_isready -U posthog`
- Temporal: `nc -z hostname 7233` (300s start period!)

---

## 8. Migration System

### Order of Operations (from `bin/migrate`)

1. **Cyclotron migrations** (Rust, skipped in hobby mode)
2. **Behavioral cohorts migrations** (Rust, skipped in hobby mode)
3. **ClickHouse migrations** (`manage.py migrate_clickhouse`) -- can run parallel with PG
4. **ClickHouse schema sync** (`manage.py sync_replicated_schema`)
5. **PostgreSQL migrations** (`manage.py migrate --noinput`) -- retry logic (10 retries, exponential backoff)
6. **Product database migrations** (`manage.py migrate_product_databases`)
7. **Persons migrations** (hobby: default DB; production: separate job)
8. **Async migrations** (`manage.py run_async_migrations --complete-noop-migrations` then `--check`)

### Migration supports `--scope` flag

`--scope=postgres`, `--scope=clickhouse`, `--scope=async`, `--scope=cyclotron`, `--scope=behavioral-cohorts`, `--scope=persons`

### ClickHouse Init (pre-migration)

Must create migration tracking tables before Django migrations run:
- `posthog.infi_clickhouse_orm_migrations` (ReplicatedMergeTree)
- `posthog.infi_clickhouse_orm_migrations_distributed` (Distributed)

### Helm Chart Migration Job Pattern

- **Connects directly to PostgreSQL** (NOT PgBouncer) with `USING_PGBOUNCER=false` -- avoids statement_timeout on long migrations
- restartPolicy: Never
- Only has wait-for-service-dependencies init container (no wait-for-migrations obviously)

---

## 9. Helm Chart Patterns Worth Preserving

### PgBouncer

The Helm chart deploys PgBouncer (`bitnami/pgbouncer`) on port 6543 in front of PostgreSQL:
- `pool_mode: transaction`
- `max_client_conn: 1000`
- All PostHog services connect to PgBouncer, not PG directly
- Migration job bypasses PgBouncer
- preStop: `sleep 30 && kill -INT 1 && sleep 31` for graceful drain
- Optional: PgBouncer-Read for read replicas

### Zero-Downtime Web Deploys

- preStop hook with 20s sleep on web pods
- terminationGracePeriodSeconds: 55

### Argo Rollouts Support

Web deployment can be configured as Argo Rollout with canary strategy and weighted traffic.

### Toolbox Deployment

A `sleep infinity` pod with all PostHog env vars -- for running `manage.py` admin commands.

### Split Worker Consumers

Worker deployment creates one Deployment per entry in `worker.consumers` list -- allows scaling different queue consumers independently.

### KEDA Scaling

Recording ingestion deployments support KEDA ScaledObjects based on Kafka consumer lag.

---

## 10. Gotchas and Critical Warnings

1. **K8s is officially unsupported** -- We are reverse-engineering from compose + deprecated Helm chart
2. **No tagged releases** -- PostHog builds from every commit. Use `latest` or pin specific SHA digests
3. **Free features only** -- Self-hosted gets free-plan features exclusively. Premium = cloud-only
4. **Two separate S3 stores required** -- MinIO for general storage, SeaweedFS for session recording v2
5. **Kafka is actually Redpanda** -- Named `kafka` but runs Redpanda. Config uses rpk CLI
6. **Temporal 300s start period** -- Takes 5 minutes to initialize
7. **GeoIP database required** -- feature-flags and cymbal need GeoLite2-City.mmdb at `/share/`. Downloaded from `mmdbcdn.posthog.net`
8. **Hobby Kafka retention = 1 hour** -- Aggressive; unconsumed events are lost
9. **ClickHouse UDFs need PostHog binary** -- The aggregate_funnel functions are executable pool functions
10. **Web runs migrations in hobby mode** -- The `compose/start` script runs migrate before starting server
11. **Worker depends on web** -- Must wait for web to start (migrations to complete)
12. **PostgreSQL init scripts exist** -- The db service mounts `docker/postgres-init-scripts/` from the repo
13. **Granian is now default** for hobby (`USE_GRANIAN=true`, 2 workers) -- NOT NGINX Unit
14. **Port 8001 for metrics** -- All Python containers expose Prometheus metrics on 8001
15. **`PRIMARY_DB=clickhouse`** -- Must be set across all PostHog containers

---

## 11. Minimum Viable K8s Deployment

### Absolutely Required (core functionality):

- PostgreSQL, ClickHouse, Redpanda, Redis, Object Storage (S3/MinIO), SeaweedFS
- kafka-init Job, clickhouse-init Job, posthog-migrate Job
- web, worker, plugins, ingestion-general, capture, replay-capture

### Recommended (full hobby parity):

- ingestion-sessionreplay, recording-api, feature-flags, property-defs-rs

### Optional (specific features):

- Temporal + ES + temporal-django-worker (batch exports, data warehouse)
- ingestion-error-tracking, cymbal (error tracking)
- ingestion-logs, ingestion-traces, capture-logs (OTEL ingestion)
- cyclotron-janitor (job cleanup)
- livestream (live event streaming UI)
- PgBouncer (production connection pooling)

### Can be omitted entirely:

- ZooKeeper (use ClickHouse embedded Keeper)
- Temporal UI, Temporal Admin Tools (debug only)
- Caddy proxy (replaced by Gateway API HTTPRoutes)
