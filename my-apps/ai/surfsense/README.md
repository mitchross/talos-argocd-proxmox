# SurfSense

Self-hosted SurfSense research platform for the Talos cluster.

## Argo CD boundary

`my-apps/ai/surfsense` is one generated Argo CD Application: `my-apps-surfsense`. Internal `app/`, `postgres/`, `redis/`, and `kopiur/` directories are organizational/resource boundaries only; the `my-apps` ApplicationSet discovers only `my-apps/*/*`.

## Deployment shape

- SurfSense `0.0.39`
- PostgreSQL 17 + pgvector with logical replication for Rocicorp Zero
- Redis 8 for Celery/cache
- Rocicorp Zero `1.6.0`
- SurfSense API + Celery worker co-located in one pod so they share one local RWO knowledge/object-store filesystem
- Celery beat, Zero, and frontend run as separate Deployments
- Existing cluster SearXNG reused at `http://searxng.searxng.svc.cluster.local:8080`
- Public single-origin URL: `https://surfsense.vanillax.me`
- OpenSandbox intentionally disabled because upstream's local provider requires a Docker socket, which Talos does not provide

## Sync order

- wave `-1`: ExternalSecret
- wave `0`: PostgreSQL + Redis and storage/restore reconciliation
- wave `1`: SurfSense migration hook
- wave `2`: API + worker, Celery beat, Zero
- wave `3`: frontend

Argo health gating waits for each wave before advancing. Kopiur Restore CRs and restore-before-bind PVCs intentionally reconcile in the same application sync.

## Required 1Password item

Item name: `surfsense`

Fields:

- `secret_key`
- `db_password`
- `zero_admin_password`
- `zero_query_api_key`

## Local AI

SurfSense uses the existing in-cluster OpenAI-compatible backend through its
operator-owned global model catalog:

- Base URL: `http://vllm-service.vllm.svc.cluster.local:8080/v1`
- Model: `qwen3.8-27b`
- Config: `global_llm_config.yaml`, mounted at `/app/app/config/global_llm_config.yaml`
- Billing tier: `free` — this is local infrastructure, not a metered provider

Initial embeddings use CPU-local `sentence-transformers/all-MiniLM-L6-v2`, so SurfSense does not request a GPU.

## Self-host billing policy

This deployment does not use SurfSense's hosted credit wallet for local infrastructure. `selfhost.env` is materialized as `surfsense-selfhost-policy` and loaded by the API, worker, Beat, and migration containers.

The policy keeps new-user wallet balance at zero and explicitly disables ETL, crawl, captcha, platform-scrape, and Stripe credit billing. This also keeps Auto mode eligible for the local `billing_tier: free` vLLM model instead of treating a default signup credit balance as premium-provider eligibility.

SurfSense upstream defaults new users to a $5 wallet. Accounts created before this policy was applied keep that persisted balance until it is reset once. For a fully local install, reset existing wallets after deployment:

```bash
kubectl -n surfsense exec deploy/surfsense-postgres -- \
  psql -U surfsense -d surfsense -c \
  'UPDATE "user" SET credit_micros_balance = 0, credit_micros_reserved = 0;'
```

This is an operational one-time cleanup, not a recurring GitOps job; Argo must not rewrite user wallet rows on every sync.

## Storage and DR

### Durable

- `surfsense-postgres-data` — `longhorn`, RWO, hourly Kopiur snapshots, restore-before-bind. PostgreSQL runs as uid/gid `999`, uses a `PGDATA` subdirectory, checksums, logical replication, and a pre-snapshot `CHECKPOINT` hook.
- `surfsense-object-store` — `longhorn`, RWO, daily Kopiur snapshots, restore-before-bind. SurfSense stores uploaded blobs and workspace knowledge-store Git working trees under this filesystem. API and worker are in the same pod specifically so both see the exact same volume without requiring RWX storage.

### Disposable

- Redis keeps a small `longhorn` RWO PVC for ordinary restart continuity and is explicitly backup-exempt.
- Zero's SQLite replica uses `emptyDir` and resyncs from PostgreSQL after replacement.
- `/shared_tmp` is `emptyDir` shared by API and worker and is disposable.

## Routing

The external HTTPRoute mirrors SurfSense 0.0.39's upstream Caddy single-origin contract:

- `/auth/callback*` -> frontend
- `/auth/*` -> backend
- `/users/*` -> backend
- `/api/v1/*` -> backend
- `/zero/context` -> backend
- remaining `/zero/*` -> Zero/WebSocket
- everything else -> frontend

The more-specific `/auth/callback` and `/zero/context` matches are intentional. The authenticated dashboard also requires `/users/me` to reach FastAPI; routing `/users/*` to the frontend produces an HTML 404 and the frontend surfaces `Failed to parse response`.
