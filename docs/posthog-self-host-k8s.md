# Self-host PostHog on Kubernetes

This page shows how to run full PostHog (product analytics, session replay and
feature flags) on any Kubernetes cluster. It is for someone who wants to copy
the setup, and for the owner before a PostHog upgrade. The manifests are in
[`my-apps/development-infra/posthog/`](https://github.com/mitchross/talos-argocd-proxmox/tree/main/my-apps/development-infra/posthog).
They are plain Deployments and Kustomize, with no Helm chart.

## What you take on

- PostHog **does not support self-hosting**. Its Helm chart is unmaintained.
  The only maintained reference is the single-box `docker-compose` "hobby"
  deploy ([docs](https://posthog.com/docs/self-host)).
- Upstream ships continuously from `master` (`posthog/posthog:latest`, Rust
  services at `:master`). It publishes no semver releases.
- This guide translates the hobby topology to Kubernetes manifests that you
  own. You are your own vendor. Pin every image by digest, and run the
  [upgrade checklist](#upgrades) before every bump.

## Topology

These services are required. They are the minimum for analytics, session
replay and feature flags:

| Service | Image | Role | Port |
|---|---|---|---|
| web | `posthog/posthog` | Django UI/API monolith | 8000 (+8001 metrics) |
| worker | `posthog/posthog` | Celery tasks/scheduler | none |
| plugins | `ghcr.io/posthog/posthog-node` (`PLUGIN_SERVER_MODE` unset) | CDP / webhooks | 6738 |
| ingestion-general | `ghcr.io/posthog/posthog-node` (`ingestion-v2-combined`) | event ingestion pipeline | none |
| ingestion-sessionreplay | `ghcr.io/posthog/posthog-node` (`recordings-blob-ingestion-v2`) | replay blob writer to S3 | none |
| recording-api | `ghcr.io/posthog/posthog-node` (`recording-api`) | replay playback | 6738 |
| capture | `ghcr.io/posthog/posthog/capture` | Rust event intake | 3000 |
| replay-capture | same image, recordings mode | Rust replay intake | 3000 |
| feature-flags | `ghcr.io/posthog/posthog/feature-flags` | Rust `/decide` + `/flags` | 3001 |
| property-defs-rs | `ghcr.io/posthog/posthog/property-defs-rs` | property definitions | none |
| postgres | `postgres:15.x-alpine` | app metadata | 5432 |
| redis | `valkey` (or redis 7) | cache/locks | 6379 |
| kafka | `redpandadata/redpanda` | event bus (Kafka API, no JVM/ZK) | 9092 |
| clickhouse | `clickhouse/clickhouse-server` | analytics store, single node, embedded Keeper | 8123/9000 |

Match the postgres, redis, redpanda and clickhouse versions to the versions
that upstream's
[`docker-compose.base.yml`](https://github.com/PostHog/posthog/blob/master/docker-compose.base.yml)
pins. That is the only combination that upstream tests.

These services are optional. Skip each one until you need its feature:

| Service | What you lose without it |
|---|---|
| capture-ai | the dedicated LLM-analytics intake (`/i/v0/ai`) with large prompt/completion bodies offloaded to S3. Basic `$ai_*` events still work through the normal capture path |
| livestream | the "Live events" UI tab (needs its own JWT secret and GeoIP) |
| cymbal | error-tracking stack-trace symbolication |
| cyclotron-janitor | CDP destinations (hog functions) job cleanup |
| temporal-django-worker + Temporal server | batch exports / scheduled workflows |
| personhog-router/replica | nothing yet. Ingestion falls back to direct Postgres person handling |
| hypercache-server | nothing yet. Flag/survey config comes from Postgres |
| browserless (Chromium) | page screenshots (heatmap previews, exports) |

In this lab, [Langfuse](domains/ai-gpu/ai-observability.md) records AI
telemetry. PostHog records product analytics, session replay and feature flags.

## Boot order and init jobs

Start the services in a strict order. The order prevents the common first-boot
failures. With ArgoCD, use the sync-wave annotations shown. Without ArgoCD,
apply in this order and wait between steps:

```
wave -1  namespace, secrets, routes
wave  0  postgres, redis, redpanda, clickhouse        (Recreate strategy, RWO PVCs)
wave  1  kafka-init Job (topics) + clickhouse-init Job (tables)
wave  2  migrate Job
wave  3  everything else
```

The `kafka-init` Job creates the topics that ingestion expects
([`core/jobs.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/development-infra/posthog/core/jobs.yaml)):
`events_plugin_ingestion`, `exceptions_ingestion`, `clickhouse_events_json`,
`session_recording_events`, `session_recording_events2`,
`session_recording_snapshot_item_events`, `clickhouse_app_metrics2`,
`logs_ingestion`, plus `events_plugin_ingestion_ai`, `ai_events_ingestion`, and `clickhouse_ai_events_json`
if you run the LLM-analytics capture path.

The `migrate` Job runs these steps in order:

1. Wait for postgres and clickhouse.
2. Run `manage.py migrate`.
3. Run `manage.py migrate_clickhouse`.
4. Run `run_async_migrations`, best-effort.
5. Run `run_async_migrations --check` as the hard gate.

The expected result is a Job in state `Completed`. A failed `--check` fails
the deploy before the app pods roll. **Do not remove the `--check` gate.**

If you use ArgoCD, give every Job `argocd.argoproj.io/hook: Sync` and
`hook-delete-policy: BeforeHookCreation`. A Job is immutable after creation, so
without these annotations an image bump fails the sync.

## Single-node ClickHouse

This is the hardest part of the setup. PostHog's code assumes a sharded,
replicated ClickHouse cluster. A single node works only with all of the
following
([`config/clickhouse/`](https://github.com/mitchross/talos-argocd-proxmox/tree/main/my-apps/development-infra/posthog/config/clickhouse)):

- Use the embedded Keeper, not ZooKeeper. `Replicated*` engines need a Keeper,
  and ClickHouse ships one (`keeper.xml`: port 9181, single `server_id`). You
  then run one StatefulSet less.
- Define nine `remote_servers` clusters that all point at the same node:
  `posthog`, `posthog_single_shard`, `posthog_migrations`, `posthog_writable`,
  `posthog_primary_replica`, plus the satellite clusters `ai_events`, `aux`,
  `ops`, `sessions`. Migrations run `ON CLUSTER <name>` against every one of
  these. A missing name fails `migrate_clickhouse`.
- Mirror upstream's `named_collections` exactly. There are eight:
  `msk_cluster`, `warpstream_ingestion`, `warpstream_calculated_events`,
  `warpstream_replay`, `warpstream_shared`, `warpstream_cyclotron`,
  `warpstream_logs`, `warpstream_traces`. Each one only sets
  `kafka_broker_list from_env="KAFKA_HOSTS"`. Upstream's Kafka-engine tables
  reference them by name, so a missing one fails migrations. Upstream adds to
  this list without notice. Diff it on every monolith bump.
- Create `sharded_events` yourself. Upstream's migrations assume the sharded
  table already exists on each shard. On a single node, create
  `posthog.sharded_events` as a local `ReplicatedReplacingMergeTree`, plus the
  migration-tracking tables, in an init Job before `migrate` runs. See
  [`core/clickhouse-init.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/development-infra/posthog/core/clickhouse-init.yaml).
  If you skip this, async migrations fail later with errors that name
  `sharded_events`.
- Create the `posthog` and `cyclotron` databases in the image's
  `docker-entrypoint-initdb.d`.

## Routing

One hostname routes by path to five backends. The table works with a Gateway
API HTTPRoute or with any Ingress ([`httproute.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/development-infra/posthog/httproute.yaml)):

| Path prefixes | Backend | Port |
|---|---|---|
| `/e`, `/i/v0`, `/capture`, `/batch` | capture | 3000 |
| `/s` | replay-capture | 3000 |
| `/decide`, `/flags` | feature-flags | 3001 |
| `/public/webhooks`, `/public/m` | plugins | 6738 |
| `/` (everything else) | web | 8000 |

Follow these rules:

- **Name your Service ports** (`name: http`). A Gateway API backend fails with
  no error when the port has no name.
- If SDK ingest is internet-facing but the UI is not, publish a second
  hostname with the same path rules minus `/`.
- Behind a proxy, set `IS_BEHIND_PROXY=true` and `TRUSTED_PROXIES=<gateway IPs>`.
  Keep `SITE_URL` equal to the public UI URL.

## Config and secrets

### Shared env ConfigMap

Put the common env in one ConfigMap. Every Python and Node workload reads it
through `envFrom`. Kustomize's `configMapGenerator` adds a hash to the name, so
an env edit rolls every consumer. You do not restart pods by hand, and no pod
keeps old config.

These are the baseline values
([`posthog-env.env`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/development-infra/posthog/posthog-env.env)):

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

### Secrets

A plain Kubernetes Secret works. Use External Secrets Operator if you have a
vault. You need `SECRET_KEY` (any long random string), `ENCRYPTION_SALT_KEYS`
(`openssl rand -hex 16`, exactly 32 hex chars), the postgres password,
`DATABASE_URL`, and the S3 access and secret keys.

### Object storage

Use any S3-compatible backend (MinIO, RustFS, Garage, SeaweedFS):

```bash
OBJECT_STORAGE_ENABLED=true
OBJECT_STORAGE_ENDPOINT=http://<s3-host>:<port>   # path-style
OBJECT_STORAGE_BUCKET=posthog
SESSION_RECORDING_V2_S3_ENDPOINT=...              # same backend is fine
SESSION_RECORDING_V2_S3_BUCKET=posthog
SESSION_RECORDING_V2_S3_FORCE_PATH_STYLE=true
```

Session replay does not work without object storage. Create the bucket before
first boot.

## Sizing

These are measured single-node baselines under light homelab traffic. Scale up
from them, not down:

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

Follow these sizing rules:

- Cap celery. The worker defaults `--concurrency` to the node's CPU count
  (32 forks on a big node) and never recycles a fork. Leaked memory grows to
  tens of Gi. Set these on the worker container:
  `WEB_CONCURRENCY=4`, `CELERY_MAX_TASKS_PER_CHILD=300`,
  `CELERY_MAX_MEMORY_PER_CHILD=1048576` (KiB).
- **Use `strategy: Recreate` on every Deployment with an RWO PVC.** An RWO PVC
  is a disk that one node mounts at a time. `RollingUpdate` deadlocks on
  Multi-Attach, because the new pod cannot mount the disk the old pod holds.
- Set memory limits and no CPU limits. No CPU limit means no throttling, and
  the requests still guide scheduling. This rule is optional.
- Set `NGINX_UNIT_APP_PROCESSES=2` to shrink the web monolith. The upstream
  default is 4.

## Upgrades

You are the vendor, so plan every bump:

1. Pin by digest (`image:tag@sha256:…`), including `:latest`/`:master`
   images. The tag documents intent, and the digest makes it immutable.
2. Bump `posthog/posthog` and `ghcr.io/posthog/posthog-node` together. The
   `migrate` Job runs the monolith image, so web, worker and plugin-server must
   match it.
3. Before any monolith bump, run the drift checklist. Upstream changes its
   compose file and configs without notice. Config drift, not code, is what
   breaks a self-hosted install:
   - diff upstream `docker/clickhouse/config.d/default.xml` against yours: new
     `named_collections` / `remote_servers` / satellite clusters must be
     mirrored or `migrate_clickhouse` fails;
   - grep new upstream `posthog/clickhouse/migrations/` for `sharded_*` tables,
     since each needs a bootstrap stanza in your clickhouse-init Job;
   - grep `docker-compose.base.yml` and `.env.services` for newly required env;
   - re-check the server entrypoint (`bin/docker-server-unit`) for changed
     process-model defaults.
4. Change the postgres, redis, redpanda or clickhouse version only when
   upstream's compose pins change.

The `run_async_migrations --check` gate in the `migrate` Job protects each
bump. A bump that needs an unapplied async migration fails the deploy before
any app pod rolls.

## Verify

Run these checks after first boot and after every upgrade:

```bash
kubectl -n posthog get pods                     # all Running, migrate Job Completed
kubectl -n posthog logs job/posthog-migrate     # ends "All migrations complete"
```

- Send an event from any SDK (or `curl -X POST https://<host>/e/ ...`). It
  appears in **Activity** within seconds.
- Record a session on an instrumented page. It plays back in **Session replay**,
  which proves the whole path: capture, kafka, ingestion-sessionreplay, S3,
  recording-api.
- `curl https://<host>/flags?v=2 -d '{"api_key":"<project key>","distinct_id":"x"}'`
  returns JSON, which proves the Rust feature-flags path.
- In ClickHouse, the count from `SELECT count() FROM events` grows. The
  postgres and redpanda logs are clean.

## Backups and cluster rebuild

Each PostHog store has a different value, so each gets a different backup rule:

| Store | Holds | Backup posture |
|---|---|---|
| Postgres | The identity layer: project API keys (`Team.api_token`, the `phc_` key every SDK embeds), personal API keys, users/orgs, dashboards, insights, feature-flag and cohort definitions | **Back this up.** It is small (single-digit GiB) and irreplaceable |
| ClickHouse | Event history, recording metadata | Optional. Rebuilds empty from migrations; only history is lost |
| Kafka / Redis | In-flight buffers, caches | Disposable. Init Jobs and warm-up recreate them |
| Object storage | Recording blobs | Useless without ClickHouse metadata; treat like ClickHouse |

Follow these rules so that a cluster rebuild keeps the identity layer:

1. Back up the Postgres PVC, with a backup based on a volume snapshot or with
   a scheduled `pg_dump` to S3. A crash-consistent volume snapshot is enough.
   Postgres recovers from it through its WAL, as it does after a power loss.
   This lab uses kopiur with restore-before-bind
   (`my-apps/development-infra/posthog/kopiur/postgres-data.yaml`). The PVC's
   `dataSourceRef` points at a `Restore` object. On a rebuild, the PVC fills
   from the latest backup before Postgres starts.
2. Keep `SECRET_KEY` and `ENCRYPTION_SALT_KEYS` in an external secret manager,
   never only in the cluster. Without the same salt keys, the encrypted
   Postgres fields (integration credentials) are unreadable after a restore.
3. Restore Postgres with the same secrets. The project API key is then
   identical, so instrumented apps keep sending through the rebuild. Dashboards
   and flags are intact. Analytics history starts empty, and Persons views are
   sparse until new events arrive.
4. Do not bump the Postgres major version without a migration plan. A restored
   data directory starts only on the major version that wrote it.

## Replay retention on a self-hosted project

This section applies to this lab's deployment. It explains why the Git repo
carries a local patch for session replay retention.

Project 1 declares 30-day replay retention through
`SELF_HOSTED_REPLAY_RETENTION_TEAM_IDS=1` in `posthog-env.env`. The migration
hook runs `scripts/configure-replay-retention.py` after the Django migrations.
The script sets that supported Team model field. It updates only the listed
projects and skips a project that does not exist yet. The setting for such a
project is applied on the next ArgoCD sync after you create the project. Add
another project ID to the comma-separated list only when that project must
also use 30 days.

The patch exists because of three upstream behaviours:

- The pinned PostHog revision
  [`065179102`](https://github.com/PostHog/posthog/blob/065179102ef87898ef952381080b55c453e7867d/posthog/api/team.py)
  rejects retention updates with `Invalid retention entitlement.` (HTTP 500)
  when a self-hosted organization lacks billing metadata.
- A self-hosted project defaults to five years, so the rejection also blocks
  the ordinary 30-day option.
- PostHog's hourly feature sync removes an entitlement that you insert once by
  hand.

The Git repo therefore carries a **local compatibility patch**. It is not an
environment switch that upstream supports. `scripts/patch-replay-retention.py`
allows exactly `30d`, and only when the retention feature is absent and
`is_cloud()` is false. Existing entitlements and checks for longer retention
follow the original validator. The patch creates no license or billing feature
records.

The migration hook checks the hash of the upstream validator before it runs.
The web container applies the same patch to its own source before it starts.
An unexpected source change fails the hook. Then do the
[upgrade review](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/development-infra/posthog/UPGRADE.md).
A generated ConfigMap mounts the scripts, so every fresh pod applies the patch
again.

### Verify retention

Rendering the manifests locally and running the unit tests change no live
retention state. Verify on the cluster after ArgoCD finishes the sync:

1. Confirm that the migration Job reports
   `Project 1: replay retention set to 30d` (or `already 30d`).
2. Open **Settings → Project → Session replay**, select 30 days, save, and
   reload. Expect the team update to return HTTP 200 and the saved value `30d`.
3. Check the value again after the hourly feature sync at minute 30.
4. Capture and play a new recording to confirm that replay still works.

### Limits and rollback

The patch changes the project's retention setting. It does not rewrite the
expiry metadata of existing recordings or the lifecycle policy of the object
store.

Roll back the startup wrapper, the patch and the reconciliation script through
Git and ArgoCD. A Git revert does not restore an earlier retention value in the
database. Declare the value you want in a reviewed follow-up change before you
enable the reconciliation again.
