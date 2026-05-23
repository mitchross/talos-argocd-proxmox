# pvc-plumber v4 — audit-mode deployment

Phase 3 of [`docs/pvc-plumber-v4-prd.md`](../../../docs/pvc-plumber-v4-prd.md).

This directory deploys pvc-plumber in **audit mode only**. The operator
watches PVCs, computes the v4 expected state, and emits structured logs
+ "would-write" counters — but **does not write** any RS, RD,
ExternalSecret, or PVC mutation to the cluster.

## Status: NOT YET SYNCED — image SHA pending

The Argo Application at
[`../argocd/apps/core-dependencies/pvc-plumber-app.yaml`](../argocd/apps/core-dependencies/pvc-plumber-app.yaml)
is committed **without automated sync**. The Deployment's image reference
is a placeholder all-zero SHA digest that intentionally cannot be pulled.

To activate this deployment:

1. **Push pvc-plumber commits** `a36bf71` (Phase 2 v4 packages) + `028f376`
   (Phase 2.5 audit-mode runtime guard) to
   `github.com/mitchross/pvc-plumber`'s `main` branch.
2. **Build + push** the operator image:
   ```
   cd ../pvc-plumber
   make docker-build VERSION=v4.0.0-audit-rc1
   make docker-push  VERSION=v4.0.0-audit-rc1
   ```
3. **Record the SHA digest** that GHCR returns and replace the
   `@sha256:000…000` placeholder in `deployment.yaml`.
4. **Enable Argo automation** by uncommenting the `automated:` block in
   `pvc-plumber-app.yaml`.
5. ArgoCD will sync. The audit-mode pod starts and logs:
   ```
   pvc-plumber starting in audit mode: no cluster writes will be performed (PVC_PLUMBER_MODE="audit" via env)
   ```

## Audit-mode safety guarantees

The pvc-plumber binary in audit mode (per Phase 2.5 of the PRD) does NOT:

- Create, update, patch, or delete any `ReplicationSource`,
  `ReplicationDestination`, `ExternalSecret`, or `Secret`.
- Mutate any PVC (the auditclient wrapper blocks all writes; webhook
  handlers are not registered).
- Run admission webhooks (no `MutatingWebhookConfiguration` /
  `ValidatingWebhookConfiguration` is deployed by this directory; the
  binary skips webhook handler registration when mode is audit).
- Run leader election (forced off by main.go in audit mode — the
  coordination.k8s.io Lease writes use a path that bypasses auditclient).
- Emit Kubernetes Events (the v3.1 and v4 reconciler code paths do not
  use `EventRecorder`; verified by grep).

The audit-mode binary MAY:

- Watch, list, and get PVCs / Namespaces / RS / RD / ExternalSecrets.
- Compute the v4 expected state (decision engine, source gating).
- Compare expected vs actual — emitted via structured logs as
  `audit-mode would-write verb=create kind=ReplicationSource ns=… name=…`.
- Track per-(verb, kind) counters in memory (`WouldWriteByKind`).

## Sync wave

Wave 2. Sequenced after Wave 1 (Longhorn, snapshot-controller, VolSync
operator) but at the same level as `volsync-backup-cluster` (the MAP +
ClusterES). The two co-exist safely — pvc-plumber observes; MAP gates
mover Jobs.

## RBAC summary

Single ClusterRole `pvc-plumber:audit-reader` with **only** `get, list,
watch` verbs on:

- `persistentvolumeclaims` (core)
- `namespaces` (core)
- `replicationsources`, `replicationdestinations` (volsync.backube)
- `externalsecrets`, `clusterexternalsecrets` (external-secrets.io)

Explicitly **NOT granted**:
- Any write verbs (create/update/patch/delete) on managed resources.
- `secrets` reads.
- `coordination.k8s.io` Leases (leader election forced off in audit).
- `events.k8s.io/events` (the binary doesn't emit Events — grep'd).
- `tokenreviews` / `subjectaccessreviews` (only needed by the webhook
  auth proxy path; webhooks aren't registered in audit mode).

If startup logs ever show warnings like "unable to perform
SubjectAccessReview" or "events not allowed", add the verbs back with
proof. Defaults to maximally tight.

When Phase 5+ flips the operator to permissive/enforce, a separate
ClusterRole (`pvc-plumber:writer`, not yet authored) will be bound. This
audit role stays read-only forever.

## Verifying without deployment

Render the manifests locally:
```
kustomize build infrastructure/controllers/pvc-plumber
```

Confirm what's rendered:
- 1× Namespace
- 1× ServiceAccount
- 1× ClusterRole + 1× ClusterRoleBinding
- 1× Deployment (single replica, audit env)
- 1× Service (metrics + probes only — no admission port)
- 1× ServiceMonitor (kube-prometheus-stack scrape)
- 1× PrometheusRule (pod-down + crash-looping)
- **0× MutatingWebhookConfiguration**
- **0× ValidatingWebhookConfiguration**

## Related

- [`docs/pvc-plumber-v4-prd.md`](../../../docs/pvc-plumber-v4-prd.md) —
  full design + 12-phase rollout
- [`docs/pvc-plumber-v4-inventory.md`](../../../docs/pvc-plumber-v4-inventory.md) —
  current PVC classification (Phase 1)
- [`hack/pvc-plumber-inventory.py`](../../../hack/pvc-plumber-inventory.py) —
  inventory generator
- [`infrastructure/storage/volsync-backup-cluster/`](../../storage/volsync-backup-cluster/) —
  the MAP that coexists with pvc-plumber at Wave 2
- Operator repo: <https://github.com/mitchross/pvc-plumber>
  - Commit `a36bf71` adds the v4 internal/v4/* packages
  - Commit `028f376` adds the audit-mode runtime guard
