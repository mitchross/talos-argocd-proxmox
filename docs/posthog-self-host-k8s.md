# Self-Hosting PostHog on Kubernetes

A working recipe for running full PostHog (product analytics, session replay,
feature flags) on any Kubernetes cluster. The reference implementation lives in
[`my-apps/development/posthog/`](https://github.com/mitchross/talos-argocd-proxmox/tree/main/my-apps/development/posthog)
— plain Deployments + Kustomize, no Helm, portable to any cluster.

## 1. Reality check

- PostHog **does not support self-hosting**: the Helm chart is dead, and the only
  maintained reference is the single-box `docker-compose` "hobby" deploy
  ([docs](https://posthog.com/docs/self-host)).
- Upstream ships continuously from `master` (`posthog/posthog:latest`, Rust
  services at `:master`) — there are no semver releases to follow.
- This guide translates the hobby topology to Kubernetes manifests you own.
  Expect to act as your own vendor: pin digests, and run the
  [upgrade checklist](#8-upgrades) before every bump.

## 2. Topology

**Required** — the minimum for analytics + session replay + feature flags:

| Service | Image | Role | Port |
|---|---|---|---|
| web | `posthog/posthog` | Django UI/API monolith | 8000 (+8001 metrics) |
| worker | `posthog/posthog` | Celery tasks/scheduler | — |
| plugins | `posthog/posthog-node` (`PLUGIN_SERVER_MODE` unset) | CDP / webhooks | 6738 |
| ingestion-general | `posthog/posthog-node` (`ingestion-v2-combined`) | event ingestion pipeline | — |
| ingestion-sessionreplay | `posthog/posthog-node` (`recordings-blob-ingestion-v2`) | replay blob writer → S3 | — |
| recording-api | `posthog/posthog-node` (`recording-api`) | replay playback | 6738 |
| capture | `ghcr.io/posthog/posthog/capture` | Rust event intake | 3000 |
| replay-capture | same image, recordings mode | Rust replay intake | 3000 |
| feature-flags | `ghcr.io/posthog/posthog/feature-flags` | Rust `/decide` + `/flags` | 3001 |
| property-defs-rs | `ghcr.io/posthog/posthog/property-defs-rs` | property definitions | — |
| postgres | `postgres:15.x-alpine` | app metadata | 5432 |
| redis | `valkey` (or redis 7) | cache/locks | 6379 |
| kafka | `redpandadata/redpanda` | event bus (Kafka API, no JVM/ZK) | 9092 |
| clickhouse | `clickhouse/clickhouse-server` | analytics store, single node, embedded Keeper | 8123/9000 |

Match postgres/redis/redpanda/clickhouse versions to whatever upstream's
[`docker-compose.base.yml`](https://github.com/PostHog/posthog/blob/master/docker-compose.base.yml)
currently pins — that's the only combination upstream tests.

**Optional** — skip these until you need the feature:

| Service | What you lose without it |
|---|---|
| capture-ai | the dedicated LLM-analytics intake (`/i/v0/ai`) with large prompt/completion bodies offloaded to S3 — basic `$ai_*` events still work through the normal capture path |
| livestream | the "Live events" UI tab (needs its own JWT secret + GeoIP) |
| cymbal | error-tracking stack-trace symbolication |
| cyclotron-janitor | CDP destinations (hog functions) job cleanup |
| temporal-django-worker + Temporal server | batch exports / scheduled workflows |
| personhog-router/replica | nothing yet — ingestion falls back to direct Postgres person handling |
| hypercache-server | nothing yet — flag/survey config served from Postgres |
| browserless (Chromium) | page screenshots (heatmap previews, exports) |

## 3. Boot order and init jobs

Strict ordering prevents every classic first-boot failure. With ArgoCD use
sync-waves (shown); otherwise apply in this order and wait between steps:

```
wave -1  namespace, secrets, routes
wave  0  postgres, redis, redpanda, clickhouse        (Recreate strategy, RWO PVCs)
wave  1  kafka-init Job (topics) + clickhouse-init Job (tables)
wave  2  migrate Job
wave  3  everything else
```

**kafka-init** pre-creates the topics ingestion expects
([`core/jobs.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/development/posthog/core/jobs.yaml)):
`events_plugin_ingestion`, `exceptions_ingestion`, `clickhouse_events_json`,
`session_recording_events`, `session_recording_events2`,
`session_recording_snapshot_item_events`, `clickhouse_app_metrics2`,
`logs_ingestion`, plus `ai_events_ingestion` and `clickhouse_ai_events_json`
if you run the LLM-analytics capture path.

**migrate** runs, in order: wait for postgres + clickhouse → `manage.py migrate`
→ `manage.py migrate_clickhouse` → `run_async_migrations` best-effort, then
`run_async_migrations --check` as the hard gate. Expected result: Job
`Completed`; a failed `--check` fails the deploy **before** app pods roll —
that is the design, don't remove it.

If you use ArgoCD: give every Job `argocd.argoproj.io/hook: Sync` +
`hook-delete-policy: BeforeHookCreation` (Jobs are immutable; image bumps fail
the sync otherwise).

## 4. Single-node ClickHouse (the hard part)

PostHog's code assumes a sharded, replicated ClickHouse cluster. A single node
works, but only with all of the following
([`config/clickhouse/`](https://github.com/mitchross/talos-argocd-proxmox/tree/main/my-apps/development/posthog/config/clickhouse)):

- **Embedded Keeper, no ZooKeeper.** `Replicated*` engines need a Keeper;
  ClickHouse ships one (`keeper.xml`: port 9181, single `server_id`). One less
  StatefulSet.
- **Nine `remote_servers` clusters, all pointing at the same node**:
  `posthog`, `posthog_single_shard`, `posthog_migrations`, `posthog_writable`,
  `posthog_primary_replica`, plus the satellite clusters `ai_events`, `aux`,
  `ops`, `sessions`. Migrations run `ON CLUSTER <name>` against every one of
  these — a missing name fails `migrate_clickhouse`.
- **Mirror upstream's `named_collections` exactly** (currently eight:
  `msk_cluster`, `warpstream_ingestion`, `warpstream_calculated_events`,
  `warpstream_replay`, `warpstream_shared`, `warpstream_cyclotron`,
  `warpstream_logs`, `warpstream_traces`) — each just setting
  `kafka_broker_list from_env="KAFKA_HOSTS"`. Upstream's Kafka-engine tables
  reference them by name; absence fails migrations. This list grows without
  notice — diff it on every monolith bump.
- **Bootstrap `sharded_events` yourself.** Upstream's migrations assume the
  sharded table already exists on each shard. On a single node, create
  `posthog.sharded_events` as a local `ReplicatedReplacingMergeTree` (plus the
  migration-tracking tables) in an init Job before migrate runs — see
  [`core/clickhouse-init.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/development/posthog/core/clickhouse-init.yaml).
  Skipping this surfaces later as async-migration failures referencing
  `sharded_events`.
- Create the `posthog` and `cyclotron` databases in the image's
  `docker-entrypoint-initdb.d`.

## 5. Routing

One hostname, path-routed to five backends. Works with Gateway API HTTPRoute or
any Ingress ([`httproute.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/development/posthog/httproute.yaml)):

| Path prefixes | Backend | Port |
|---|---|---|
| `/e`, `/i/v0`, `/capture`, `/batch` | capture | 3000 |
| `/s` | replay-capture | 3000 |
| `/decide`, `/flags` | feature-flags | 3001 |
| `/public/webhooks`, `/public/m` | plugins | 6738 |
| `/` (everything else) | web | 8000 |

Rules:

- **Name your Service ports** (`name: http`) — Gateway API backends fail
  silently without named ports.
- If SDK ingest is internet-facing but the UI is not, publish a second
  hostname with the same path rules minus `/`.
- Behind a proxy set `IS_BEHIND_PROXY=true` + `TRUSTED_PROXIES=<gateway IPs>`,
  and keep `SITE_URL` = the public UI URL.

## 6. Config and secrets

**Shared env ConfigMap.** Put the common env in one ConfigMap consumed via
`envFrom` by every Python/Node workload. With Kustomize's `configMapGenerator`
the name is hash-suffixed, so any env edit automatically rolls every consumer —
no manual restarts, no stale-config pods.

Baseline that matters
([`posthog-env.env`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/development/posthog/posthog-env.env)):

```bash
SITE_URL=https://posthog.example.com
DEPLOYMENT=hobby                 # tells PostHog it's self-hosted
PRIMARY_DB=clickhouse
PGHOST=db  PGDATABASE=posthog  PGUSER=posthog
KAFKA_HOSTS=kafka:9092
CLICKHOUSE_HOST=clickhouse  CLICKHOUSE_DATABASE=posthog  CLICKHOUSE_SECURE=false
CLICKHOUSE_MIGRATIONS_CLUSTER=posthog_migrations
SKIP_ASYNC_MIGRATIONS_SETUP=1    # the migrate Job owns async migrations
IS_BEHIND_PROXY=true  TRUSTED_PROXIES=<gateway IPs>  DISABLE_SECURE_SSL_REDIRECT=true
OTEL_SDK_DISABLED=true
OPT_OUT_CAPTURE=true             # don't phone home usage analytics
```

**Secrets** (a plain K8s Secret works; External Secrets Operator if you have a
vault): `SECRET_KEY` (any long random), `ENCRYPTION_SALT_KEYS`
(`openssl rand -hex 16` — exactly 32 hex chars), postgres password +
`DATABASE_URL`, S3 access/secret keys.

**Object storage** — any S3-compatible backend (MinIO, RustFS, Garage, SeaweedFS):

```bash
OBJECT_STORAGE_ENABLED=true
OBJECT_STORAGE_ENDPOINT=http://<s3-host>:<port>   # path-style
OBJECT_STORAGE_BUCKET=posthog
SESSION_RECORDING_V2_S3_ENDPOINT=...              # same backend is fine
SESSION_RECORDING_V2_S3_BUCKET=posthog
SESSION_RECORDING_V2_S3_FORCE_PATH_STYLE=true
```

Session replay does not work without object storage — create the bucket before
first boot.

## 7. Sizing

Measured single-node baselines (light homelab traffic; scale up, not down):

| Workload | CPU req | Mem req | Mem limit |
|---|---|---|---|
| web | 600m | 4Gi | 12Gi |
| worker | 250m | 4Gi | 20Gi |
| plugins / ingestion-general / ingestion-sessionreplay | 200m | 512Mi | 2Gi |
| recording-api | 100m | 256Mi | 1Gi |
| capture / replay-capture / feature-flags | 100m | 128Mi | 512Mi |
| clickhouse | 500m | 4Gi | 16Gi (40Gi PVC) |
| redpanda | 500m | 2Gi | 4Gi (8Gi PVC) |
| postgres | 250m | 512Mi | 4Gi (8Gi PVC) |
| valkey | 50m | 64Mi | 768Mi (4Gi PVC) |

Rules that keep it healthy:

- **Cap celery.** The worker defaults `--concurrency` to the node's CPU count
  (32 forks on a big node) with no recycling — leaked memory accumulates into
  the tens of Gi. Set on the worker container:
  `WEB_CONCURRENCY=4`, `CELERY_MAX_TASKS_PER_CHILD=300`,
  `CELERY_MAX_MEMORY_PER_CHILD=1048576` (KiB).
- **`strategy: Recreate` on every Deployment with an RWO PVC** — RollingUpdate
  deadlocks on Multi-Attach.
- Memory limits only, no CPU limits (avoid throttling; requests handle
  scheduling). Optional but recommended.
- `NGINX_UNIT_APP_PROCESSES=2` trims the web monolith (upstream default 4).

## 8. Upgrades

You are the vendor. Every bump is deliberate:

1. **Pin by digest** (`image:tag@sha256:…`), including `:latest`/`:master`
   images — the tag documents intent, the digest makes it immutable.
2. **Bump `posthog/posthog` and `posthog/posthog-node` in lockstep** — the
   migrate Job runs the monolith image; web/worker/plugin-server must match it.
3. Before any monolith bump, run the drift checklist — upstream's compose and
   configs move without notice, and config drift (not code) is what breaks
   self-hosts:
   - diff upstream `docker/clickhouse/config.d/default.xml` against yours: new
     `named_collections` / `remote_servers` / satellite clusters must be
     mirrored or `migrate_clickhouse` fails;
   - grep new upstream `posthog/clickhouse/migrations/` for `sharded_*` tables
     — each needs a bootstrap stanza in your clickhouse-init Job;
   - grep `docker-compose.base.yml` + `.env.services` for newly required env;
   - re-check the server entrypoint (`bin/docker-server-unit`) for changed
     process-model defaults.
4. Only move postgres/redis/redpanda/clickhouse when upstream's compose pins
   move.

The `run_async_migrations --check` gate in the migrate Job is your safety net:
a bump that needs an unapplied async migration fails the deploy before any app
pod rolls.

## 9. Verify

After first boot (and every upgrade):

```bash
kubectl -n posthog get pods                     # all Running, migrate Job Completed
kubectl -n posthog logs job/posthog-migrate     # ends "All migrations complete"
```

- Send an event from any SDK (or `curl -X POST https://<host>/e/ ...`) → it
  appears in **Activity** within seconds.
- Record a session on an instrumented page → it plays back in **Session replay**
  (proves capture → kafka → ingestion-sessionreplay → S3 → recording-api).
- `curl https://<host>/flags?v=2 -d '{"api_key":"<project key>","distinct_id":"x"}'`
  returns JSON (proves the Rust feature-flags path).
- ClickHouse: `SELECT count() FROM events` grows; postgres/redpanda logs clean.

## 10. Backups and cluster rebuild

PostHog's stores split cleanly by value:

| Store | Holds | Backup posture |
|---|---|---|
| **Postgres** | The identity layer: project API keys (`Team.api_token` — the `phc_` key every SDK embeds), personal API keys, users/orgs, dashboards, insights, feature-flag and cohort definitions | **Back this up.** It is small (single-digit GiB) and irreplaceable |
| ClickHouse | Event history, recording metadata | Optional. Rebuilds empty from migrations; only history is lost |
| Kafka / Redis | In-flight buffers, caches | Disposable — init Jobs and warm-up recreate them |
| Object storage | Recording blobs | Useless without ClickHouse metadata; treat like ClickHouse |

Rules that make a cluster rebuild painless:

1. **Back up the Postgres PVC** (volume-snapshot based backup, or scheduled
   `pg_dump` to S3). A crash-consistent volume snapshot is fine — Postgres
   WAL-recovers from it like a power loss. The reference repo uses a
   restore-before-bind populator
   (`my-apps/development/posthog/kopiur/postgres-data.yaml`): the PVC's
   `dataSourceRef` points at a Restore object, so on rebuild the volume
   hydrates from the latest snapshot *before* Postgres starts.
2. **Keep `SECRET_KEY` and `ENCRYPTION_SALT_KEYS` in an external secret
   manager**, never only in-cluster. Encrypted Postgres fields (integration
   credentials) are unreadable after a restore without the same salt keys.
3. **Restore Postgres + keep the same secrets = SDKs never notice.** The
   project API key comes back identical, so instrumented apps keep sending
   through the rebuild; dashboards and flags are intact; analytics history
   starts fresh (Persons views are sparse until events re-accumulate).
4. Never bump the Postgres major version casually — a restored data directory
   only starts on the major it was written by.
