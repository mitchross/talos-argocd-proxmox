# pvc-plumber v4 nginx-example/storage canary incident

**Date:** 2026-05-27 → 2026-05-28
**Canary scope:** single PVC, `nginx-example/storage`
**Outcome:** stabilized on inline-Argo-owned VolSync resources; v4 operator-managed handoff
deferred to rc6.

> Companion to [`pvc-plumber-v4-cutover.md`](pvc-plumber-v4-cutover.md) (runbook),
> [`pvc-plumber-v4-prd.md`](pvc-plumber-v4-prd.md) (design contract), and
> [`pvc-plumber-v4-roadmap.md`](pvc-plumber-v4-roadmap.md) (backlog). This file is the
> single source of truth for what happened during the nginx-example/storage canary,
> what was learned, and what must land before another PVC is migrated.

---

## Summary

The `nginx-example/storage` v4 canary successfully validated several parts of the
pvc-plumber v4 adoption flow, but exposed two blocking issues before the migration
could be completed:

1. The pvc-plumber operator runtime ServiceAccount initially lacked namespace-scoped
   VolSync RS/RD write RBAC.
2. After RBAC was fixed, the operator attempted to create RS/RD with an invalid
   Kubernetes label value containing `/`, specifically `nginx-example/storage`.

The canary was stabilized by restoring the inline Argo-owned VolSync resources for
`nginx-example/storage`. Backups are back on the known-good Argo-owned RS/RD chain.
The pvc-plumber operator is now observing the PVC as `inline-argo` and emitting no
planned operations.

---

## Timeline

| Time (UTC) | Event |
|---|---|
| 2026-05-26 19:36 | rc5 operator pod started in permissive mode (`pvc-plumber-65f8b64588-ss9qj`). |
| 2026-05-26 | rc5 image pin landed in this repo as `c2bfa83b chore(pvc-plumber): bump image to permissive rc5`. CLI bundled in the image; `/pvc-plumber-adopt --help`, `plan`, and `apply --dry-run` all worked against `nginx-example/storage`. |
| 2026-05-26 | Adopt-scoped RBAC landed: `9fd038d1 chore(pvc-plumber): add canary-scoped adopt RBAC`. ServiceAccount `pvc-plumber:pvc-plumber-adopt` got namespace-scoped writes on RS/RD in `nginx-example` plus a cluster-wide namespace-reader role. The operator runtime SA `pvc-plumber:pvc-plumber` was left at audit-reader (read-only). |
| 2026-05-27 ~17:35 | Live adopt of `nginx-example/storage` via `/pvc-plumber-adopt apply` with the six `PVC_PLUMBER_DEFAULT_*` env overrides. PVC gained the three v4 labels: `pvc-plumber.io/enabled=true`, `pvc-plumber.io/manage-volsync=true`, `pvc-plumber.io/tier=daily`. SSA field manager `pvc-plumber-adopt`. No RS/RD changes. |
| 2026-05-27 | Phase 2 Git handoff commit `bf3fb925 chore(nginx): hand off storage backup to pvc-plumber` — removed inline `ReplicationSource/storage` and `ReplicationDestination/storage-dst` documents from `my-apps/development/nginx/pvc.yaml`. |
| 2026-05-27 | ComparisonError appeared on `my-apps-nginx`: PVC `spec.dataSourceRef` is immutable on Bound PVCs; live=`storage-backup` vs Git=`storage-dst` collided in Argo's server-side diff dry-run. Cache-hit compares masked it; cache-miss compares (hourly) surfaced it for ~5 min each cycle. |
| 2026-05-27 | Phase 2.5 PVC-level workaround: `73eb990e fix(nginx): opt storage PVC out of server-side apply` added `argocd.argoproj.io/sync-options: ServerSideApply=false`. Annotation took effect but was ineffective for the symptom — `compare-options: ServerSideDiff=false` is the relevant annotation, and Argo v3.4.2 honored it on cached compares but not on the first uncached compare per cycle. |
| 2026-05-27 23:55:04 | Argo selfHeal auto-synced `my-apps-nginx` (`autoHealAttemptsCount=3`) and pruned both inline `ReplicationSource/storage` and `ReplicationDestination/storage-dst`. Cluster RS+RD total dropped 56 → 54. PVC reconfigured (rv 62113009 → 62481753) but UID, phase, immutable spec preserved. |
| 2026-05-27 23:55:06 | pvc-plumber v4 reconciler observed the v4-labeled PVC with missing RS/RD; attempted to create both; **denied by RBAC**: `replicationsources.volsync.backube is forbidden: User "system:serviceaccount:pvc-plumber:pvc-plumber" cannot create resource ... in the namespace "nginx-example"`. (Same error for RD.) Operator entered controller-runtime exponential-backoff retry loop. |
| 2026-05-27 | AppSet-level compare-options workaround: `9d996aea chore(argocd): disable server-side diff for my-apps migration` added `argocd.argoproj.io/compare-options: ServerSideDiff=false` to the `my-apps` AppSet template. `ignoreApplicationDifferences` on the AppSet preserved manual per-app annotations against AppSet regeneration, so a one-time `kubectl annotate` on `my-apps-nginx` was used to bootstrap the annotation on just that one Application. ComparisonError cleared cluster-wide. |
| 2026-05-28 02:48 | Patch 7.7 landed: `8953fefd chore(pvc-plumber): add operator volsync-writer RBAC for managed namespaces`. New `ClusterRole/pvc-plumber:volsync-writer` (verbs `get,list,watch,create,patch,delete` on `volsync.backube/replicationsources` + `replicationdestinations` only; no `update`, no status subresource, no PVC/Secret/Argo/wildcard). First `RoleBinding/pvc-plumber:volsync-writer` in `nginx-example`. Managed-namespace contract codified in [cutover doc](pvc-plumber-v4-cutover.md). |
| 2026-05-28 02:57 | Manual Argo sync of `pvc-plumber` Application at `8953fefd`. ClusterRole + RoleBinding created. |
| 2026-05-28 03:03 | Inert PVC poke (`kubectl annotate pvc storage -n nginx-example pvc-plumber.io/poke-rev=8953fefd`) — adds one annotation, no spec/label change — re-enqueued the operator's reconcile work-item immediately. |
| 2026-05-28 03:03:18 | Operator reconciled. **RBAC denial gone.** New error class: `ReplicationSource.volsync.backube "storage" is invalid: metadata.labels: Invalid value: "nginx-example/storage": a valid label must be ... (regex: '(([A-Za-z0-9][-A-Za-z0-9_.]*)?[A-Za-z0-9])?')`. (Same error for RD `storage-dst`.) The operator was writing the compound `backup_identity` string into a label value, which K8s rejects because `/` is not legal in label values. |
| 2026-05-28 03:11 | Stabilization rollback committed: `6d85c630 revert(nginx): restore inline VolSync resources`. Restored both Argo-owned YAML documents to `my-apps/development/nginx/pvc.yaml` in their pre-`bf3fb925` known-good shape. v4 PVC labels left in place; per the v4 ownership contract, the operator classifies `managed-by: argocd` RS/RD as `inline-argo` and writes nothing. |
| 2026-05-28 03:17 | Manual Argo sync of `my-apps-nginx` at `6d85c630`. Required one hard-refresh cycle to invalidate the diff cache before RS/RD showed `OutOfSync`. selfHeal then applied both within seconds. RS `storage` and RD `storage-dst` materialized as Argo-owned with the exact pre-`bf3fb925` spec. |
| 2026-05-28 03:17:34 | `/audit` re-evaluated. `action: already-matches`, `owner_classification: inline-argo`, `label_source: v4`, `planned_ops: 0`, `execution_failed: null`. Operator quiescent. Cluster RS+RD total restored to **56**. |

---

## What worked

- **rc5 image rollout**: clean. Operator pod restarted with the new image, came up Running, served `/audit` from minute 0.
- **CLI binary bundled** with the operator container; `kubectl exec` invocation of `/pvc-plumber-adopt` for `plan`, `apply --dry-run`, and `apply` all worked.
- **Adopt-scoped RBAC** (`9fd038d1`): the manual CLI ServiceAccount got exactly the writes it needed; namespace-scoped, not cluster-wide.
- **Dry-run apply** correctly previewed the three PVC labels and the would-apply SSA patch with field manager `pvc-plumber-adopt`.
- **Live label apply** wrote the three v4 labels cleanly via SSA — no UID change, no spec mutation, no other label touched.
- **App-level `compare-options: ServerSideDiff=false`** (commit `9d996aea`) bypassed the immutable-PVC-spec compare failure entirely. AppSet's `ignoreApplicationDifferences` clause meant a single one-time annotate on `my-apps-nginx` was sufficient and stuck across AppSet regenerations.
- **Managed-namespace RBAC pattern** (Patch 7.7, commit `8953fefd`) is now codified: one ClusterRole, per-namespace RoleBindings, opt-in by appending one stanza. Documented in [cutover doc](pvc-plumber-v4-cutover.md#managed-namespace-contract).
- **Restoring inline RS/RD** (commit `6d85c630`) stabilized the backup chain via GitOps. No manual `kubectl create` of RS/RD was used.
- **pvc-plumber correctly observes Argo-owned inline RS/RD** and writes nothing — the v4 ownership contract held under live load. The label-value bug is **not reached** when the planner emits no create.

## What failed

### 1. Migration order bug

Inline RS/RD were removed from Git (`bf3fb925`) before the operator was proven able
to render and create *valid* replacement RS/RD. The two prerequisite gaps
(operator runtime write RBAC; operator renderer correctness) were only discovered
*after* selfHeal had already pruned the live RS/RD, putting the PVC into a no-backup
state.

**Correct future migration order — strict:**

1. **Operator code/image** must be proven to render valid RS/RD (passing K8s
   admission). This is a *unit test* requirement, not a cluster check.
2. **Operator namespace-scoped write RBAC** must exist (preflight check #1
   of the [cutover checklist](pvc-plumber-v4-cutover.md#per-pvc-cutover-checklist)).
3. **PVC v4 labels** applied via `/pvc-plumber-adopt apply` (or directly in
   `pvc.yaml`).
4. **Dry-run** verified: `/audit` reports `action: already-matches` and
   `owner_classification: managed-by-pvc-plumber` if RS/RD already exist owned
   by the operator, or `action: would-create` with zero `execution_failed` if
   they don't.
5. **Live apply** verified: operator log shows successful create; `/audit`
   flips to `already-matches`; cluster RS+RD count matches pre-canary total.
6. **Only then** remove inline RS/RD from Git.

Reversing steps 5 and 6 is exactly what produced this incident.

### 2. Missing operator RBAC

The operator runtime ServiceAccount `pvc-plumber:pvc-plumber` had only
`ClusterRole/pvc-plumber:audit-reader` (read-only, cluster-wide). It could
read PVC, RS, RD, ExternalSecret, ClusterExternalSecret. It could not
create, update, patch, or delete anything.

`9fd038d1` added RBAC for the *adopt* SA (`pvc-plumber:pvc-plumber-adopt`),
which the CLI runs as. The operator SA was not extended in the same commit
because the operator was assumed to be observe-only during the canary.
Permissive mode write paths in the v4 reconciler require write RBAC; that
mismatch produced the `forbidden` retry loop after Argo's prune.

**Fixed by Patch 7.7** (`8953fefd`):

- `ClusterRole/pvc-plumber:volsync-writer` — verbs `get, list, watch,
  create, patch, delete` on `volsync.backube/replicationsources` and
  `replicationdestinations` **only**.
- `RoleBinding/pvc-plumber:volsync-writer` per managed namespace,
  binding the ClusterRole to the operator SA.
- nginx-example is the first managed namespace.
- Explicitly NOT granted: `update`, status-subresource writes, any verb
  on PVC, Secret, ExternalSecret, Argo Application/ApplicationSet, or
  any wildcard.

### 3. pvc-plumber label rendering bug

When the operator attempted to create RS/RD with the new RBAC in place,
the API server rejected the manifests:

```
ReplicationSource.volsync.backube "storage" is invalid:
  metadata.labels: Invalid value: "nginx-example/storage":
  a valid label must be an empty string or consist of alphanumeric
  characters, '-', '_' or '.', and must start and end with an
  alphanumeric character
  (regex: '(([A-Za-z0-9][-A-Za-z0-9_.]*)?[A-Za-z0-9])?')
```

The toxic value `"nginx-example/storage"` matches the operator's `backup_identity`
field (visible in `/audit.expected.backup_identity`). The renderer in
`internal/controller/v4_reconciler.go:313` (per the stacktrace) appears to be
emitting at least one label whose value is the compound `<namespace>/<pvc>` string.
Kubernetes label values must match `(([A-Za-z0-9][-A-Za-z0-9_.]*)?[A-Za-z0-9])?` —
slash is not in the allowed character set.

**Durable fix** belongs in the pvc-plumber codebase. Recommended shape:

- Keep safe labels (each individually valid):
  - `pvc-plumber.io/source-namespace=nginx-example`
  - `pvc-plumber.io/source-pvc=storage`
  - `pvc-plumber.io/tier=daily`
- Move the compound identity to an **annotation** (annotation values have no
  `/` restriction and are not indexed):
  - `pvc-plumber.io/backup-identity: nginx-example/storage`
- Alternative: sanitize the label value (e.g., `nginx-example_storage` or
  hash-suffix). Annotation is preferred for human-readable compound identity
  and avoids losing collision-detection precision.

---

## Current safe state

| Aspect | State |
|---|---|
| `my-apps-nginx` Argo Application | `Synced`, no `ComparisonError`, `sync.revision=6d85c630` |
| `my-apps-nginx` health | `Progressing` — expected; VolSync health checks require `RS.status.lastSyncTime` and `RD.status.latestImage`. RS becomes Healthy after first scheduled backup; RD after first manual trigger. |
| PVC `nginx-example/storage` | `Bound`; UID `2f871057-9e1a-42a1-9ede-bbd071c48c56`; `spec.dataSourceRef.name=storage-backup` (immutable, unchanged); all three v4 labels still present |
| `ReplicationSource/storage` | restored; `app.kubernetes.io/managed-by=argocd`; schedule `18 2 * * *`; repo `volsync-kopia-repository`; kopia `storage@nginx-example`; mover 568/568/568 |
| `ReplicationDestination/storage-dst` | restored; `app.kubernetes.io/managed-by=argocd`; manual trigger `restore-once`; capacity `5Gi`; same kopia identity |
| pvc-plumber operator pod | `Running`, `restartCount=0`, startTime `2026-05-26T19:36:27Z` (no restart through entire incident) |
| pvc-plumber `/audit` for `nginx-example/storage` | `action=already-matches`, `owner_classification=inline-argo`, `label_source=v4`, `planned_ops=0`, `execution_failed=null` |
| Cluster-wide RS+RD count | **56** (matches pre-canary baseline) |
| Cluster-wide `managed-by=pvc-plumber` RS/RD | **0** |
| Next scheduled backup | RS `storage` cron `18 2 * * *` → next run 2026-05-29T02:18Z on the restored inline-Argo chain |

---

## What not to do next

- **Do not** migrate Karakeep yet.
- **Do not** migrate any additional PVCs.
- **Do not** remove any more inline RS/RD from Git.
- **Do not** rely on “one manual command” as the solution path. Manual commands
  belong in CI gates, runbooks, or operator code — not in tribal knowledge.
- **Do not** scale this pattern across the repo until pvc-plumber rc6 fixes the
  invalid-label-value bug and the fix is validated end-to-end on this same canary.
- **Do not** remove the v4 labels from `nginx-example/storage` unless intentionally
  rolling the PVC completely back out of v4 candidacy. Today the labels are
  inert (operator observes `inline-argo` and writes nothing) and serve as the
  durable record that this PVC is still a candidate for the eventual
  operator-managed path.

---

## Next durable fix — pvc-plumber rc6 TODO

> This belongs in the **pvc-plumber repo**, not this repo. Captured here so the
> next-session operator has the full context. Do not edit pvc-plumber code from
> this repo.

**Patch target:** pvc-plumber rc6.

**Required:**

1. **Renderer fix** in `internal/controller/v4_reconciler.go` (or wherever the
   RS/RD builder lives): no Kubernetes label value emitted by the v4 builder may
   contain `/` or any other character outside the K8s label-value regex
   `(([A-Za-z0-9][-A-Za-z0-9_.]*)?[A-Za-z0-9])?`.
2. **Identity placement**: move `backup_identity = <namespace>/<pvc>` from a
   label to an **annotation** (`pvc-plumber.io/backup-identity`). Replace the
   compound label with separate, individually valid labels:
   `pvc-plumber.io/source-namespace`, `pvc-plumber.io/source-pvc`.
3. **Unit tests**:
   - Assert every label emitted by the v4 builder matches the K8s label-value
     regex for at least one cherry-picked adversarial input
     (namespace=`nginx-example`, pvc=`storage`).
   - Regression test: `namespace=nginx-example, pvc=storage,
     backup_identity=nginx-example/storage` round-trips through the builder
     and produces RS/RD that pass `kubectl apply --validate=true --dry-run=server`.
4. **Release rc6** (image bundle in pvc-plumber repo).
5. **Bump pvc-plumber image pin** in this repo's
   `infrastructure/controllers/pvc-plumber/deployment.yaml` to rc6 (single line
   image SHA bump).
6. **Re-run nginx-example/storage handoff** from the current stabilized
   inline-Argo state — using the corrected migration order above.

---

## Lessons learned

- **The canary did its job.** It found two bad assumptions (operator runtime
  RBAC, label-value validity) before they hit Karakeep or Immich, where a
  failed handoff would have cost real backup history.
- **GitOps restore path worked.** Reverting Phase 2 via Git (commit `6d85c630`)
  re-materialized the Argo-owned RS/RD without any manual `kubectl create` or
  CLI invocation. Backups are back on the known-good chain entirely through
  the normal sync mechanism.
- **Argo-owned inline RS/RD remain a safe fallback.** The v4 ownership contract
  is intentionally tolerant of `managed-by: argocd` resources: the operator
  observes, never writes. This means rollback is always available, even
  mid-migration.
- **Managed-namespace RBAC must be a hard preflight.** Codified in
  Patch 7.7 and in the [cutover doc preflight checklist](pvc-plumber-v4-cutover.md#preflight).
  No future PVC may have inline RS/RD removed from Git until check #1
  (`kubectl get rolebinding pvc-plumber:volsync-writer -n <ns>`) returns a
  RoleBinding.
- **pvc-plumber needs a code-level validation gate before fleet migration.**
  Beyond unit tests for label-value validity, the v4 reconciler should
  ideally do a client-side dry-run apply against the API server before
  reporting `action: would-create` as "good to go". That belongs in rc7 or
  later; rc6 is scoped narrowly to the label fix.
- **Final v4 cutover docs and the visual explainer must wait** until the rc6
  canary succeeds end-to-end on this same `nginx-example/storage` PVC, with
  RS/RD ending up as `managed-by: pvc-plumber` and a first backup actually
  running. Anything documented before that point will be wrong.

---

## References

- [`pvc-plumber-v4-cutover.md`](pvc-plumber-v4-cutover.md) — operational runbook,
  managed-namespace contract, preflight checklist
- [`pvc-plumber-v4-prd.md`](pvc-plumber-v4-prd.md) — locked design contract
- [`pvc-plumber-v4-roadmap.md`](pvc-plumber-v4-roadmap.md) — post-PRD backlog,
  Patch 7.7 completion entry
- [`pvc-plumber-v4-adopt-cli-spec.md`](pvc-plumber-v4-adopt-cli-spec.md) — adopt
  CLI surface

### Important commits

| SHA | Subject |
|---|---|
| `c2bfa83b` | chore(pvc-plumber): bump image to permissive rc5 |
| `9fd038d1` | chore(pvc-plumber): add canary-scoped adopt RBAC |
| `bf3fb925` | chore(nginx): hand off storage backup to pvc-plumber |
| `73eb990e` | fix(nginx): opt storage PVC out of server-side apply |
| `9d996aea` | chore(argocd): disable server-side diff for my-apps migration |
| `8953fefd` | chore(pvc-plumber): add operator volsync-writer RBAC for managed namespaces |
| `6d85c630` | revert(nginx): restore inline VolSync resources |
