# pvc-plumber v4 cutover runbook

> Operational checklist for migrating apps from inline VolSync RS/RD
> to operator-managed RS/RD under the v4 audit-then-permissive rollout.
> This file is the day-of operations guide. Design contract lives in the
> [PRD](pvc-plumber-v4-prd.md); the post-PRD working backlog is in the
> [roadmap](pvc-plumber-v4-roadmap.md); per-app status is in the
> [inventory](pvc-plumber-v4-inventory.md). Audit-the-cluster reference is
> [`volsync-storage-recovery.md`](volsync-storage-recovery.md).

## Quick links
- [Status today](#status-today)
- [Label model](#label-model)
- [Write eligibility (two-gate)](#write-eligibility-two-gate)
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

**Implemented today** (after Patches 6.5 → 6.8a, all on `pvc-plumber` `main`):

- audit mode runs the v4 reconciler with bounded planner output and
  zero cluster writes; the `auditclient` wrapper around the embedded
  controller-runtime client is a second independent layer enforcing this.
- permissive mode code path exists and routes to the v4 reconciler
  (Patch 6.7-wire). enforce / strict are rejected at startup
  (Phase 8).
- bounded executor enforces a hard GVK allow-list
  (`volsync.backube/v1alpha1/ReplicationSource` and `…/ReplicationDestination`
  only) plus an ownership re-check on Update/Delete.
- `/audit` HTTP endpoint serves the parity report for any v4-routed mode
  (audit + permissive).
- permissive-mode startup requires six explicit defaults — empty
  snapshot class, ambiguous cache capacity, or `0`/root UID/GID/FSGroup
  will refuse to start (Patch 6.8a).
- backups continue through the cluster-wide
  `volsync-mover-backend-availability` MutatingAdmissionPolicy
  (RustFS-availability gate scoped to mover Jobs) — that policy is the
  fail-closed substrate; pvc-plumber sits on top of it.

**Canary-ready once rc4 image is published and Talos is bumped**:

- karakeep destructive canary on one PVC. Hard stop after that one PVC
  per repo policy. No other app may run permissive in the same rollout.

**Future Phase 8+** (NOT implemented today; do not infer from this runbook):

- admission webhook deployment.
- restore injection via PVC `dataSourceRef` mutation.
- strict mode (denies on stale cache / unknown truth / duplicate identity).
- enforce mode (denies on invalid config but allows unknown truth).
- automated batch app migration.
- in-binary adoption / relabeling of existing inline-Argo RS/RD.
- cluster-wide nuke + restore drill validation.

**Live Talos cluster (this repo) right now**: audit mode, image pinned to
rc3 digest. Permissive cutover is gated on rc4 publishing AND the Talos
manifest update AND an intentional verification step BEFORE the canary.
See the rc4 sequence at the end of this doc.

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
until the karakeep canary is complete and the user explicitly authorizes
batch migration. Per current repo policy, karakeep is the only authorized
destructive scope.

Substitute `<ns>` and `<pvc>` throughout. Substitute the captured
expected RS name `<rs>` = `<pvc>` and RD name `<rd>` = `<pvc>-dst`.

### Preflight

Capture state to disk in case rollback is needed.

```sh
mkdir -p /tmp/v4-cutover/<ns>-<pvc> && cd /tmp/v4-cutover/<ns>-<pvc>
```

- [ ] Identify the target namespace + PVC. Confirm it appears in
      [`docs/pvc-plumber-v4-inventory.md`](pvc-plumber-v4-inventory.md)
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

## Karakeep canary checklist

This is the first PVC to migrate after rc4 lands. Hard rules per repo
policy (memory: `feedback_commit_authorization` + canary scope):

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

- [ ] Flip pvc-plumber to audit mode (or remove `manage-volsync` from
      the target PVC only). The fast option:
      ```sh
      kubectl -n <ns> label pvc <pvc> pvc-plumber.io/manage-volsync-
      ```
      Verdict immediately becomes `write-gate-missing` and the executor
      makes no further writes for this PVC. (This is per-PVC; other
      apps under permissive continue normally.)
- [ ] Revert the cutover PR (or push a new commit that re-adds the
      inline RS/RD documents and the legacy `backup:` label).
- [ ] Sync the target app's ArgoCD Application.
- [ ] After Argo recreates the inline RS/RD with `managed-by: argocd`,
      delete the operator-owned RS/RD by hand:
      ```sh
      kubectl -n <ns> delete rs <pvc> -l app.kubernetes.io/managed-by=pvc-plumber
      kubectl -n <ns> delete rd <pvc>-dst -l app.kubernetes.io/managed-by=pvc-plumber
      ```
      The label selector is the safety: it refuses to delete an
      Argo-owned resource even if you typo the name.
- [ ] **Do not delete backup history** in the kopia repo. The PVC's
      backup lineage in the shared `volsync-kopia-repository` is keyed
      by `<namespace>/<pvc>` and is independent of which controller is
      managing the RS/RD. Future restores can still hit it.
- [ ] Verify with `/audit`: action should return to `already-matches`
      with `owner_classification: inline-argo`.

### Cluster-level rollback (rc4 itself is bad)

If rc4 produces a problem that's not specific to one PVC — startup
failures, audit-mode behavior change, etc. — revert the Talos
manifest's `pvc-plumber` image digest back to rc3. The Talos repo
holds the digest as an Argo-managed manifest; revert that one file via
a normal PR.

Audit-mode pods do nothing destructive even on a bad rc, so the
rollback's blast radius is just "the operator pod goes back to the rc3
behavior set." No PVC, RS, RD, or Secret is rewritten by the rollback.

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
- [`pvc-plumber-v4-inventory.md`](pvc-plumber-v4-inventory.md) — per-app
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

- 2026-05-24 — Initial cutover runbook (Patch 6.8b). Reflects Phase 6
  audit + permissive code paths as of pvc-plumber commit `82f37a3`
  (Patch 6.8a, "require explicit defaults for permissive VolSync
  management"). Live Talos cluster is rc3 / audit at this writing;
  rc4 is not yet tagged. Karakeep canary is the next operational
  milestone, gated on rc4.
