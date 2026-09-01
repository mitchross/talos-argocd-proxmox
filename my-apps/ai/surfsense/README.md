# SurfSense

Self-hosted SurfSense research platform for the Talos cluster.

## Deployment shape

- SurfSense `0.0.39`
- PostgreSQL 17 + pgvector with logical replication enabled for Rocicorp Zero
- Redis 8 for Celery/cache
- Rocicorp Zero `1.6.0`
- SurfSense backend, Celery worker, Celery beat, and web frontend
- Existing cluster SearXNG reused at `http://searxng.searxng.svc.cluster.local:8080`
- Public single-origin URL: `https://surfsense.vanillax.me`
- OpenSandbox intentionally disabled: upstream's local OpenSandbox provider requires a Docker socket, which Talos does not provide

## Required 1Password item

Create an item named `surfsense` with these fields before merging/syncing:

- `secret_key` — random application/JWT secret
- `db_password` — random PostgreSQL password
- `zero_admin_password` — random Zero admin password
- `zero_query_api_key` — random shared secret for Zero -> frontend query forwarding

Example random values can be produced locally with `openssl rand -base64 32`.

## Local model

SurfSense's provider/model selection is configured in the application. For local chat inference use the in-cluster vLLM endpoint:

- Base URL: `http://vllm-service.vllm.svc.cluster.local:8080/v1`
- Model: `qwen3.8-27b`

The initial embedding configuration uses SurfSense's CPU-local `sentence-transformers/all-MiniLM-L6-v2`, so this app does not request a GPU and does not compete with the active vLLM pod.

## Storage

Postgres and Zero/Redis state use Longhorn RWO PVCs. The object store and shared temporary processing volume use Longhorn RWX because both API and worker pods must mount them concurrently.

The initial pilot marks PVCs backup-exempt. Before treating SurfSense as durable production data, validate on-disk ownership and add Kopiur policies for PostgreSQL and the object store; Redis, shared temp, and Zero cache remain disposable.

## Upstream path routing

The HTTPRoute preserves SurfSense's documented single-origin contract:

- `/auth/*` -> backend
- `/api/v1/*` -> backend
- `/zero/*` -> zero-cache (WebSocket)
- everything else -> frontend
