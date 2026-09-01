# SurfSense on Kubernetes — Agent Guide

This directory is the Talos/Kubernetes translation of SurfSense's self-hosted Docker topology. It is GitOps-managed by the `my-apps` ApplicationSet and exposed at `https://surfsense.vanillax.me` through the external Cilium Gateway.

## File map

| Path | What it is |
|---|---|
| `deployment.yaml` | SurfSense API + Celery worker in one pod; they intentionally share the same RWO object-store filesystem |
| `deployment-beat.yaml` | Celery beat scheduler |
| `deployment-zero.yaml` | Rocicorp Zero realtime cache/replication layer; disposable SQLite replica |
| `deployment-frontend.yaml` | SurfSense web frontend |
| `postgres/` | pgvector/PostgreSQL Deployment, Service, and restore-before-bind PVC |
| `redis/` | Redis Deployment, Service, and backup-exempt PVC |
| `migrations-job.yaml` | ArgoCD Sync hook that runs SurfSense migrations before app workloads |
| `service.yaml` | ClusterIP services for backend/frontend/Zero |
| `pvc.yaml` | Durable SurfSense knowledge/object-store PVC |
| `kopiur/postgres-data.yaml` | Hourly Postgres backup + Restore |
| `kopiur/object-store.yaml` | Daily knowledge/object-store backup + Restore |
| `externalsecret.yaml` | 1Password-backed application/database/Zero secrets |
| `httproute.yaml` | Single-origin external routing for frontend, API/auth, and Zero WebSockets |
| `vpa.yaml` | VPAs for every long-running Deployment |

## Invariants — do not break these

1. **Sync order is load-bearing:** Postgres/Redis wave 0 → migrations wave 1 → API+worker/beat/Zero wave 2 → frontend wave 3.
2. **PostgreSQL logical replication is required.** Keep `wal_level=logical`, replication slots, and WAL senders enabled; Zero depends on the `zero_publication` verified by the migration job.
3. **Postgres follows the repo's plain-Postgres + Kopiur pattern.** RWO, `Recreate`, uid/gid 999, `PGDATA` subdir, data checksums, startup/readiness/liveness probes, hourly snapshots, and restore-before-bind.
4. **API and worker MUST see the exact same object-store filesystem.** SurfSense keeps workspace knowledge-store Git working trees beneath `FILE_STORAGE_LOCAL_PATH`. They are co-located in one pod to share one local `longhorn` RWO PVC. Do not split them into separate pods unless the storage design becomes true RWX.
5. **`/shared_tmp` is intentionally `emptyDir`.** It only coordinates temporary upload/processing files between API and worker in the same pod.
6. **Redis is not backed up.** Its PVC exists for ordinary restart continuity only and is explicitly backup-exempt.
7. **Zero is not backed up and has no PVC.** Its SQLite replica is `emptyDir`; replacement resyncs from Postgres.
8. **Keep SurfSense same-origin.** `/api/v1` and `/auth` route to backend, `/zero` routes to Zero, and `/` falls through to frontend.
9. **Do not add upstream OpenSandbox's Docker socket to Talos.** Talos has no Docker daemon/socket. `SANDBOX_ENABLED=FALSE` is intentional until a Kubernetes-native or remote sandbox provider is selected.
10. **Do not request a GPU.** The active RTX 3090 belongs to vLLM. SurfSense uses CPU embeddings and can call vLLM for chat.
11. **Reuse cluster SearXNG** at `http://searxng.searxng.svc.cluster.local:8080`; do not deploy another copy.
12. **Secrets stay in 1Password.** Item `surfsense`: `secret_key`, `db_password`, `zero_admin_password`, `zero_query_api_key`.

## Storage choices

- Postgres: `longhorn-flash` — fsync-sensitive database/WAL workload. Kopiur is proven with the same Longhorn snapshot path.
- Object/knowledge store: `longhorn` — local RWO avoids HDD-NFS small-file/random-I/O penalties; API+worker co-location removes the need for RWX.
- Redis: `longhorn-flash` — AOF is write-heavy, but the volume is disposable and backup-exempt.
- Zero/shared temp: `emptyDir`.

The SurfSense backend image does not set a non-root `USER`, so object-store data is root-owned by default. The namespace therefore carries the repo's `privileged-movers` annotation and the object-store Kopiur mover runs as uid 0. If upstream changes the image user, verify on-disk ownership and change the mover identity before upgrading.

## Local AI

- Base URL: `http://vllm-service.vllm.svc.cluster.local:8080/v1`
- Model: `qwen3.8-27b`

Do not point SurfSense at the parked llama.cpp service unless the repo's AI backend state changes.
