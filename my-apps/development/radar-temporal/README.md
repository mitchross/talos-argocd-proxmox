# radar-temporal — dedicated Temporal control plane for Radar NG

**Purpose:** a second, Radar-only Temporal server so Radar workflows stop
sharing the one-shard `temporal` control plane with every other app.
**Status:** current desired state; the cluster is deployed *empty* — no
Radar workers, schedules, or `TemporalConnection` point at it yet. The
cutover is a separate change in `my-apps/development/radar-ng/`.

| Fact | Value |
|---|---|
| Kubernetes namespace | `radar-temporal` (ArgoCD app `my-apps-radar-temporal`, wave 6) |
| Logical Temporal namespace | `radar-ng`, 7-day retention, seeded by `scripts/seed-namespaces.sh` |
| History shards | **32**, immutable after first boot |
| Server services | frontend, history, matching, worker — **3 replicas each**, one per wired zone |
| UI / admintools | 1 replica each, `radar-temporal.vanillax.me` on the internal gateway |
| Database | plain Postgres 17, 30Gi PVC on `longhorn-wired-ha` (2 Longhorn replicas), kopiur hourly at :36 |

## Scope

This directory owns the Temporal **server** and its Postgres. It deliberately
does not:

- touch `my-apps/development/radar-ng/` (workers, schedules, the shared
  `TemporalConnection`);
- back up anything on the shared `temporal` namespace;
- claim cluster-level HA — Talos still has one control-plane/etcd node.

## How placement works

All three placement rules are Helm values in `values.yaml`; nothing is
patched after render.

| Rule | Where | Effect |
|---|---|---|
| `server.affinity` nodeAffinity `node.vanillax.dev/link In [wired]` | all four server services (Postgres repeats it in `postgres/deployment.yaml`) | only hp-sff, hp-elite, dell are eligible |
| per-service `topologySpreadConstraints` on `topology.kubernetes.io/zone`, `maxSkew: 1`, `DoNotSchedule` | frontend/history/matching/worker | exactly one replica per wired node |
| `server.deploymentStrategy` `maxSurge: 0`, `maxUnavailable: 1` | all four server services | a rollout reuses the freed zone instead of needing a 4th slot |
| per-service `podDisruptionBudget: {maxUnavailable: 1}` | frontend/history/matching/worker | drains move one pod at a time |

Consequence to know: if a wired node is down, its replica stays `Pending`
until the node returns (the spread refuses to double up a zone). Two of three
replicas keep serving. That is intended.

## Prerequisites (before merging)

1. **Longhorn node tags.** `longhorn-wired-ha` requires the Longhorn node tag
   `wired-storage` on at least two wired nodes (PR #2191). Until then the PVC
   stays `Pending` and the whole app waits at wave -2 — it fails closed.
   Verify:
   ```sh
   kubectl -n longhorn-system get nodes.longhorn.io -o custom-columns='NAME:.metadata.name,TAGS:.spec.tags'
   ```
   Expected: `[wired-storage]` on the hp-sff, hp-elite, and dell nodes.
2. **1Password property.** Add `radar_temporal_db_password` to the
   `postgres-secrets` item in the `homelab-prod` vault (new random password —
   do **not** copy `temporal_db_password`). Until it exists the ExternalSecret
   reports `SecretSyncedError` and Postgres never starts. Verify after sync:
   ```sh
   kubectl -n radar-temporal get externalsecret radar-temporal-db-secret
   ```
   Expected: `STATUS SecretSynced`, `READY True`.
3. Node labels already present (read-only check):
   ```sh
   kubectl get nodes -L node.vanillax.dev/link,topology.kubernetes.io/zone
   ```
   Expected: three nodes with `LINK wired` and three distinct zones.

## Verification (after merge)

```sh
# 1. ArgoCD app healthy, all pods on wired nodes, one per zone
kubectl get application -n argocd my-apps-radar-temporal
kubectl -n radar-temporal get deploy
kubectl -n radar-temporal get pods -o wide
```
Expected: frontend/history/matching/worker `3/3`, postgres/web/admintools
`1/1`; each 3-replica service has pods on three different nodes.

```sh
# 2. PDBs and PVC
kubectl -n radar-temporal get pdb
kubectl -n radar-temporal get pvc radar-temporal-postgres-data
kubectl -n longhorn-system get volumes.longhorn.io -o custom-columns='NAME:.metadata.name,PVC:.status.kubernetesStatus.pvcName,ROBUST:.status.robustness' | grep radar-temporal
```
Expected: four PDBs with `MAX UNAVAILABLE 1`; PVC `Bound` on
`longhorn-wired-ha`; the Longhorn volume `healthy` with two replicas on two
different nodes (check in the Longhorn UI or `kubectl -n longhorn-system get replicas.longhorn.io`).

```sh
# 3. Temporal itself: 32 shards, namespace radar-ng exists
kubectl -n radar-temporal exec deploy/radar-temporal-admintools -- \
  temporal --address radar-temporal-frontend:7233 operator cluster describe
kubectl -n radar-temporal exec deploy/radar-temporal-admintools -- \
  temporal --address radar-temporal-frontend:7233 operator namespace describe -n radar-ng
```
Expected: `HistoryShardCount 32`; namespace `radar-ng` with
`WorkflowExecutionRetentionTtl 168h0m0s`.

```sh
# 4. Backups and alerts wired up
kubectl -n radar-temporal get secret kopiur-rustfs
kubectl -n radar-temporal get snapshotpolicy,snapshotschedule,restore,snapshot
kubectl -n radar-temporal get servicemonitor,prometheusrule
```
Expected: the secret exists; after the first :36 a `Snapshot` reaches
`Succeeded` with non-zero files.

Web UI: <https://radar-temporal.vanillax.me> (internal gateway, LAN only).

## Timer DLQ

Same rule as the shared server: a non-zero timer DLQ is an incident.
Inventory with `tdbg dlq list --print-json` in `radar-temporal-admintools`,
merge only an explicitly approved contiguous prefix, never purge. The full
procedure is in `../temporal/README.md` § "Timer DLQ alert runbook"; swap the
namespace and deployment names.

## Rollback

Revert the merge commit. ArgoCD prunes the namespace and everything in it.
Two things to know before doing that:

- `longhorn-wired-ha` is `reclaimPolicy: Delete` — pruning the PVC deletes the
  Longhorn volume. The kopiur repository keeps the snapshots (the component
  sets `onPolicyDelete: Retain`), so a re-deploy restores from the latest one
  via `dataSourceRef`.
- Nothing else depends on this namespace until the Radar cutover, so a revert
  has no effect on the shared `temporal` control plane or on `radar-ng`.

## Source of truth

- `values.yaml` — image pin, shards, replicas, placement, PDBs.
- `postgres/` + `kopiur/radar-temporal-postgres-data.yaml` — database and backup.
- `prometheusrule.yaml` — alerts (DLQ, availability, persistence, shards).
- Reference app this mirrors: `../temporal/README.md`.
- Storage class contract: `infrastructure/storage/longhorn/storageclass-wired-ha.yaml`.
- Backup architecture: `docs/domains/storage/kopiur-backup-architecture.md`.
