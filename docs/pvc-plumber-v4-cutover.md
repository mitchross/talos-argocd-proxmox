# pvc-plumber v4 cutover runbook

> Operational checklist for migrating apps from inline VolSync RS/RD
> to operator-managed RS/RD under the v4 permissive rollout. As of
> 2026-05-31: operator **v4.0.1**, permissive; **19 PVCs operator-managed
> across 14 namespaces** (n8n/data was the first SAVE_FOR_END migration —
> empty-dsr unlock + mover 1000→568 normalization, both validated); RBAC is a
> single cluster-wide `ClusterRoleBinding pvc-plumber:volsync-writer` (no
> per-namespace RoleBindings). Remaining work = the rest of the SAVE_FOR_END
> tier (see [migration-readiness §8](pvc-plumber-v4-migration-readiness.md)).
> (Sections below that say "rc7" / "one PVC" are historical
> implementation record; the current model is the banner above.)
> This file is the day-of operations guide. Design contract lives in the
> [PRD](pvc-plumber-v4-prd.md); the post-PRD working backlog is in the
> [roadmap](pvc-plumber-v4-roadmap.md); per-app status is in the
> [inventory](archive/pvc-plumber/inventories/pvc-plumber-v4-inventory.md). Audit-the-cluster reference is
> [`volsync-storage-recovery.md`](volsync-storage-recovery.md).

## Quick links
- [Status today](#status-today)
- [Label model](#label-model)
- [Write eligibility (two-gate)](#write-eligibility-two-gate)
- [Managed-namespace contract](#managed-namespace-contract)
- [Ownership](#ownership)
- [Generated VolSync shape](#generated-volsync-shape)
- [Required permissive defaults](#required-permissive-defaults)
- [Action verdicts and /audit output](#action-verdicts-and-audit-output)
- [Schedule minute drift](#schedule-minute-drift)
- [Per-PVC cutover checklist](#per-pvc-cutover-checklist)
- [Karakeep canary checklist](#karakeep-canary-checklist)
- [Rollback](#rollback)
- [What is NOT implemented yet](#what-is-not-implemented-yet)
- [Visual explainer backlog](#visual-explainer-backlog)
- [References](#references)

---

## Status today

**Truth-in-claims**: this section is the contract. If reality differs from
what you read here, the runbook is wrong and must be updated before
anything else.

**Live Talos cluster (this repo) right now**: pvc-plumber **rc7**, running
in **permissive** mode. Pod is Ready, restarts 0. The operator can write
operator-owned RS/RD in managed namespaces today.

**Implemented today** (rc7 on `pvc-plumber` `main`):

- permissive mode runs the v4 reconciler and the bounded executor applies
  the planner's ops (Create/Update/Delete) for write-eligible PVCs.
- rc6 fixed the invalid-label-value bug that previously broke the
  reconcile path.
- rc7 added the **ReplicationSource/ReplicationDestination watch** plus a
  child→PVC reverse-map, a self-heal requeue, a partial-inline-argo
  `needs-human-review` guard, and `/audit` `age_seconds` + `stale` per
  entry. This closes the rc6 reconcile-trigger gap: a pruned or deleted
  operator-owned (managed) RS/RD is now recreated automatically within
  ~5s, no manual PVC poke required (proven on nginx).
- bounded executor enforces a hard GVK allow-list
  (`volsync.backube/v1alpha1/ReplicationSource` and `…/ReplicationDestination`
  only) plus an ownership re-check on Update/Delete.
- `/audit` HTTP endpoint serves the parity report for any v4-routed mode
  (audit + permissive).
- permissive-mode startup requires six explicit defaults — empty
  snapshot class, ambiguous cache capacity, or `0`/root UID/GID/FSGroup
  will refuse to start.
- backups continue through the cluster-wide
  `volsync-mover-backend-availability` MutatingAdmissionPolicy
  (RustFS-availability gate scoped to mover Jobs) — that policy is the
  fail-closed substrate; pvc-plumber sits on top of it.

**First canary — COMPLETE**:

- `nginx-example/storage` migrated under rc7. Inline RS/RD removed from
  Git (commit `50a84cc9`); the operator recreated `RS/storage` and
  `RD/storage-dst` as `managed-by: pvc-plumber`; first operator-managed
  backup **Successful** at `2026-05-29T04:04:29Z`.
- Karakeep is **deferred** (destructive, separately-authorized, one-PVC,
  uses a non-568 mover so v4 would change its identity). It is **not**
  the first or next canary.
- Recommended next routine migration: `homepage-dashboard/config`
  (single 5Gi, daily, mover 568, no dataSourceRef drift). See
  [`docs/pvc-plumber-v4-migration-readiness.md`](pvc-plumber-v4-migration-readiness.md).

**Future Phase 8+** (NOT implemented today; do not infer from this runbook):

- admission webhook deployment.
- restore injection via PVC `dataSourceRef` mutation.
- strict mode (denies on stale cache / unknown truth / duplicate identity).
- enforce mode (denies on invalid config but allows unknown truth).
- automated batch app migration.
- in-binary adoption / relabeling of existing inline-Argo RS/RD.
- cluster-wide nuke + restore drill validation.

---

## Label model

The PVC is the single source of truth. Five label/annotation pieces
matter; everything else is downstream.

### `pvc-plumber.io/enabled: "true"`

The PVC's **opt-in to the v4 contract**. Carries three meanings, all at
once:

1. **Visibility / reporting**: the PVC appears in the `/audit` parity
   report. Without this label, the PVC is `skipped-not-opted-in` and
   the operator does not consider it at all (legacy `backup:` label is
   the one exception — see below).
2. **Protection intent**: future strict-mode admission would key off
   this label (`objectSelector.matchLabels.pvc-plumber.io/enabled: "true"`,
   per the [PRD](pvc-plumber-v4-prd.md) §3 rule 3). Today there is no
   webhook, but setting this label is the explicit "yes this PVC is
   v4-eligible" signal.
3. **First half of the write fuse**. By itself, `enabled` does not
   permit any operator writes — see the two-gate table below.

### `pvc-plumber.io/tier: hourly | daily | weekly | monthly | disabled`

Backup cadence or a disabled state.

- `hourly | daily | weekly | monthly` → planner emits a RS schedule
  whose minute is deterministic-hashed from `(namespace, pvc, tier)` so
  fleet load smooths out.
- `disabled` → planner emits Delete ops if operator-owned RS/RD exist
  (only with both write fuses on; see ownership).

If the tier label is missing on a v4-opted-in PVC, the planner emits
`needs-human-review` with a parser-error blocker rather than guessing.

### `pvc-plumber.io/manage-volsync: "true"`

The **write fuse**. Independent of `enabled`. When this is `"true"` AND
`enabled: "true"` is also set, the operator may Create/Update/Delete
VolSync ReplicationSource and ReplicationDestination for the PVC's v4
expected names.

When this label is missing or `"false"`, the operator may
report on the PVC (`/audit` shows it) but writes are off — verdict is
`write-gate-missing` if an expected RS/RD doesn't exist, or
`already-matches` with a note if existing inline resources already match
the expected shape.

### Legacy `backup: hourly | daily`

Pre-v4 reporting input. The operator reads it for inventory and audit
visibility but it is **never** write eligibility on its own. A PVC with
only `backup: daily` and no v4 labels lands as `write-gate-missing`
with no planned ops. Migration to v4 means adding `pvc-plumber.io/enabled`
and `pvc-plumber.io/tier` (and optionally `pvc-plumber.io/manage-volsync`)
alongside or in place of the legacy label.

The legacy label may be removed once the PVC is on v4. Leaving it
present is harmless (it stays in the reporting input but does not affect
verdicts).

### `backup-exempt: "true"` + `storage.vanillax.dev/backup-exempt-reason: "<reason>"`

Excludes the PVC from backup decisions entirely. Verdict is
`skipped-exempt`. Exempt **wins over everything** — including over
`enabled` + `manage-volsync`. If you mark a PVC exempt that previously
had operator-owned RS/RD, the planner emits no Delete ops; cleaning
the stale children is a manual operator decision, never automatic.

**Both pieces required**. The bare `backup-exempt-reason` (without the
fully-qualified `storage.vanillax.dev/` prefix) is silently ignored and
the PVC is denied on CREATE by the `backup-exempt-contract` CI job. See
the root [CLAUDE.md](../CLAUDE.md#do) for the load-bearing reason.

---

## Write eligibility (two-gate)

The operator writes nothing unless both gates are set. The legacy and
exempt rows are pinned here so an operator misreading the label model
sees the answer in one table.

| `pvc-plumber.io/enabled` | `pvc-plumber.io/manage-volsync` | legacy `backup:` | `backup-exempt: "true"` | Operator behavior |
|---|---|---|---|---|
| (any) | (any) | (any) | **set** | `skipped-exempt`. Zero writes. |
| absent | absent | absent | absent | `skipped-not-opted-in`. Zero writes. |
| absent | absent | `hourly\|daily` | absent | `write-gate-missing` (reporting visibility only). Zero writes. |
| `"true"` | absent | (any) | absent | `write-gate-missing` if no RS/RD exists; `already-matches` if inline already matches. Zero writes. |
| absent | `"true"` | (any) | absent | `skipped-not-opted-in` + blocker "manage-volsync without enabled." Zero writes. |
| `"true"` | `"true"` | (any) | absent | **Write-eligible.** Verdict depends on current state: `already-matches` / `would-create` / `would-update` / `would-delete` / `inline-argo-observed`. In permissive mode the executor applies the planner's ops; in audit mode they're recorded as Skipped in `execution_result`. |

`enabled` alone never writes. `manage-volsync` alone never writes (and
without `enabled` the PVC is treated as not-opted-in). Legacy `backup:`
alone never writes. Exempt never writes.

---

## Managed-namespace contract

> **Updated 2026-05-31 — v4.0.1 RBAC model.** The per-namespace `RoleBinding`
> model described in earlier revisions of this doc is **retired**. RBAC is now
> a **single cluster-wide `ClusterRoleBinding pvc-plumber:volsync-writer`**
> (commit `a1916d61`) that grants the operator SA RS/RD write across all
> namespaces. There is **no per-namespace RoleBinding step** in a migration.
> The per-namespace gate is now purely the **software write-gate** (the
> namespace label), enforced in the operator's reconciler.

The two-gate write fuse on the PVC is necessary but not sufficient. The
operator also has to be *allowed* to manage the namespace at all. A namespace is
**pvc-plumber managed** iff all of the following are true:

1. **Namespace software write-gate:** the namespace carries
   `pvc-plumber.io/managed-namespace: "true"`. The v4.0.1 reconciler checks this
   label and emits `skipped-namespace-not-managed` for any v4-labeled PVC in a
   namespace that lacks it — so the operator will **not** create/repair RS/RD
   there until the label is added. (RBAC is already satisfied fleet-wide by the
   cluster-wide CRB; the label is the real opt-in.)
2. Namespace carries label `volsync.backube/privileged-movers: "true"`
   so the `ClusterExternalSecret/volsync-kopia-repository` fanout
   materializes `Secret/volsync-kopia-repository` locally.
3. At least one PVC in the namespace carries the v4 two-gate write
   fuses (`pvc-plumber.io/enabled=true` AND
   `pvc-plumber.io/manage-volsync=true`).

Historical note: under the *old* per-namespace-RoleBinding model, removing
inline RS/RD before the RoleBinding existed stranded the PVC (the
`nginx-example/storage` incident, 2026-05-27). That specific failure mode is
gone now that the cluster-wide CRB covers every namespace — but the ordering
discipline below still matters because of the **software gate**: don't remove
inline RS/RD before the namespace label + PVC fuses are in place, or Argo prunes
the chain while the operator is still skipping the (not-yet-gated) PVC.

### Adding a new managed namespace

Add the gate label to the namespace's manifest in Git (no RoleBinding needed):

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: <new-namespace>
  labels:
    volsync.backube/privileged-movers: "true"
    pvc-plumber.io/managed-namespace: "true"
```

Commit + sync the app. The cluster-wide CRB already authorizes the operator;
the label opts the namespace in, and the operator begins reconciling
v4-labeled PVCs there.

### Discovery

Enumerate managed namespaces by the gate label:

```sh
kubectl get ns -l pvc-plumber.io/managed-namespace=true
# RBAC: a single cluster-wide binding (NOT per-namespace RoleBindings):
kubectl get clusterrolebinding pvc-plumber:volsync-writer
```

### RBAC contract

The `pvc-plumber:volsync-writer` ClusterRole grants the operator SA the
following verbs only, bound cluster-wide via the single
`ClusterRoleBinding pvc-plumber:volsync-writer` (subject
ServiceAccount `pvc-plumber/pvc-plumber`):

| Resource | Verbs |
|---|---|
| `volsync.backube/replicationsources` | get, list, watch, create, patch, delete |
| `volsync.backube/replicationdestinations` | get, list, watch, create, patch, delete |

Explicitly **not** granted (default-deny):

- any verb on `persistentvolumeclaims` (operator must never mutate PVCs)
- any verb on `secrets` or `external-secrets.io/externalsecrets`
- any verb on `argoproj.io/applications` or `applicationsets`
- the `update` verb on RS/RD (reconciler uses server-side Apply only;
  if a future code path requires Update, the ClusterRole must be
  amended in the same commit)
- status subresource writes on RS/RD (VolSync owns status)
- any resource other than RS/RD (the cluster-wide binding is scoped to
  exactly the two VolSync kinds above — blast radius is the RS/RD lifecycle,
  nothing else).

### Migration order — strict

For every PVC being migrated to operator ownership:

1. **Namespace gate first** (RBAC is already satisfied cluster-wide — no
   RoleBinding step): add `pvc-plumber.io/managed-namespace: "true"` to the
   namespace. Verify the cluster-wide CRB exists (preflight check (1) below).
2. **PVC fuse labels second**: `pvc-plumber.io/enabled=true` +
   `manage-volsync=true` + `tier` directly in `pvc.yaml` (the namespace label
   and the PVC fuses can land in the same handoff commit).
3. **Inline RS/RD removal third**: in that same handoff commit (or after),
   only once the gate + fuses are present so the operator can immediately adopt.

Reversing this order (removing inline RS/RD before the namespace gate + fuses)
strands the PVC: Argo prunes the inline chain while the operator is still
skipping the un-gated PVC.

---

## Ownership

The planner classifies live RS/RD by the
`app.kubernetes.io/managed-by` label on the resource.

| Live resource state | Classification | Operator may write? |
|---|---|---|
| Resource absent | `none` | **Yes**, Create — but only with both gates set. |
| `app.kubernetes.io/managed-by: pvc-plumber` | `managed-by-pvc-plumber` | **Yes** for Update/Delete — but only with both gates set, and the executor re-checks the live label before each Update/Delete (race-safety against between-plan-and-execute relabels). |
| `app.kubernetes.io/managed-by: argocd` | `inline-argo` | **No.** Verdict is `inline-argo-observed`. The planner emits zero ops; the executor refuses anything that targets one of these even if a buggy planner emitted an op. |
| Label absent but shape matches expected (same name, same repository, same source PVC) | `unmanaged-or-gitops-observed` | **No.** Treated as a GitOps-managed resource whose `managed-by` label was omitted (Helm charts often do this). Observed only. |
| Label absent and shape does NOT match | `unknown` | **No.** Verdict is `needs-human-review`. |

### No adoption in Phase 6

The operator does **not** relabel an inline-Argo or unmanaged RS/RD to
take ownership. The cutover model is:

1. Remove the inline RS/RD YAML from Git.
2. Argo deletes the inline resource (`managed-by: argocd`).
3. Operator sees no current resource at the expected name.
4. With both gates set on the PVC, operator creates a fresh RS/RD with
   `managed-by: pvc-plumber`.

Step 3 → 4 happens in the next reconcile pass after the inline delete
lands. There is no race window where the operator sees a live argo-owned
resource and patches it; the planner's `inline-argo-observed` verdict is
the safety stop.

**Exception** (future): an adoption path is on the Phase 8 roadmap. Any
resource carrying `app.kubernetes.io/managed-by: pvc-plumber` that the
operator does NOT own in-memory will be flagged for adoption then. Not
implemented today.

---

## Generated VolSync shape

Source of truth: [`internal/v4/builder/builder.go`](https://github.com/mitchross/pvc-plumber/blob/main/internal/v4/builder/builder.go).
The operator emits exactly two kinds; the executor's GVK allow-list
refuses anything else.

| Field | Value |
|---|---|
| RS name | `<pvc>` — bare PVC name verbatim, no `-backup` suffix. |
| RD name | `<pvc>-dst` — PVC name with `-dst` suffix. |
| Repository Secret | `volsync-kopia-repository` — single cluster-wide kopia repo Secret. Fanned out per-namespace by `ClusterExternalSecret/volsync-kopia-repository`. No per-PVC `volsync-<pvc>` ExternalSecret is created. |
| Namespace label requirement | The PVC's namespace MUST carry `volsync.backube/privileged-movers: "true"` so the shared kopia Secret can be materialized. Same requirement as the inline pattern documented in `my-apps/CLAUDE.md`. |
| `copyMethod` | `Snapshot`. |
| `volumeSnapshotClassName` | `pvc-plumber.io/snapshot-class` annotation override → operator default `PVC_PLUMBER_DEFAULT_SNAPSHOT_CLASS`. |
| `cacheCapacity` | `pvc-plumber.io/cache-capacity` annotation override → operator default `PVC_PLUMBER_DEFAULT_CACHE_CAPACITY`. |
| `storageClassName` | `pvc-plumber.io/storage-class` annotation override → PVC's own `spec.storageClassName` → operator default `PVC_PLUMBER_DEFAULT_STORAGE_CLASS`. |
| `moverSecurityContext.runAsUser` | `pvc-plumber.io/uid` annotation override → operator default `PVC_PLUMBER_DEFAULT_UID`. |
| `moverSecurityContext.runAsGroup` | `pvc-plumber.io/gid` annotation override → operator default `PVC_PLUMBER_DEFAULT_GID`. |
| `moverSecurityContext.fsGroup` | `pvc-plumber.io/fsgroup` annotation override → operator default `PVC_PLUMBER_DEFAULT_FSGROUP`. |
| RS `trigger.schedule` | Deterministic cron from `(namespace, pvc, tier)`. See [Schedule minute drift](#schedule-minute-drift). |
| RD `trigger.manual` | `restore-once` (matches the inline talos pattern). |
| Operator labels stamped on RS/RD | `app.kubernetes.io/managed-by: pvc-plumber`, `pvc-plumber.io/source-namespace`, `pvc-plumber.io/source-pvc`, `pvc-plumber.io/tier`, `pvc-plumber.io/backup-identity`, `volsync.backup/pvc`. |

Sample rendered RS (karakeep-flavored, for orientation):

```yaml
apiVersion: volsync.backube/v1alpha1
kind: ReplicationSource
metadata:
  namespace: karakeep
  name: data
  labels:
    app.kubernetes.io/managed-by: pvc-plumber
    pvc-plumber.io/source-namespace: karakeep
    pvc-plumber.io/source-pvc: data
    pvc-plumber.io/tier: daily
    pvc-plumber.io/backup-identity: karakeep/data
    volsync.backup/pvc: data
spec:
  sourcePVC: data
  trigger:
    schedule: "23 2 * * *"        # deterministic hash; see §schedule
  kopia:
    repository: volsync-kopia-repository
    username: karakeep
    hostname: data
    compression: zstd-fastest
    parallelism: 2
    copyMethod: Snapshot
    storageClassName: longhorn
    volumeSnapshotClassName: longhorn-snapclass
    cacheCapacity: 2Gi
    retain:
      hourly: 24
      daily: 7
      weekly: 4
      monthly: 2
    moverSecurityContext:
      runAsUser: 568
      runAsGroup: 568
      fsGroup: 568
```

The RD mirrors this with `trigger.manual: restore-once`, the same kopia
identity, and `accessModes` + `capacity` lifted from the PVC.

---

## Required permissive defaults

Permissive mode startup is gated on six environment variables. Audit
mode does not require them (the executor short-circuits before any RS/RD
body matters). Enforce / strict are rejected at startup before this
check runs (Patch 6.7-wire's `validateMode`), so the check applies only
to permissive in practice.

| Env var | Value for this cluster | Required in permissive? | Required in audit? |
|---|---|---|---|
| `PVC_PLUMBER_DEFAULT_SNAPSHOT_CLASS` | `longhorn-snapclass` | **yes** | optional |
| `PVC_PLUMBER_DEFAULT_CACHE_CAPACITY` | `2Gi` | **yes** | optional |
| `PVC_PLUMBER_DEFAULT_STORAGE_CLASS` | `longhorn` | **yes** | optional |
| `PVC_PLUMBER_DEFAULT_UID` | `568` | **yes**, must be `> 0` | optional |
| `PVC_PLUMBER_DEFAULT_GID` | `568` | **yes**, must be `> 0` | optional |
| `PVC_PLUMBER_DEFAULT_FSGROUP` | `568` | **yes**, must be `> 0` | optional |

The `> 0` rule on UID/GID/FSGroup is intentional. `0` is the explicit
"root" value, which:

- diverges from the cluster's PSA `restricted` posture,
- fights with Longhorn's mover Pod expectations,
- produces snapshots with root-owned files that won't match the running
  application's filesystem owner (the talos repo's inline pattern is
  `568:568:568` across the board),
- and creates a confusing restore — files come back with the wrong owner.

If the binary boots in permissive without all six set (or any of UID/GID/
FSGroup is missing or zero), it crashes at startup with a single
composite error listing every offending variable:

```
v4 permissive mode requires explicit defaults:
  - PVC_PLUMBER_DEFAULT_SNAPSHOT_CLASS must be set when PVC_PLUMBER_MODE=permissive
  - PVC_PLUMBER_DEFAULT_FSGROUP must be > 0 when PVC_PLUMBER_MODE=permissive (got 0; root mover security context is not supported)
  - …
```

Audit-mode pods are unaffected even with all six unset — the
`/audit` parity report still renders correctly because the executor
short-circuits before consuming default values.

---

## Action verdicts and `/audit` output

The `/audit` endpoint returns a JSON `ParityReport` with one entry per
PVC the operator observed. The `action` field on each entry is one of
nine values; the meaning is identical in audit and permissive.

| Action | Meaning | Operator response |
|---|---|---|
| `already-matches` | Expected RS/RD exist and shape matches what v4 would render. | No-op. |
| `skipped-exempt` | `backup-exempt: "true"` plus the FQ reason annotation. | Reported only. |
| `skipped-not-opted-in` | No v4 labels, no legacy `backup:` label. | Reported only. |
| `write-gate-missing` | PVC is opted in for reporting (v4 or legacy label) but the write fuse is off. Includes a `blockers` entry naming the missing label. | Reported only. |
| `would-create` | Both gates set, expected RS/RD absent. Planner emits Create ops. | In permissive: executor creates. In audit: skipped. |
| `would-update` | Both gates set, operator-owned RS/RD present, shape drifts. | In permissive: executor read-then-overwrites with planner's body. In audit: skipped. |
| `would-delete` | Both gates set, `tier: disabled`, operator-owned RS/RD present. | In permissive: executor deletes. In audit: skipped. |
| `inline-argo-observed` | Resource at the expected name carries `managed-by: argocd`. | Observed only. Operator never modifies. |
| `needs-human-review` | Malformed labels (bad tier, exempt without reason, etc.) or unknown live owner. `blockers` lists the problems. | Fix the PVC in Git. |

### `planned_ops` and `execution_result`

When the verdict is one of `would-create` / `would-update` / `would-delete`,
the entry also carries:

- `planned_ops`: compact list of `{kind, gvk, namespace, name}` so a
  reviewer can grep for `volsync.backube/v1alpha1/ReplicationSource` and
  verify the operator only targets RS/RD. Empty for non-write verdicts.
- `execution_result`: present **only when `planned_ops` is non-empty**.
  Contains `counts: {Skipped, Succeeded, Refused, Failed}` plus per-op
  `outcomes`.

Behavior matrix:

| Mode | `planned_ops` | `execution_result` |
|---|---|---|
| audit, `already-matches` | empty | omitted (skimmable /audit) |
| audit, `skipped-*` | empty | omitted |
| audit, `write-gate-missing` | empty | omitted |
| audit, `would-create` / `update` / `delete` | non-empty | included; `counts.Skipped == len(planned_ops)`, every outcome has `status: "skipped"` |
| permissive, `already-matches` | empty | omitted |
| permissive, `would-create` / `update` / `delete` | non-empty | included; `counts.Succeeded` for apiserver-accepted ops, `counts.Refused` for executor-rejected (e.g., `not-owned`, `exists`), `counts.Failed` for apiserver errors |

The executor's per-op `Err` is intentionally **not** in the `/audit` JSON
(stable schema). apiserver errors are emitted to the reconciler's
structured log instead.

---

## Schedule minute drift

The inline RS YAML in `my-apps/**` carries hand-picked cron minutes
(e.g. `57 2 * * *`, `3 2 * * *`). The v4 builder uses a deterministic
hash of `(namespace, pvc, tier)` to pick the minute so a freshly-managed
RS may report a different minute than the inline original.

- **Cadence is preserved.** Hourly → `* * * *` form; daily →
  `<min> <hour> * * *`. The slot is consistent across reconciles.
- **The minute may differ from the hand-picked inline value.** This is
  expected. Do not treat it as drift; do not file a bug.
- **Verify via `lastSyncTime`.** After cutover, watch
  `kubectl -n <ns> get rs <pvc> -o jsonpath='{.status.lastSyncTime}'`.
  As long as it advances within the tier cadence, the schedule is
  working.

The schedule itself is `string`-equal across reconciles for a given
`(ns, pvc, tier)`, so the operator does not flap the schedule field
once the resource is created.

---

## Per-PVC cutover checklist

This is the operational core of the runbook. **Run one PVC at a time**
and get explicit user authorization before each migration; batch
migration is not authorized. The first canary (`nginx-example/storage`)
is complete under rc7. The recommended next routine migration is
`homepage-dashboard/config`. Karakeep remains a deferred, separately
authorized destructive canary (see below) — it is not the first or next
migration.

Substitute `<ns>` and `<pvc>` throughout. Substitute the captured
expected RS name `<rs>` = `<pvc>` and RD name `<rd>` = `<pvc>-dst`.

### Preflight

Capture state to disk in case rollback is needed.

**rc7 note**: the RS/RD watch makes the operator recreate of a pruned or
deleted **managed** child automatic in <5s after Argo prunes the inline
resource — no manual PVC poke is needed (proven on nginx). The preflight
below still captures state for rollback, but you should not have to
manually trigger a reconcile.

```sh
mkdir -p /tmp/v4-cutover/<ns>-<pvc> && cd /tmp/v4-cutover/<ns>-<pvc>
```

- [ ] Identify the target namespace + PVC. Confirm it appears in
      [`docs/pvc-plumber-v4-inventory.md`](archive/pvc-plumber/inventories/pvc-plumber-v4-inventory.md)
      as a Phase 7 cutover candidate.
- [ ] Capture PVC YAML:
      ```sh
      kubectl -n <ns> get pvc <pvc> -o yaml > pvc.before.yaml
      ```
- [ ] Capture inline RS + RD YAML:
      ```sh
      kubectl -n <ns> get replicationsource <pvc> -o yaml > rs.before.yaml
      kubectl -n <ns> get replicationdestination <pvc>-dst -o yaml > rd.before.yaml
      ```
- [ ] Capture the current `/audit` entry for the PVC (operator pod):
      ```sh
      kubectl -n pvc-plumber port-forward svc/pvc-plumber 8080:8080 &
      curl -s localhost:8080/audit | jq '.entries[] | select(.namespace=="<ns>" and .pvc=="<pvc>")' > audit.before.json
      ```
      Expected: `action: "already-matches"`, `owner_classification: "inline-argo"`,
      `label_source: "legacy"`, `planned_ops` absent, `execution_result` absent.
- [ ] Confirm the `/audit` entry's `stale` field is `false` (rc7 added
      `age_seconds` + `stale` per entry):
      ```sh
      jq '.stale' audit.before.json
      # expect: false
      ```
      A `stale: true` entry means the operator's view of the PVC is
      behind; let it reconcile before proceeding.
- [ ] If the PVC has live `dataSourceRef` drift (Argo reports it
      OutOfSync on the `dataSourceRef` field), add
      `argocd.argoproj.io/sync-options: ServerSideApply=false` to the PVC
      in addition to the existing `ServerSideDiff=false` compare-option.
      This is the proven `nginx` mitigation for the dataSourceRef
      reconcile loop.
- [ ] Capture last successful backup time:
      ```sh
      kubectl -n <ns> get rs <pvc> -o jsonpath='{.status.lastSyncTime}'
      ```
- [ ] Verify the app is healthy. Whatever the app's specific liveness
      probe / endpoint is, confirm it's serving traffic before changing
      its backup pipeline.
- [ ] Verify the namespace carries `volsync.backube/privileged-movers: "true"`:
      ```sh
      kubectl get ns <ns> -o jsonpath='{.metadata.labels.volsync\.backube/privileged-movers}'
      ```
      Expected: `true`. If empty, this PVC is not currently being backed
      up by VolSync; the cutover is not the right tool — fix the namespace
      label first.
- [ ] Verify the shared kopia repo Secret materialized in the namespace:
      ```sh
      kubectl -n <ns> get secret volsync-kopia-repository
      ```
- [ ] Verify RBAC is in place — a **single cluster-wide** binding covers
      all namespaces (no per-namespace RoleBinding):
      ```sh
      kubectl get clusterrolebinding pvc-plumber:volsync-writer -o name
      ```
      Expected: `clusterrolebinding.rbac.authorization.k8s.io/pvc-plumber:volsync-writer`.
- [ ] Verify the namespace is **pvc-plumber managed** (the software
      write-gate that actually opts the namespace in). See the
      [managed-namespace contract](#managed-namespace-contract) above.
      ```sh
      kubectl get ns <ns> -o jsonpath='{.metadata.labels.pvc-plumber\.io/managed-namespace}'
      ```
      Expected: `true`. If empty, the cutover **must not proceed**:
      removing inline RS/RD from Git will leave Argo pruning them while the
      operator skips the un-gated PVC (`skipped-namespace-not-managed`),
      stranding the PVC without a backup chain. Add the
      `pvc-plumber.io/managed-namespace: "true"` label to the namespace
      manifest in the same handoff commit (or earlier).
- [ ] Verify the operator pod log has no recent `forbidden` errors for
      `<ns>` (sanity check that the binding above is effective):
      ```sh
      kubectl -n pvc-plumber logs deployment/pvc-plumber --since=10m \
        | grep -iE "forbidden|create-failed" | grep "<ns>" || echo "clean"
      ```
      Expected: `clean`. `kubectl auth can-i --as=` is **not** authoritative
      here — it returns false positives under cluster-admin impersonation.
      The operator pod's own log is the only reliable signal.

### Git change

Single PR. Touch only the target app's directory.

- [ ] Replace the legacy `backup: <tier>` label on the PVC with:
      ```yaml
      labels:
        pvc-plumber.io/enabled: "true"
        pvc-plumber.io/tier: <tier>            # hourly | daily | weekly | monthly
        pvc-plumber.io/manage-volsync: "true"
      ```
      Optional: remove the legacy `backup:` label entirely. Leaving it
      is harmless but adds noise.
- [ ] Remove the inline `ReplicationSource` and `ReplicationDestination`
      manifests for this PVC only. They are typically in `pvc.yaml`
      as additional YAML documents — delete those documents but leave
      the PVC document itself unchanged.
- [ ] **Do not** modify the PVC's `storageClassName`, `resources.requests.storage`,
      `accessModes`, or `dataSourceRef`. The cutover is metadata + child-resource
      only.
- [ ] **Do not** modify the app's workload (Deployment / StatefulSet /
      DaemonSet) in this PR.
- [ ] **Do not** modify any Secrets or ExternalSecrets in this PR.
- [ ] Open the PR. Title: `chore(<app>): cutover to pvc-plumber v4`.

### Sync order

- [ ] Verify pvc-plumber is healthy and in permissive mode:
      ```sh
      kubectl -n pvc-plumber get pods
      kubectl -n pvc-plumber logs -l app.kubernetes.io/name=pvc-plumber --tail=5 | head -1
      ```
      The startup banner must read "permissive mode" and the pod must
      be `Running`.
- [ ] Merge + sync the target app's ArgoCD Application. Do not sync any
      other app in the same window.
- [ ] Watch Argo delete the inline RS/RD:
      ```sh
      kubectl -n <ns> get replicationsource,replicationdestination -w
      ```
      The inline `<pvc>` RS and `<pvc>-dst` RD disappear (deletion is
      Argo's, not pvc-plumber's).
- [ ] Watch pvc-plumber create fresh RS/RD with `managed-by: pvc-plumber`:
      ```sh
      kubectl -n <ns> get replicationsource <pvc> -o jsonpath='{.metadata.labels.app\.kubernetes\.io/managed-by}'
      # expect: pvc-plumber
      kubectl -n <ns> get replicationdestination <pvc>-dst -o jsonpath='{.metadata.labels.app\.kubernetes\.io/managed-by}'
      # expect: pvc-plumber
      ```

### Post-cutover verification

- [ ] App is healthy (same liveness / endpoint check as Preflight).
- [ ] PVC is `Bound`:
      ```sh
      kubectl -n <ns> get pvc <pvc>
      ```
- [ ] Operator-owned RS + RD exist with correct names:
      ```sh
      kubectl -n <ns> get replicationsource <pvc>
      kubectl -n <ns> get replicationdestination <pvc>-dst
      ```
- [ ] Repository Secret unchanged:
      ```sh
      kubectl -n <ns> get rs <pvc> -o jsonpath='{.spec.kopia.repository}'
      # expect: volsync-kopia-repository
      ```
- [ ] No per-PVC `volsync-<pvc>` ExternalSecret created:
      ```sh
      kubectl -n <ns> get externalsecret volsync-<pvc> 2>&1
      # expect: NotFound
      ```
- [ ] `/audit` action is now `already-matches`:
      ```sh
      curl -s localhost:8080/audit | jq '.entries[] | select(.namespace=="<ns>" and .pvc=="<pvc>") | .action'
      # expect: "already-matches"
      ```
- [ ] `/audit` `owner_classification` is `managed-by-pvc-plumber`:
      ```sh
      curl -s localhost:8080/audit | jq '.entries[] | select(.namespace=="<ns>" and .pvc=="<pvc>") | .owner_classification'
      # expect: "managed-by-pvc-plumber"
      ```
- [ ] First backup tick succeeds within one tier cadence. For `tier: daily`
      that's up to 24 hours; for `tier: hourly` up to 1 hour. Watch:
      ```sh
      watch -n 30 'kubectl -n <ns> get rs <pvc> -o jsonpath="{.status.lastSyncTime}"'
      ```
      The new operator-managed RS's `lastSyncTime` must advance past the
      pre-cutover timestamp.
- [ ] `kubectl -n <ns> describe rs <pvc>` shows no error events.

If every check passes, the PVC is migrated. Move to the next PVC ONLY
after the user authorizes (see karakeep policy below).

---

## Karakeep canary checklist (DEFERRED)

Karakeep is a **deferred, separately-authorized destructive canary** — it
is **NOT** the first or next migration. The first canary
(`nginx-example/storage`) is already complete under rc7. Karakeep runs
**hourly** and uses a **non-568 mover**, so a v4 cutover would change its
backup identity; that is why it is held back for explicit, isolated
handling. Migrating karakeep requires **explicit user authorization**, is
**one PVC only**, and carries the destructive hard-stops below.

The checklist steps remain valid for when karakeep is eventually
migrated. Hard rules per repo policy (memory:
`feedback_commit_authorization` + canary scope):

- **One PVC only.** Likely target: `karakeep / data` (verify against
  the live cluster before the PR).
- **Karakeep is the only app authorized for destructive operations**
  during this cutover. The user has external backup; karakeep data loss
  is explicitly accepted as part of this canary.
- **Forbidden even for karakeep**:
  - delete the `karakeep` namespace
  - delete backup history in the RustFS object store
  - prune kopia retention manually
- **Forbidden for every other app**:
  - touch non-karakeep apps in the same PR or window
  - delete non-karakeep PVCs
  - enable webhooks
  - enable strict mode
  - enable Argo automated sync on `pvc-plumber` itself
  - run a cluster-wide nuke/restore
  - touch backup Secrets
- **Hard stop**: after the karakeep PVC migrates and the post-cutover
  verification passes, stop. Do not proceed to a second app without
  explicit user authorization.

The full per-PVC checklist above still applies. The canary additions are
just the scope/discipline constraints.

If the canary fails, fall back to [Rollback](#rollback). Capture
everything before the rollback — the failure data is the input to the
next rc.

---

## Rollback

### Per-PVC rollback (one app failed cutover)

This is the well-trodden path: the PR is merged, the operator created
its own RS/RD, but something is wrong (app misbehaving, backup not
ticking, /audit verdict unexpected).

**rc7 caveat — out-of-band delete does not stick.** Under rc7 the RS/RD
watch recreates a manually-deleted **managed** RS/RD within ~5s, so
`kubectl delete` of the operator-owned resource is **not** a rollback
step — the operator just recreates it. Rollback is pure GitOps: disarm
the operator first, then let Argo recreate the inline resources. This is
the path proven on `nginx` and documented in
[`docs/pvc-plumber-v4-migration-readiness.md`](pvc-plumber-v4-migration-readiness.md) §6.

- [ ] **Disarm the operator first** so it stops owning the child. Either
      restore the inline RS/RD documents in Git (preferred — covered by
      the next step) or flip the PVC's write fuse off so the executor
      makes no further writes for this PVC:
      ```sh
      kubectl -n <ns> label pvc <pvc> pvc-plumber.io/manage-volsync-
      ```
      With the fuse off the verdict becomes `write-gate-missing` and the
      operator will not recreate the child. (Per-PVC; other apps under
      permissive continue normally.)
- [ ] Revert the cutover PR (or push a new commit that re-adds the inline
      `ReplicationSource` + `ReplicationDestination` documents into the
      app's `pvc.yaml` from the prior commit, and restores the legacy
      `backup:` label).
- [ ] Commit + sync the target app's ArgoCD Application. Argo recreates
      the inline RS/RD with `managed-by: argocd`. Because the operator is
      disarmed (or because the resource now carries `managed-by: argocd`,
      which the planner classifies `inline-argo-observed`), it will not
      fight Argo for ownership.
- [ ] **Do not** `kubectl delete` the operator-owned RS/RD out of band —
      under rc7 the watch recreates it within ~5s unless the fuse is off
      or Git already owns the inline resource. Let GitOps converge.
- [ ] **Do not delete backup history** in the kopia repo. The PVC's
      backup lineage in the shared `volsync-kopia-repository` is keyed
      by `<namespace>/<pvc>` and is independent of which controller is
      managing the RS/RD. Future restores can still hit it.
- [ ] Verify with `/audit`: action should return to `already-matches`
      with `owner_classification: inline-argo`.

### Cluster-level rollback (the running RC itself is bad)

If the live RC produces a problem that's not specific to one PVC —
startup failures, a regression in the reconcile/watch path, etc. —
revert `deployment.yaml`'s `pvc-plumber` image digest back to the
previous known-good RC (currently **rc6** / its prior digest) via a
normal PR. The image digest is an Argo-managed manifest; revert that one
file.

The operator runs **PERMISSIVE**, so it *can* write RS/RD — this is not
an audit-mode no-write rollback. The blast radius is bounded by the
executor's safety layers, not by the mode: the GVK allow-list
(RS/RD only), the ownership re-check before every Update/Delete, the
two-gate write fuse on the PVC, the namespace software write-gate
(`pvc-plumber.io/managed-namespace`), and the cluster-wide
`ClusterRoleBinding pvc-plumber:volsync-writer` (scoped to RS/RD verbs only).
A rollback
therefore only changes which RC's executor logic is running against
**operator-owned RS/RD in managed namespaces**. No PVC, Secret, or
inline-Argo RS/RD is rewritten by the rollback.

---

## What is NOT implemented yet

Explicit list. The runbook does not cover any of these. Do not infer
from anything above that they're live.

- **No admission webhook deployed.** There is no
  MutatingWebhookConfiguration or ValidatingWebhookConfiguration owned
  by pvc-plumber today. The cluster-wide
  `volsync-mover-backend-availability` MutatingAdmissionPolicy exists
  but is unrelated to pvc-plumber (it gates VolSync mover Jobs on
  RustFS reachability).
- **No restore injection.** The operator does not mutate a PVC's
  `dataSourceRef` at admission time. Restores are still operator-driven
  via the inline `ReplicationDestination` pattern documented in
  [`my-apps/CLAUDE.md`](../my-apps/CLAUDE.md).
- **No strict mode.** `PVC_PLUMBER_MODE=strict` fails at startup with
  a Phase 8 message. Do not set it.
- **No enforce mode.** `PVC_PLUMBER_MODE=enforce` fails at startup
  identically. Do not set it.
- **No cluster nuke/restore validation.** The full DR drill (zap
  cluster, reinstall, restore every PVC) has not been validated under
  v4. Use [`docs/volsync-storage-recovery.md`](volsync-storage-recovery.md)
  as the per-PVC restore reference.
- **No adoption / relabeling.** The operator never changes an existing
  resource's `app.kubernetes.io/managed-by` label. Cutover requires
  removing inline-Argo RS/RD before the operator can take ownership.
- **No automated batch migration.** Each PVC moves via its own PR. There
  is no fleet-wide "migrate everything" command and there will not be
  one in Phase 6.
- **No global batch sync.** Argo Application sync is per-app; do not
  sync the root ApplicationSet during cutover unless every PVC in scope
  is ready (which is true approximately never during phased rollout).

---

## Visual explainer backlog

A full ELI5 markdown + interactive single-file HTML lifecycle viewer is
on the backlog as a follow-up deliverable. See
[`pvc-plumber-v4-roadmap.md`](pvc-plumber-v4-roadmap.md) item #1 for the
full scope. **Start gate**: karakeep canary complete + operator in a
known-good state. Until then this runbook is the authoritative
operational reference; the explainer is the audience-facing artifact.

---

## References

- [`pvc-plumber-v4-prd.md`](pvc-plumber-v4-prd.md) — locked design
  contract. The runbook implements the design; the PRD is the design.
- [`pvc-plumber-v4-roadmap.md`](pvc-plumber-v4-roadmap.md) — backlog
  items gated on rollout milestones.
- [`pvc-plumber-v4-inventory.md`](archive/pvc-plumber/inventories/pvc-plumber-v4-inventory.md) — per-app
  status. The single place that tracks which apps are migrated.
- [`volsync-storage-recovery.md`](volsync-storage-recovery.md) — PVC
  backup/restore reference (the existing system that v4 sits on top of).
- [`my-apps/CLAUDE.md`](../my-apps/CLAUDE.md) — inline RS/RD pattern
  (the pattern v4 replaces app-by-app).
- [`.claude/commands/add-backup.md`](../.claude/commands/add-backup.md) —
  the existing per-PVC backup workflow. After v4 cutover, this workflow
  may be retired for migrated apps; pre-cutover apps still use it.
- pvc-plumber source code (external repo, `mitchross/pvc-plumber`):
  - `internal/v4/builder/builder.go` — RS/RD rendering.
  - `internal/v4/planner/planner.go` — action verdicts.
  - `internal/v4/executor/executor.go` — bounded writes.
  - `internal/v4/runtimeconfig/config.go` — env-var contract for the
    six defaults.
  - `cmd/operator/main.go` — startup wiring (`validateMode` +
    `RequireV4WriteDefaults`).

---

## Change log

- 2026-05-29 — Cluster is rc7 / permissive. rc6 fixed the invalid-label
  bug; rc7 added the RS/RD watch closing the reconcile-trigger gap.
  `nginx-example/storage` canary complete (operator-managed, backup
  Successful `2026-05-29T04:04:29Z`). Karakeep deferred. Next routine
  candidate: `homepage-dashboard/config`.
- 2026-05-24 — Initial cutover runbook (Patch 6.8b). Reflects Phase 6
  audit + permissive code paths as of pvc-plumber commit `82f37a3`
  (Patch 6.8a, "require explicit defaults for permissive VolSync
  management"). Live Talos cluster is rc3 / audit at this writing;
  rc4 is not yet tagged. Karakeep canary is the next operational
  milestone, gated on rc4.
