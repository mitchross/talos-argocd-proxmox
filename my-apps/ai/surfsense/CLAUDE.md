# SurfSense on Kubernetes — Agent Guide

This directory is the Talos/Kubernetes translation of SurfSense's self-hosted topology. It is GitOps-managed by the `my-apps` ApplicationSet and exposed at `https://surfsense.vanillax.me` through the external Cilium Gateway.

## Argo CD boundary

`my-apps/ai/surfsense` is intentionally **one Argo CD Application** (`my-apps-surfsense`). The `my-apps` ApplicationSet discovers only `my-apps/*/*`; child directories such as `app/`, `postgres/`, `redis/`, and `kopiur/` are organization/resource boundaries, not additional Applications.

Do not split these child folders into independent Argo Applications unless there is a demonstrated independent lifecycle requirement. The stack has tight startup dependencies and is deliberately ordered with resource sync waves inside one Application.

## File map

| Path | What it is |
|---|---|
| `app/deployment.yaml` | SurfSense API + Celery worker in one pod; they intentionally share the same RWO object-store filesystem |
| `app/beat.yaml` | Celery beat scheduler |
| `app/zero.yaml` | Rocicorp Zero realtime cache/replication layer; disposable SQLite replica |
| `app/frontend.yaml` | SurfSense web frontend |
| `app/migrations-job.yaml` | Argo CD Sync hook that runs SurfSense migrations after the data layer is healthy |
| `app/service.yaml` | ClusterIP services for backend/frontend/Zero |
| `app/pvc.yaml` | Durable SurfSense knowledge/object-store PVC |
| `postgres/` | pgvector/PostgreSQL Deployment, Service, and restore-before-bind PVC |
| `redis/` | Redis Deployment, Service, and backup-exempt PVC |
| `kopiur/postgres-data.yaml` | Hourly Postgres backup + Restore |
| `kopiur/object-store.yaml` | Daily knowledge/object-store backup + Restore |
| `externalsecret.yaml` | 1Password-backed application/database/Zero secrets; wave -1 |
| `httproute.yaml` | Single-origin external routing that mirrors SurfSense's upstream Caddy contract |
| `vpa.yaml` | VPAs for every long-running Deployment |

## Sync / health ordering

Argo health gates each wave before advancing:

1. `ExternalSecret` wave **-1** — materialize `surfsense-secrets` before consumers start.
2. Postgres + Redis wave **0** — PVC/Restore resources reconcile in the same application sync; restore-before-bind keeps backed-up PVCs Pending until Kopiur hydrates them.
3. `app/migrations-job.yaml` wave **1** — schema/publication migration hook runs only after the data layer is healthy.
4. API+worker, Celery beat, and Zero wave **2**.
5. Frontend wave **3**.

Do not put the Kopiur `Restore` CR in an earlier isolated wave than its PVC. The repo's restore-before-bind model intentionally lets the Restore/populator/PVC reconcile together while Argo waits for the workload to become healthy.

## Invariants — do not break these

1. **PostgreSQL logical replication is required.** Keep `wal_level=logical`, replication slots, and WAL senders enabled; Zero depends on the `zero_publication` verified by the migration job.
2. **Postgres follows the repo's plain-Postgres + Kopiur pattern.** RWO, `Recreate`, uid/gid 999, `PGDATA` subdir, data checksums, startup/readiness/liveness probes, hourly snapshots, and restore-before-bind.
3. **API and worker MUST see the exact same object-store filesystem.** SurfSense keeps workspace knowledge-store Git working trees beneath `FILE_STORAGE_LOCAL_PATH`. They are co-located in one pod to share one local `longhorn` RWO PVC. Do not split them into separate pods unless the storage design becomes true RWX.
4. **`/shared_tmp` is intentionally `emptyDir`.** It only coordinates temporary upload/processing files between API and worker in the same pod.
5. **Redis is not backed up.** Its PVC exists for ordinary restart continuity only and is explicitly backup-exempt.
6. **Zero is not backed up and has no PVC.** Its SQLite replica is `emptyDir`; replacement resyncs from Postgres.
7. **Mirror SurfSense's upstream same-origin proxy contract exactly.** `/auth/callback` goes to the frontend; `/auth`, `/users`, `/api/v1`, and `/zero/context` go to the backend; remaining `/zero` traffic goes to zero-cache; everything else goes to the frontend. The `/users/me` and `/zero/context` exceptions are required for authenticated dashboard startup. Do not collapse these into broad `/auth` or `/zero` routes without preserving the more-specific exceptions.
8. **Do not add upstream OpenSandbox's Docker socket to Talos.** Talos has no Docker daemon/socket. `SANDBOX_ENABLED=FALSE` is intentional until a Kubernetes-native or remote sandbox provider is selected.
9. **Do not request a GPU.** The active RTX 3090 belongs to vLLM. SurfSense uses CPU embeddings and can call vLLM for chat.
10. **Reuse cluster SearXNG** at `http://searxng.searxng.svc.cluster.local:8080`; do not deploy another copy.
11. **Secrets stay in 1Password.** Item `surfsense`: `secret_key`, `db_password`, `zero_admin_password`, `zero_query_api_key`.

## Storage choices

- Postgres: `longhorn` RWO — current repo standard for app/database block storage; Kopiur restore-before-bind.
- Object/knowledge store: `longhorn` RWO — API+worker co-location removes the need for RWX.
- Redis: `longhorn` RWO — ordinary restart continuity only; backup-exempt.
- Zero/shared temp: `emptyDir`.

The SurfSense backend image does not set a non-root `USER`, so object-store data is root-owned by default. The namespace therefore carries the repo's `privileged-movers` annotation and the object-store Kopiur mover runs as uid 0. If upstream changes the image user, verify on-disk ownership and change the mover identity before upgrading.

## Local AI

- Base URL: `http://vllm-service.vllm.svc.cluster.local:8080/v1`
- Model: `qwen3.8-27b`

Do not point SurfSense at the parked llama.cpp service unless the repo's AI backend state changes.