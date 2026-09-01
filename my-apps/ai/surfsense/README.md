# SurfSense

Self-hosted SurfSense research platform for the Talos cluster.

## Deployment shape

- SurfSense `0.0.39`
- PostgreSQL 17 + pgvector with logical replication for Rocicorp Zero
- Redis 8 for Celery/cache
- Rocicorp Zero `1.6.0`
- SurfSense API + Celery worker co-located in one pod so they share one local RWO knowledge/object-store filesystem
- Celery beat, Zero, and frontend run as separate Deployments
- Existing cluster SearXNG reused at `http://searxng.searxng.svc.cluster.local:8080`
- Public single-origin URL: `https://surfsense.vanillax.me`
- OpenSandbox intentionally disabled: upstream's local provider requires a Docker socket, which Talos does not provide

## Required 1Password item

Item name: `surfsense`

Fields:

- `secret_key`
- `db_password`
- `zero_admin_password`
- `zero_query_api_key`

## Local AI

SurfSense can use the existing in-cluster OpenAI-compatible backend:

- Base URL: `http://vllm-service.vllm.svc.cluster.local:8080/v1`
- Model: `qwen3.8-27b`

Initial embeddings use CPU-local `sentence-transformers/all-MiniLM-L6-v2`, so SurfSense does not request a GPU.

## Storage and DR

### Durable

- `surfsense-postgres-data` — `longhorn-flash`, RWO, hourly Kopiur snapshots, restore-before-bind. PostgreSQL runs as uid/gid `999`, uses a `PGDATA` subdirectory, checksums, logical replication, and a pre-snapshot `CHECKPOINT` hook.
- `surfsense-object-store` — `longhorn`, RWO, daily Kopiur snapshots, restore-before-bind. SurfSense stores uploaded blobs and workspace knowledge-store Git working trees under this filesystem. API and worker are in the same pod specifically so both see the exact same volume without using network RWX storage.

### Disposable

- Redis keeps a small `longhorn-flash` RWO PVC for normal restart continuity but is explicitly backup-exempt.
- Zero's SQLite replica uses `emptyDir` and resyncs from PostgreSQL after replacement.
- `/shared_tmp` is `emptyDir` shared by API and worker and is disposable.

## Routing

The external HTTPRoute keeps SurfSense's single-origin contract:

- `/auth/*` -> backend
- `/api/v1/*` -> backend
- `/zero/*` -> Zero/WebSocket
- everything else -> frontend
