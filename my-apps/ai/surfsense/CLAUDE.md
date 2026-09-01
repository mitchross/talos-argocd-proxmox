# SurfSense on Kubernetes — Agent Guide

This directory is the Talos/Kubernetes translation of SurfSense's self-hosted Docker topology. It is GitOps-managed by the `my-apps` ApplicationSet and exposed at `https://surfsense.vanillax.me` through the external Cilium Gateway.

## File map

| Path | What it is |
|---|---|
| `deployment-backend.yaml` | SurfSense API/backend |
| `deployment-worker.yaml` | Celery worker for ingestion/background work |
| `deployment-beat.yaml` | Celery beat scheduler |
| `deployment-zero.yaml` | Rocicorp Zero realtime cache/replication layer |
| `deployment-frontend.yaml` | SurfSense web frontend |
| `database.yaml` | PostgreSQL 17 + pgvector and Redis data-layer workloads/services |
| `migrations-job.yaml` | ArgoCD Sync hook that runs SurfSense migrations before app workloads |
| `service.yaml` | ClusterIP services for backend/frontend/Zero |
| `pvc.yaml` | Longhorn PVCs for PostgreSQL, object store, shared temp, Redis, and Zero |
| `externalsecret.yaml` | 1Password-backed application/database/Zero secrets |
| `httproute.yaml` | Single-origin external routing for frontend, API/auth, and Zero WebSockets |
| `vpa.yaml` | VPAs for every long-running Deployment |

## Invariants — do not break these

1. **Sync order is load-bearing:** data layer wave 0 → migrations wave 1 → backend/worker/beat/Zero wave 2 → frontend wave 3.
2. **PostgreSQL logical replication is required.** Keep `wal_level=logical`, replication slots, and WAL senders enabled; Rocicorp Zero depends on the `zero_publication` created by SurfSense migrations.
3. **Keep SurfSense same-origin.** `/api/v1` and `/auth` route to backend, `/zero` routes to Zero, and `/` falls through to frontend. This is the upstream self-hosted browser contract.
4. **Do not add the upstream OpenSandbox Docker-socket service to Talos.** Talos has no Docker daemon/socket. `SANDBOX_ENABLED=FALSE` is intentional until a Kubernetes-native or remote sandbox provider is chosen.
5. **Do not request a GPU.** The active RTX 3090 belongs to vLLM. SurfSense starts with CPU-local embeddings and can call the existing OpenAI-compatible vLLM service for chat.
6. **Reuse the existing SearXNG instance** at `http://searxng.searxng.svc.cluster.local:8080`; do not deploy a second SurfSense-local SearXNG stack.
7. **RWO data-layer workloads use `strategy: Recreate`.** RollingUpdate can deadlock Longhorn RWO attachment.
8. **Secrets stay in 1Password.** The `surfsense` item supplies `secret_key`, `db_password`, `zero_admin_password`, and `zero_query_api_key`; never commit values.

## Local AI

The cluster's active OpenAI-compatible backend is:

- Base URL: `http://vllm-service.vllm.svc.cluster.local:8080/v1`
- Model: `qwen3.8-27b`

Use that endpoint when configuring SurfSense chat models. Do not point SurfSense at the parked llama.cpp service unless the repo's AI backend state changes.

## Storage / DR

The initial pilot intentionally marks all PVCs backup-exempt while ownership and restore behavior are validated. PostgreSQL and the local object store are the durable candidates for Kopiur. Redis, shared temp, and Zero's SQLite replica are disposable/rebuildable.

Before adding Kopiur, determine the actual on-disk UID/GID for PostgreSQL and backend object-store data and follow `my-apps/CLAUDE.md` restore-before-bind rules.
