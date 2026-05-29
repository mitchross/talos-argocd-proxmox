# pvc-plumber v4 — permissive-mode deployment (rc7 live)

Phase 6 of [`docs/pvc-plumber-v4-prd.md`](../../../docs/pvc-plumber-v4-prd.md).
Live status + migration tracking: [`docs/pvc-plumber-v4-migration-readiness.md`](../../../docs/pvc-plumber-v4-migration-readiness.md).

This directory deploys pvc-plumber in **permissive mode**
(`PVC_PLUMBER_MODE=permissive`). The operator watches PVCs **and** their
VolSync `ReplicationSource`/`ReplicationDestination`, computes the v4
expected state, and **creates/updates/deletes operator-owned RS/RD** for
PVCs that carry both write-fuse labels — in namespaces that have a
`volsync-writer` RoleBinding. It never mutates PVCs, Secrets, or
ExternalSecrets.

## Status: LIVE (synced) — rc7, permissive

Image is pinned to the immutable release digest:

```
ghcr.io/mitchross/pvc-plumber:4.0.0-permissive-rc7@sha256:091f21b1b07c4373569d38d4c8d066ceea325fdaa2e996f5ad89b0b5d02d525c
```

(multi-arch manifest list, Release run 26606509577, built from operator
commit `3c40a1f`). Pod Ready, `restartCount=0`.

The Argo Application at
[`../argocd/apps/core-dependencies/pvc-plumber-app.yaml`](../argocd/apps/core-dependencies/pvc-plumber-app.yaml)
has **automated sync DISABLED** — an image-pin bump alone does not roll the
Deployment; a deliberate manual sync is required.

> **Known cosmetic drift:** `deployment.yaml` still carries
> `pvc-plumber.io/mode: audit` LABELS (Deployment metadata line 60 + pod
> template line 78), and the audit-reader `rbac.yaml` objects carry the same
> label. The runtime mode is governed by the `PVC_PLUMBER_MODE` env var
> (`permissive`), **not** by these labels — trust the operator's startup
> banner, not the label. These are tracked as a *gated* fix in the
> migration-readiness doc §7 (editing the pod-template label rolls the pod,
> so it is applied with a deliberate sync, not as a doc-only change).

## What rc6 → rc7 fixed

- **rc6** fixed the invalid-label bug: the operator used to emit a label
  whose value was the compound `nginx-example/storage` identity, which the
  API server rejected (`/` is not a legal label-value character). rc6 moved
  backup identity to an annotation so operator RS/RD creates pass admission.
- **rc7** fixed the reconcile-**trigger** gap. rc6 made operator RS/RD
  creates valid, but the reconciler still watched PVCs **only** — so when
  Argo pruned a PVC's inline RS/RD, the PVC object never changed, no event
  fired, and the PVC sat with no backup chain (~15h on the nginx canary)
  while `/audit` served a stale `already-matches` snapshot. rc7 adds a
  `ReplicationSource`/`ReplicationDestination` watch that re-enqueues the
  owning PVC on child create/**delete**/spec-change (delete is the
  load-bearing event), plus a periodic self-heal requeue, a partial
  inline-argo needs-human-review guard, and per-entry `/audit` staleness
  (`age_seconds` + `stale`).

Full incident write-up:
[`docs/pvc-plumber-v4-nginx-canary-incident.md`](../../../docs/pvc-plumber-v4-nginx-canary-incident.md).

## Permissive-mode bounds (blast radius)

The running binary DOES write, but the writes are bounded by four
independent fuses:

1. **GVK allow-list** — the executor only ever touches
   `volsync.backube/ReplicationSource` + `ReplicationDestination`. Nothing
   else is in the write path.
2. **Two-gate write fuse** — a PVC is write-eligible only if it carries
   BOTH `pvc-plumber.io/enabled=true` AND
   `pvc-plumber.io/manage-volsync=true`.
3. **Ownership re-check** — only resources labeled
   `app.kubernetes.io/managed-by: pvc-plumber` are write-eligible. Inline
   Argo-owned RS/RD (`managed-by: argocd`) are **observed only**; a partial
   inline-argo state is escalated to needs-human-review, never overwritten.
4. **Namespace RBAC** — writes happen only in namespaces that have a
   `RoleBinding/pvc-plumber:volsync-writer`. Everywhere else the operator is
   read-only.

The binary still **never** mutates PVCs, Secrets, ExternalSecrets, or Argo
Applications under any mode. Enforce/strict are still rejected at startup
(Phase 8, not yet reached).

## Sync wave

Wave 2. Sequenced after Wave 1 (Longhorn, snapshot-controller, VolSync
operator) but at the same level as `volsync-backup-cluster` (the MAP +
ClusterES). The two co-exist safely — pvc-plumber owns the per-PVC RS/RD of
migrated PVCs; the MAP gates mover Jobs cluster-wide.

## RBAC summary

Two ClusterRoles:

- **`pvc-plumber:audit-reader`** (`rbac.yaml`) — cluster-wide
  `get, list, watch` **only**, on `persistentvolumeclaims`, `namespaces`,
  `replicationsources`, `replicationdestinations`, `externalsecrets`,
  `clusterexternalsecrets`. This role also authorizes rc7's cluster-wide
  RS/RD LIST+WATCH (the new child watch). It stays read-only forever.
- **`pvc-plumber:volsync-writer`** (`rbac-volsync-writer.yaml`, Patch 7.7) —
  `get, list, watch, create, patch, delete` on `replicationsources` +
  `replicationdestinations` **only** (no `update`, no status subresource,
  no PVC/Secret/ExternalSecret/Argo access). Bound **per managed namespace**
  via a `RoleBinding/pvc-plumber:volsync-writer`; there is no cluster-wide
  write binding.

**Managed namespaces today:** `nginx-example` only (the completed canary).
Adding a managed namespace = appending one RoleBinding stanza to
`rbac-volsync-writer.yaml`. **RBAC lands first** in any migration; inline
RS/RD removal is last.

## nginx canary (complete)

`nginx-example/storage` is the first migrated PVC. Its inline Argo-owned
RS/RD were removed from Git; the operator recreated `RS/storage` +
`RD/storage-dst` as `managed-by: pvc-plumber`, and the first
operator-managed backup succeeded **2026-05-29T04:04:29Z**. The canary is
functionally complete. The `2026-05-30T02:58Z` cron-recurrence check is an
optional, read-only follow-up — not a blocker.

## Next migration candidate

`homepage-dashboard/config` — single 5Gi PVC, daily, mover 568/568/568, no
dataSourceRef drift. Karakeep is **deferred** (destructive, explicit
per-PVC authorization only). Migration plan + ready-to-run prompt:
[`docs/pvc-plumber-v4-migration-readiness.md`](../../../docs/pvc-plumber-v4-migration-readiness.md).

## Verifying without deployment

Render the manifests locally:
```
kustomize build infrastructure/controllers/pvc-plumber
```

Confirm what's rendered:
- 1× Namespace
- 1× ServiceAccount
- `pvc-plumber:audit-reader` ClusterRole + ClusterRoleBinding (read-only)
- `pvc-plumber:volsync-writer` ClusterRole + per-namespace RoleBinding(s)
  (`rbac-volsync-writer.yaml`, Patch 7.7)
- adopt SA + canary-scoped RBAC (`rbac-adopt.yaml`)
- 1× Deployment (single replica, permissive env, no webhook server)
- 1× Service (metrics + probes + audit-http — no admission port)
- 1× ServiceMonitor (kube-prometheus-stack scrape)
- 1× PrometheusRule (pod-down + crash-looping)
- **0× MutatingWebhookConfiguration**
- **0× ValidatingWebhookConfiguration**

## Related

- [`docs/pvc-plumber-v4-prd.md`](../../../docs/pvc-plumber-v4-prd.md) —
  locked design + 12-phase rollout (design contract; see its execution
  cross-note for live status)
- [`docs/pvc-plumber-v4-cutover.md`](../../../docs/pvc-plumber-v4-cutover.md) —
  day-of cutover runbook (label model, two-gate write contract, per-PVC
  checklist, rollback)
- [`docs/pvc-plumber-v4-migration-readiness.md`](../../../docs/pvc-plumber-v4-migration-readiness.md) —
  live status, fleet readiness matrix, next-candidate plan
- [`docs/pvc-plumber-v4-nginx-canary-incident.md`](../../../docs/pvc-plumber-v4-nginx-canary-incident.md) —
  rc5/rc6 incident + rc7 resolution
- [`infrastructure/storage/volsync-backup-cluster/`](../../storage/volsync-backup-cluster/) —
  the MAP that coexists with pvc-plumber at Wave 2
- Operator repo: <https://github.com/mitchross/pvc-plumber>
