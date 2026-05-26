# pvc-plumber v4 `adopt` CLI spec

> Design spec for an operator-aware onboarding command that safely labels
> existing Bound PVCs into pvc-plumber v4 management without depending on
> Argo to apply the labels. Spec only — no code, no Git changes, no
> cluster changes. Once approved, implementation slots into the
> [v4 PRD](pvc-plumber-v4-prd.md) Phase 6 / Phase 8 boundary and lands in
> the [cutover runbook](pvc-plumber-v4-cutover.md) as the supported
> migration path for drift-affected PVCs.

## Quick links
- [Why this exists](#why-this-exists)
- [Core concept](#core-concept)
- [Non-goals](#non-goals)
- [1. User-facing commands](#1-user-facing-commands)
- [2. Inputs](#2-inputs)
- [3. Validation pipeline](#3-validation-pipeline)
- [4. Backup freshness checks](#4-backup-freshness-checks)
- [5. What adopt writes](#5-what-adopt-writes)
- [6. Handoff sequence with Git/Argo](#6-handoff-sequence-with-gitargo)
- [7. Rollback](#7-rollback)
- [8. Dry-run and output](#8-dry-run-and-output)
- [9. Safety rails](#9-safety-rails)
- [10. Implementation architecture](#10-implementation-architecture)
- [11. Tests](#11-tests)
- [12. First adopt canary plan (nginx-example/storage)](#12-first-adopt-canary-plan-nginx-examplestorage)
- [13. Open questions](#13-open-questions)

---

## Why this exists

The Phase 6 cutover model assumes the operator can move a PVC from
"inline Argo-owned RS/RD" to "pvc-plumber-managed RS/RD" by:

1. Adding the v4 labels (`pvc-plumber.io/enabled`, `tier`,
   `manage-volsync`) in Git.
2. Letting Argo apply those labels during the next sync.
3. Removing the inline RS/RD YAML in a follow-up commit.

That model breaks for any PVC where Argo cannot compute a diff — which
turns out to be every Bound PVC in this cluster.

The nginx-example/storage canary (2026-05-22 → 2026-05-23,
documented in [`pvc-plumber-v4-nginx-canary-lessons.md`](../../.mink/wiki/projects/talos-argocd-proxmox/pvc-plumber-v4-nginx-canary-lessons.md))
proved two things:

1. **Universal `dataSourceRef` drift**. Every Bound PVC across the
   cluster has live `spec.dataSourceRef.name=<pvc>-backup` (v3 chart era)
   while Git carries `<pvc>-dst` (v4 bare-dst). The field is immutable
   on Bound PVCs. Argo's server-side diff dryrun fails. Sync status
   becomes `ComparisonError` and the PVC document is never re-applied —
   so labels added in Git never reach the live PVC.
2. **Argo does not strip foreign-owned live labels** under current
   sync settings. Two confirmatory tests:
   - Clean v4-era PVC (`homepage-dashboard/config`): test label written
     by a different field manager survived natural reconcile and a
     forced full sync.
   - Drift-affected PVC (`nginx-example/storage`): test label written by
     a different field manager survived hard refresh; Argo was paralyzed
     by `ComparisonError` and never even attempted a PVC write.

Combined finding: **a CLI that writes labels live, under a dedicated
field manager, is safe.** Argo's selfHeal does not contest those labels,
and Argo's diff machinery cannot fight back on drift-affected PVCs even
if it wanted to.

That CLI is `pvc-plumber adopt`.

---

## Core concept

`pvc-plumber adopt` does **one thing**: it writes v4 metadata
(labels + optional override annotations) to a live PVC, under field
manager `pvc-plumber-adopt`, after validating that the PVC's current
inline RS/RD shape matches what the operator would have generated.

It does **not**:

- create, update, or delete any `ReplicationSource` / `ReplicationDestination`,
- mutate any PVC `spec` field,
- touch Argo `Application` resources,
- write to Git,
- delete backup data, snapshots, or PVCs,
- enable strict or enforce mode,
- bypass the cluster-wide `volsync-mover-backend-availability`
  MutatingAdmissionPolicy.

After `adopt` succeeds, the existing pvc-plumber reconciler sees both
write gates set and proceeds through normal planner/executor rules. RS/RD
ownership transitions to `managed-by: pvc-plumber` only when the inline
Argo-owned RS/RD are removed from Git (a separate operator step) and
Argo prunes them. Until then, the planner emits `inline-argo-observed`
and no writes happen — exactly the Phase 6 semantics already documented
in the cutover runbook.

This addresses the previous failure mode directly: labels go on first,
inline RS/RD come off second, the operator takes over third. The
ordering matters because labels in Git can't land on drift-affected
PVCs at all — but live label writes can.

---

## Non-goals

- **Not** a generic relabel tool. The CLI's only write target is
  pvc-plumber v4 metadata.
- **Not** a replacement for Git as source of truth. `adopt` is a bridge
  for the Bound-PVC drift window. Labels SHOULD also be committed to Git
  (see §6) so the contract is visible to future operators; the CLI emits
  the suggested patch but never writes Git itself.
- **Not** the long-term solution. A `BackupIntent` CRD (or equivalent)
  is the right destination, where backup policy is a first-class object
  separate from PVC metadata. `adopt` is the explicit short-term bridge.
- **Not** a destructive recovery tool. `adopt undo` removes labels only.
  Restoring inline RS/RD is a Git/Argo operation, not a CLI operation.

---

## 1. User-facing commands

```
pvc-plumber adopt pvc <namespace>/<pvc-name> [flags]
pvc-plumber adopt undo <namespace>/<pvc-name> [flags]
pvc-plumber adopt status <namespace>/<pvc-name>
```

**v1 surface** (single PVC only):

| Command | Purpose |
|---|---|
| `adopt pvc <ns>/<pvc> --tier daily` | Validate + write labels live. |
| `adopt pvc <ns>/<pvc> --tier daily --dry-run` | Validate + render plan. No writes. |
| `adopt pvc <ns>/<pvc> --tier daily --diff` | Show shape diff between current inline RS/RD and expected v4 shape. No writes. |
| `adopt pvc <ns>/<pvc> --tier daily --emit-git-patch` | Print a YAML patch the operator can apply to the PVC's Git manifest. No writes. |
| `adopt pvc <ns>/<pvc> --tier hourly --uid 1001 --gid 1001 --fs-group 1001` | Same, with non-default UID/GID override (karakeep shape). |
| `adopt pvc <ns>/<pvc> --tier daily --force` | Override soft blockers. Hard blockers (system namespace, exempt, unknown owner) are never overridable. |
| `adopt undo <ns>/<pvc>` | Remove pvc-plumber-owned labels. Restoring inline RS/RD is a separate Git step. |
| `adopt status <ns>/<pvc>` | Read-only summary: current labels, current RS/RD shape vs expected, latest backup, planner verdict simulation. |

**v2 surface** (deferred):

```
pvc-plumber adopt batch --selector <label-selector>
pvc-plumber adopt batch --file adopt-plan.yaml
```

Batch adoption is explicitly out of scope for v1. Per-PVC adoption gives
the operator a forced human moment to verify shape, freshness, and tier
selection. Batch is dangerous until status reporting and freshness
gating are battle-tested.

---

## 2. Inputs

### Required
| Flag | Type | Notes |
|---|---|---|
| `<namespace>/<pvc>` positional | string | Must resolve to a Bound PVC. |
| `--tier` | enum | `hourly` / `daily` / `weekly` / `monthly` / `disabled`. No default — explicit per-PVC choice. |

### Optional overrides
| Flag | Default | Maps to annotation |
|---|---|---|
| `--uid` | `PVC_PLUMBER_DEFAULT_UID` (568) | `pvc-plumber.io/uid` |
| `--gid` | `PVC_PLUMBER_DEFAULT_GID` (568) | `pvc-plumber.io/gid` |
| `--fs-group` | `PVC_PLUMBER_DEFAULT_FSGROUP` (568) | `pvc-plumber.io/fsgroup` |
| `--snapshot-class` | `PVC_PLUMBER_DEFAULT_SNAPSHOT_CLASS` (`longhorn-snapclass`) | `pvc-plumber.io/snapshot-class` |
| `--cache-capacity` | `PVC_PLUMBER_DEFAULT_CACHE_CAPACITY` (`2Gi`) | `pvc-plumber.io/cache-capacity` |
| `--storage-class` | PVC's own `spec.storageClassName` → `PVC_PLUMBER_DEFAULT_STORAGE_CLASS` (`longhorn`) | `pvc-plumber.io/storage-class` |
| `--repo-secret` | `volsync-kopia-repository` | Validated against current RS, not written; future override would be a new annotation. |
| `--naming-strategy` | `bare-dst` | `bare-dst` is the only v4-supported strategy. v3 `-backup` suffix is rejected. Flag exists for future-proofing only. |

**Override-only emission rule**: optional annotations are only written if
the value differs from the operator default. This keeps the live PVC
metadata clean and matches how the cutover runbook describes the
override contract — annotations are exceptions, not defaults.

### Behavior flags
| Flag | Default | Effect |
|---|---|---|
| `--dry-run` | `false` | Run full validation pipeline + render plan. No cluster writes. Exit non-zero if validation fails. |
| `--diff` | `false` | Print shape diff: current inline RS/RD vs expected v4-rendered RS/RD. Includes operator default expansion. |
| `--emit-git-patch` | `false` | Print a YAML snippet the operator can paste into the PVC's Git manifest (labels only). Stdout, never written. |
| `--field-manager` | `pvc-plumber-adopt` | Override only for testing. Real adoptions use the default. |
| `--output` | `table` | `table` / `yaml` / `json`. JSON is the machine-readable form. |
| `--yes` / `-y` | `false` | Skip interactive confirmation. Required in Job mode. |
| `--force` | `false` | Override soft blockers (see §3). Never overrides hard blockers. |
| `--allow-stale-backup` | `false` | Override `BLOCKED_BACKUP_STALE` only. Logged at WARN. |
| `--allow-no-successful-backup` | `false` | Override "no lastSyncTime ever" only. Logged at ERROR. Pairs with `--force`. |

---

## 3. Validation pipeline

`adopt` runs every check before any write. Validation is the entire
safety surface — a bad write means the next reconcile may create or
delete VolSync resources based on a bad shape assumption.

### PVC checks
| Check | Blocker class |
|---|---|
| PVC exists in namespace | hard |
| PVC `status.phase == Bound` | hard |
| Namespace is not in the system-ns deny-list (`kube-system`, `kube-public`, `kube-node-lease`, `volsync-system`, `argocd`, `longhorn-system`, `pvc-plumber-system`) | hard, never overridable |
| PVC does not carry `backup-exempt: "true"` | hard, never overridable in v1 |
| PVC's namespace carries `volsync.backube/privileged-movers: "true"` | hard (without this, the `ClusterExternalSecret` will not materialize the shared kopia Secret) |
| PVC's `spec.storageClassName` is readable | soft (informational) |
| PVC's `spec.accessModes` and `spec.resources` are readable | soft |
| `spec.dataSourceRef` matches expected `<pvc>-dst` | **soft** — reported as drift but explicitly **not** a blocker. This is the whole point of the CLI. |
| PVC is not already adopted (both v4 gates already set) | soft → returns `ALREADY_ADOPTED` and exits 0 unless `--force` |

### Inline VolSync shape checks

For each of `ReplicationSource/<pvc>` and `ReplicationDestination/<pvc>-dst`:

| Check | Blocker class |
|---|---|
| Resource exists (RS) | soft — absence is OK if planner verdict will be `none` (no current resource). Reported. |
| Resource exists (RD) | soft, same. |
| Owner is `managed-by: argocd`, `managed-by: Helm`, no `managed-by` label, OR `managed-by: pvc-plumber` (already-adopted) | hard if owner is unknown / any other value |
| Repository Secret name | hard if mismatch (default `volsync-kopia-repository`; only overridden via future `--repo-secret`) |
| `kopia.username` matches PVC name | hard if mismatch |
| `kopia.hostname` matches namespace | hard if mismatch |
| `sourceIdentity` matches expected `<namespace>/<pvc>` (when present) | hard if mismatch |
| `copyMethod: Snapshot` | hard if mismatch |
| `volumeSnapshotClassName` matches `--snapshot-class` or operator default | soft (annotation override would resolve) |
| `cacheCapacity` matches `--cache-capacity` or operator default | soft (annotation override would resolve) |
| `storageClassName` matches `--storage-class` or PVC's own SC | soft (annotation override would resolve) |
| `accessModes` and `capacity` on the cache match PVC's | soft (logged as informational diff) |
| `retain` policy matches expected for the chosen tier | soft (will be normalized by operator after takeover) |
| `compression: zstd-fastest` and `parallelism: 2` | soft (operator default; logged as diff) |
| `moverSecurityContext.runAsUser/runAsGroup/fsGroup` match `--uid/--gid/--fs-group` or operator defaults | **hard if mismatch and no override flag supplied**. The mover identity is data-integrity-critical. |

### Backup-state checks
See §4. These produce `BLOCKED_BACKUP_STALE` /
`BLOCKED_NO_SUCCESSFUL_BACKUP` if applicable.

### Result classes

| Class | Meaning | Adopt action |
|---|---|---|
| `PASS_SAFE_TO_ADOPT` | All checks green. Shape matches expected exactly. | Writes labels (live mode) or prints plan (dry-run). |
| `PASS_WITH_WARNINGS` | Soft-only diffs (e.g. cache capacity differs from default). | Writes labels + suggests annotations. `--diff` prints the deltas. |
| `BLOCKED_SHAPE_MISMATCH` | One or more hard shape mismatches. | Refuse. `--force` is the only override and only for explicitly listed soft-promoted blockers. |
| `BLOCKED_OWNER_UNKNOWN` | RS or RD has `managed-by` value the operator does not understand. | Refuse. Never overridable. |
| `BLOCKED_BACKUP_STALE` | Latest `lastSyncTime` is older than tier's freshness window. | Refuse unless `--allow-stale-backup`. |
| `BLOCKED_NO_SUCCESSFUL_BACKUP` | RS exists but `lastSyncTime` is unset. | Refuse unless `--allow-no-successful-backup --force`. |
| `BLOCKED_UID_MISMATCH` | Mover UID/GID/FSGroup differs from default and no override flag supplied. | Refuse. Operator must pass explicit `--uid/--gid/--fs-group`. |
| `BLOCKED_REPO_MISMATCH` | Repository Secret name differs from `--repo-secret` (default `volsync-kopia-repository`). | Refuse. Hard block — the wrong repo means the wrong backup history. |
| `BLOCKED_SYSTEM_NAMESPACE` | PVC is in a deny-listed namespace. | Refuse. Never overridable. |
| `BLOCKED_EXEMPT` | PVC carries `backup-exempt: "true"` with the FQ reason annotation. | Refuse. Never overridable in v1. |
| `BLOCKED_MISSING_PRIVILEGED_MOVERS` | Namespace lacks `volsync.backube/privileged-movers: "true"`. | Refuse with remediation hint. |
| `ALREADY_ADOPTED` | Both v4 gates are already set live. | Exit 0. Idempotent. `--force` re-writes the override annotations only. |

`--force` semantics: `--force` ONLY promotes specific soft blockers to
pass. It never overrides the hard blockers labeled "never overridable"
in the tables above. The `--force` log line lists exactly which soft
blockers it bypassed.

---

## 4. Backup freshness checks

The CLI refuses to adopt a PVC whose backup chain is broken, on the
principle that an adopted PVC should have a known-good lineage before
the operator takes over. A stale or never-successful backup means the
operator may be inheriting a silent data-loss condition.

### Freshness windows by tier
| Tier | Maximum age of `latestMoverStatus.lastSyncTime` | Allow-stale flag |
|---|---|---|
| `hourly` | 3 hours | `--allow-stale-backup` |
| `daily` | 48 hours | `--allow-stale-backup` |
| `weekly` | 9 days (1.3× cadence) | `--allow-stale-backup` |
| `monthly` | 35 days (1.15× cadence) | `--allow-stale-backup` |
| `disabled` | — | Skipped (no backup expected). |

### Never-successful gate
If `latestMoverStatus.lastSyncTime` is empty (no successful backup
**ever**), adopt refuses unless **both** `--allow-no-successful-backup`
and `--force` are supplied. Adopting a never-backed-up PVC is the
highest-risk operation in the CLI; double-flag forces the operator to
intend it.

### Backup-availability gate
The cluster-wide `volsync-mover-backend-availability`
MutatingAdmissionPolicy is **not** evaluated by `adopt`. That policy is
the substrate fail-closed gate — backups can't run against a black-holed
RustFS regardless of what the CLI does. The CLI only checks past
freshness; the MAP guarantees future correctness.

---

## 5. What `adopt` writes

### Labels (always written on success)
```yaml
metadata:
  labels:
    pvc-plumber.io/enabled: "true"
    pvc-plumber.io/tier: "<tier>"
    pvc-plumber.io/manage-volsync: "true"
```

These are the canonical v4 two-gate write fuse. Once both `enabled` and
`manage-volsync` are present alongside a valid `tier`, the operator
plans and executes per normal v4 rules.

### Annotations (written only when override-needed)
```yaml
metadata:
  annotations:
    pvc-plumber.io/uid: "<value>"           # only if --uid != default
    pvc-plumber.io/gid: "<value>"           # only if --gid != default
    pvc-plumber.io/fsgroup: "<value>"       # only if --fs-group != default
    pvc-plumber.io/snapshot-class: "<v>"    # only if --snapshot-class != default
    pvc-plumber.io/cache-capacity: "<v>"    # only if --cache-capacity != default
    pvc-plumber.io/storage-class: "<v>"     # only if --storage-class != PVC default
```

### Write mechanism

- **Strategic Merge Patch (preferred)** with field manager
  `pvc-plumber-adopt`. SMP is sufficient for adding labels and
  annotations and avoids the SSA "force-conflict-on-foreign-owned-fields"
  complexity for v1.
- Alternative: Server-Side Apply with `fieldManager: pvc-plumber-adopt`
  and `force: false`. Tested viable in both selfHeal tests; harder to
  reason about for operators reading `kubectl get pvc -o yaml` because
  field managers are not visible in the default output.
- **Final v1 choice**: SMP. Simpler, deterministic, no conflict surface,
  and the selfHeal tests proved Argo doesn't strip foreign labels under
  either patch mode.

### What `adopt` MUST NOT write
| Forbidden | Reason |
|---|---|
| PVC `spec.*` (any field) | Spec is Git-owned and many fields are immutable on Bound PVCs. |
| PVC `spec.dataSourceRef` / `spec.dataSource` | Immutable on Bound PVCs; this is the universal drift field. |
| PVC `spec.volumeName` | Immutable. |
| PVC `spec.resources` | Resize is Longhorn-controlled, not CLI-controlled. |
| `ReplicationSource` / `ReplicationDestination` (any field) | Reconciler-only. Adopt is metadata-only by design. |
| Secrets / ExternalSecrets | The `ClusterExternalSecret` fanout owns this. |
| ArgoCD `Application` resources | Argo's domain. |
| Backup data / VolumeSnapshots / Kopia history | Never. |
| Foreign-owned labels (anything not in the v4 label set) | Field-manager scoped to v4 keys only. |

---

## 6. Handoff sequence with Git/Argo

The cutover sequence has nine steps and is the canonical "Phase 6 with
adopt" runbook. It supersedes the
[current Phase 6 per-PVC cutover checklist](pvc-plumber-v4-cutover.md#per-pvc-cutover-checklist)
for drift-affected PVCs (which is all of them).

### Step-by-step

1. **Dry-run adopt**.
   ```
   pvc-plumber adopt pvc <ns>/<pvc> --tier <t> --dry-run --diff
   ```
   Review validation result + shape diff. Resolve all hard blockers
   before continuing. Capture the `--emit-git-patch` output for step 5.

2. **Live adopt**.
   ```
   pvc-plumber adopt pvc <ns>/<pvc> --tier <t> --yes
   ```
   Writes labels live. Idempotent — re-running is a no-op once
   `PASS_SAFE_TO_ADOPT`.

3. **Verify gates**.
   ```
   kubectl get pvc <pvc> -n <ns> -o jsonpath='{.metadata.labels}'
   curl <pvc-plumber>/audit?ns=<ns>&pvc=<pvc>
   ```
   Confirm `/audit` shows the verdict transitioning from
   `skipped-not-opted-in` to `inline-argo-observed`. The latter is the
   correct steady state **while inline RS/RD still exist**. Zero writes.

4. **Commit Git PR — labels in Git**.
   Add the v4 labels to the PVC manifest in Git so Git and live match.
   This is documentation / defense-in-depth: if Argo ever does manage to
   apply the PVC document, it will not strip our labels. The PR contains
   **labels only**, not RS/RD deletions.

5. **Commit Git PR — remove inline RS/RD**.
   Separate commit. Delete the inline `ReplicationSource` and
   `ReplicationDestination` documents from the PVC's manifest.

6. **Argo syncs the app**. Argo prunes the inline RS/RD because they no
   longer exist in Git. The PVC document still fails its dry-run because
   of `dataSourceRef` drift — but that does not block RS/RD pruning,
   which doesn't depend on PVC apply success.

7. **Operator takes over**. Next reconcile sees:
   - Both gates set on the PVC.
   - No `ReplicationSource/<pvc>` and no `ReplicationDestination/<pvc>-dst`.
   - Planner verdict: `would-create` (audit) or `created` (permissive).
   In permissive mode, the executor creates RS/RD with
   `app.kubernetes.io/managed-by: pvc-plumber`.

8. **Audit steady state**. `/audit` shows `already-matches`, owner
   `managed-by-pvc-plumber`. Schedule cron stable (deterministic from
   `(ns, pvc, tier)`).

9. **Verify next backup tick**. Within one tier cadence (e.g. 24 hours
   for `daily`), confirm `lastSyncTime` advances on the operator-owned
   RS. Until that tick, the operator has not yet "earned" the takeover
   from a data-integrity standpoint.

### Why adopt does not create RS/RD itself

Two reasons:

1. **Avoids dual-write race**. While inline Argo-owned RS/RD exist, a
   CLI that also creates RS/RD would either fight Argo over ownership or
   require the CLI to relabel the existing RS/RD — which is exactly the
   "adoption of inline-Argo-owned resources" path the PRD explicitly
   pushes to Phase 8.
2. **Keeps planner authority**. The v4 planner's
   `inline-argo-observed` verdict is the safety stop. Letting the
   reconciler discover the RS/RD-missing state naturally is simpler and
   stays inside the existing audit/permissive gate.

The CLI's job ends at "labels live." Everything after that is the
existing reconciler doing exactly what it already does.

---

## 7. Rollback

### Goal
Return the PVC to "inline Argo-owned RS/RD" state. The CLI handles
half of this (label removal). The Git PR handles the other half
(restore inline RS/RD).

### Steps

1. **Stop future writes first**.
   ```
   pvc-plumber adopt undo <ns>/<pvc>
   ```
   Removes `pvc-plumber.io/manage-volsync` first (closes the write
   fuse), then `pvc-plumber.io/enabled` and `pvc-plumber.io/tier`. Any
   override annotations written by `adopt` are also removed.
   **Does not touch** non-pvc-plumber labels.

2. **Restore inline RS/RD in Git**. If they were deleted in step 5 of
   adopt, revert that commit. The labels-in-Git commit (step 4 of adopt)
   should also be reverted so Git matches the post-undo live state.

3. **Sync the app**. Argo recreates inline RS/RD with
   `managed-by: argocd`.

4. **Delete operator-owned RS/RD if any**. If the operator already
   created `managed-by: pvc-plumber` RS/RD (steps 6-7 of adopt
   completed), the operator will see the inline-argo RS/RD recreate and
   emit `inline-argo-observed` — but it will not delete its own
   resources. The operator does NOT manage rollback. The CLI does:
   ```
   pvc-plumber adopt rollback-cleanup <ns>/<pvc>
   ```
   This is an explicit step that deletes only resources carrying
   `managed-by: pvc-plumber` AND `pvc-plumber.io/source-pvc: <pvc>`.
   Refuses if both inline and operator-owned RS/RD exist with different
   shapes — that's a state the operator must resolve manually.

### Forbidden during rollback
- Do not delete the PVC.
- Do not delete VolumeSnapshots.
- Do not prune Kopia history.
- Do not touch backup data on RustFS.
- Do not modify the `ClusterExternalSecret` or per-namespace
  `volsync-kopia-repository` Secret.

### `undo` write contract
`undo` uses the same `pvc-plumber-adopt` field manager. SMP with
`null`-value labels to remove them. Verifies field-manager ownership
before each delete: only removes labels/annotations the CLI wrote
itself. If a label key is present but a different field manager owns it,
`undo` reports it and skips — never silently strip operator state.

---

## 8. Dry-run and output

### Dry-run shape

```
$ pvc-plumber adopt pvc nginx-example/storage --tier daily --dry-run --diff

=== Adopt plan: nginx-example/storage ===
verdict:          PASS_WITH_WARNINGS
field-manager:    pvc-plumber-adopt
tier:             daily

PVC summary:
  storageClass:    longhorn
  accessModes:     [ReadWriteOnce]
  capacity:        10Gi
  bound:           true
  dataSourceRef:   storage-backup  (DRIFT — expected storage-dst, NOT a blocker)
  exempt:          false
  namespace privileged-movers: true

Current RS/RD:
  ReplicationSource/storage      owner: argocd       shape: matches expected
  ReplicationDestination/storage-dst  owner: argocd  shape: matches expected
  Last backup:    2026-05-23T02:19:38Z  (age 4h12m, fresh for tier=daily)

Expected v4 RS/RD (post-takeover, for reference only):
  RS name:        storage
  RD name:        storage-dst
  repository:     volsync-kopia-repository
  username:       storage
  hostname:       nginx-example
  copyMethod:     Snapshot
  snapshotClass:  longhorn-snapclass     (default)
  cacheCapacity:  2Gi                    (default)
  storageClass:   longhorn               (PVC default)
  mover UID/GID/fsGroup: 568/568/568     (default)
  schedule:       18 2 * * *             (deterministic)
  retain:         24h / 7d / 4w / 2m     (default)

Soft warnings:
  - schedule will be regenerated from (ns, pvc, tier) hash. Minute drift
    from current cron `18 2 * * *` is at most one cadence cycle.

Labels/annotations to write:
  labels:
    pvc-plumber.io/enabled: "true"
    pvc-plumber.io/tier: "daily"
    pvc-plumber.io/manage-volsync: "true"
  annotations: (none — all overrides match defaults)

Equivalent kubectl command:
  kubectl label pvc storage -n nginx-example \
    --field-manager=pvc-plumber-adopt \
    pvc-plumber.io/enabled=true \
    pvc-plumber.io/tier=daily \
    pvc-plumber.io/manage-volsync=true

Suggested Git patch (for documentation):
  --- a/my-apps/development/nginx/pvc.yaml
  +++ b/my-apps/development/nginx/pvc.yaml
  @@ metadata.labels @@
  +    pvc-plumber.io/enabled: "true"
  +    pvc-plumber.io/tier: "daily"
  +    pvc-plumber.io/manage-volsync: "true"

Next steps:
  1. Re-run without --dry-run to write live.
  2. Verify /audit shows verdict transition to inline-argo-observed.
  3. Commit Git PR with labels above (defense-in-depth).
  4. Commit Git PR removing inline RS/RD.
  5. Wait for one reconcile pass; verify operator-owned RS/RD appear.
  6. Verify next backup tick.

Exit code: 0 (dry-run success, would-write)
```

### JSON output (`--output json`)

Machine-readable equivalent for automation. Includes every field above
plus structured `verdict`, `result_class`, `warnings`, `blockers`,
`would_write`, and `next_steps` arrays.

### Logging

| Level | Used for |
|---|---|
| DEBUG | Each validation check pass/fail with reason |
| INFO | Plan summary, write success |
| WARN | Soft warnings, override flags used |
| ERROR | Hard blockers, write failures |

INFO is the default level. WARN/ERROR always go to stderr.

---

## 9. Safety rails

These are absolute and cannot be flagged off:

| Rail | Behavior |
|---|---|
| **Refuse system namespaces** | Hard blocker. No flag. |
| **Refuse exempt PVCs** | Hard blocker in v1. `--force-exempt` is explicitly **not** in the v1 flag surface. |
| **Refuse unknown owners** | Hard blocker. No flag. |
| **Refuse shape mismatch beyond soft** | Hard blocker. `--force` only promotes specific soft blockers, never owner / UID / repo mismatches. |
| **Refuse stale backups by default** | Soft blocker, `--allow-stale-backup` overrides. |
| **Refuse never-backed-up by default** | Soft blocker requiring **two flags** (`--allow-no-successful-backup --force`) to override. |
| **Refuse missing tier** | Hard blocker. No default — explicit operator decision. |
| **Refuse UID/GID mismatch without override** | Hard blocker. Operator must pass explicit flag values. |
| **Refuse if already adopted (no force)** | Returns `ALREADY_ADOPTED` exit 0. Re-adoption only with `--force` and only updates override annotations. |
| **Never mutate RS/RD** | Hard rule. Enforced by the executor wrapper — adopt code path has no RS/RD client at all. |
| **Never delete anything** | Hard rule. `adopt` has no delete verb. `undo` deletes labels only via SMP `null` patch. |
| **Never prune backup history** | Hard rule. No code path touches Kopia / RustFS. |
| **Never patch Argo Applications** | Hard rule. No code path touches `argoproj.io/v1alpha1`. |
| **Refuse if `audit` mode is forced via env** | The CLI runs from outside the operator pod, but should refuse if it can't reach the operator's audit endpoint to confirm steady state. Soft warning only — the CLI can run without the operator running. |

---

## 10. Implementation architecture

### Code layout (pvc-plumber repo, separate from this Talos repo)

```
pvc-plumber/
├── cmd/
│   └── pvc-plumber/
│       └── main.go              # already exists; adds `adopt` subcommand tree
├── internal/
│   ├── v4/
│   │   ├── adopt/               # NEW
│   │   │   ├── adopt.go         # entrypoint, flag parsing, exit codes
│   │   │   ├── validate.go      # validation pipeline (PVC, RS/RD, freshness)
│   │   │   ├── plan.go          # build the write plan
│   │   │   ├── write.go         # SMP patch with field-manager
│   │   │   ├── undo.go          # remove labels (mirrors write.go)
│   │   │   ├── output.go        # table/yaml/json renderers
│   │   │   └── diff.go          # shape diff: current RS/RD vs expected
│   │   ├── builder/             # EXISTS — reused for expected-shape rendering
│   │   ├── planner/             # EXISTS — borrows verdict logic
│   │   └── labels/              # EXISTS — canonical key constants reused
│   └── client/
│       └── kubeclient.go        # NEW thin wrapper around client-go for the CLI
```

### Reuse from the existing operator code

- **`internal/v4/builder`** is the source of truth for "what does the
  expected v4 RS/RD look like?" The CLI calls the same builder
  functions with the PVC + override flags as input so the diff is
  byte-identical to what the reconciler would create.
- **`internal/v4/labels`** owns the canonical label/annotation key
  constants. The CLI imports them, never duplicates strings.
- **`internal/v4/planner`** owns the owner classification rules
  (`inline-argo` vs `unmanaged-or-gitops-observed` vs
  `managed-by-pvc-plumber` vs `unknown`). The CLI reuses the same
  classifier so adopt's "owner" verdict matches `/audit` verbatim.
- **Permissive defaults env vars** (`PVC_PLUMBER_DEFAULT_*`) are read
  from the same loader. CLI failure to find them = fail-closed startup,
  same as the operator.

### Delivery: same binary, subcommand

**Recommendation: A — embed `adopt` as a subcommand in the existing
`pvc-plumber` binary.**

Rationale:
- Reuses the existing image. No new build pipeline, no new SBOM.
- One image to pin and rotate. The same SHA the operator runs is the
  same SHA `adopt` runs as.
- Operator-aware code paths (planner, builder, labels) are direct
  imports, not vendored copies.
- Runs as a one-shot Job or interactively with `kubectl run`:
  ```
  kubectl -n pvc-plumber-system run pvc-plumber-adopt-<short> \
    --rm -i --tty \
    --image=ghcr.io/mitchross/pvc-plumber:4.0.0-permissive-rc4@sha256:... \
    --serviceaccount=pvc-plumber-adopt \
    --restart=Never \
    --command -- /pvc-plumber adopt pvc <ns>/<pvc> --tier <t> --yes
  ```
- A dedicated `pvc-plumber-adopt` ServiceAccount has the minimal RBAC
  needed: `patch pvc`, `get pvc`, `get rs`, `get rd`, `get secret`,
  `list namespaces`. No write access to RS/RD or Secrets.

Rejected alternatives:
- **B — separate `pvc-plumberctl` binary**: more images, more pinning,
  more drift surface. Considered for v2 if a desktop CLI becomes a
  real ask.
- **C — Kubernetes Job per adoption**: same idea as the `kubectl run`
  above, but pre-baked as a `kind: Job` template. Useful for CI/audit
  trails. Document as an alternative invocation method, don't make it
  the only one.

### RBAC for the CLI's ServiceAccount

```yaml
# illustrative only — not for commit
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: pvc-plumber-adopt
rules:
- apiGroups: [""]
  resources: ["persistentvolumeclaims"]
  verbs: ["get", "list", "patch"]
- apiGroups: [""]
  resources: ["namespaces"]
  verbs: ["get", "list"]
- apiGroups: ["volsync.backube"]
  resources: ["replicationsources", "replicationdestinations"]
  verbs: ["get", "list"]                  # READ ONLY
- apiGroups: [""]
  resources: ["secrets"]
  verbs: ["get", "list"]                  # READ ONLY (to verify repo Secret presence)
```

The absence of any `verbs: ["create", "update", "delete"]` on RS/RD
makes the "adopt cannot mutate RS/RD" rail enforceable at the API
server. Even a buggy CLI cannot escape this RBAC.

---

## 11. Tests

### Unit tests (fake client)

| Test | Asserts |
|---|---|
| `dry_run_writes_nothing` | `--dry-run` produces a plan; fake client records zero writes. |
| `clean_shape_writes_only_labels` | `PASS_SAFE_TO_ADOPT` writes exactly the three labels. Records no annotation writes, no RS/RD writes. |
| `with_warnings_writes_annotations_only_on_override` | `--cache-capacity 5Gi` writes the annotation; same flag at default writes none. |
| `uid_mismatch_blocks_without_override` | Mover UID 1001 on RS, no `--uid` flag → `BLOCKED_UID_MISMATCH`. Records no writes. |
| `uid_mismatch_passes_with_override` | Same RS + `--uid 1001 --gid 1001 --fs-group 1001` → `PASS_WITH_WARNINGS`. Writes labels + UID annotations. |
| `repo_mismatch_blocks` | RS repo `wrong-repo` → `BLOCKED_REPO_MISMATCH`. Never overridable. |
| `unknown_owner_blocks` | `managed-by: someoperator` → `BLOCKED_OWNER_UNKNOWN`. Never overridable. |
| `stale_backup_blocks` | `lastSyncTime` > 48h for daily → `BLOCKED_BACKUP_STALE`. |
| `stale_backup_passes_with_flag` | Same + `--allow-stale-backup` → `PASS_WITH_WARNINGS`. WARN logged. |
| `no_successful_backup_blocks` | Empty `lastSyncTime` → `BLOCKED_NO_SUCCESSFUL_BACKUP`. |
| `no_successful_backup_passes_with_two_flags` | Same + `--allow-no-successful-backup --force` → `PASS_WITH_WARNINGS`. ERROR logged. |
| `exempt_blocks` | `backup-exempt: "true"` → `BLOCKED_EXEMPT`. No flag overrides. |
| `system_ns_blocks` | PVC in `kube-system` → `BLOCKED_SYSTEM_NAMESPACE`. No flag overrides. |
| `missing_privileged_movers_blocks` | Namespace lacks the label → `BLOCKED_MISSING_PRIVILEGED_MOVERS`. |
| `already_adopted_idempotent` | Both gates already set → `ALREADY_ADOPTED`, exit 0, no writes. |
| `undo_removes_only_pvc_plumber_labels` | Foreign label survives `undo`. Operator labels removed. |
| `undo_skips_foreign_field_manager` | A v4-named label owned by a different field manager is skipped, not stripped. |
| `field_manager_conflict_behavior` | Two CLI invocations with same field manager → second one no-ops cleanly. |
| `no_rs_rd_writes_under_any_path` | Fake client write recorder asserts zero RS/RD writes across the full test matrix. |
| `golden_output_table` | Output matches golden file for `PASS_WITH_WARNINGS` + drift. |
| `golden_output_json` | JSON output matches golden schema. |

### Integration tests (envtest)

| Test | Asserts |
|---|---|
| `end_to_end_dry_run` | Real PVC + real RS/RD in envtest cluster; `--dry-run` produces correct plan. |
| `end_to_end_live_label_write` | Same + live mode → labels written. `kubectl get pvc -o yaml` shows the labels. RS/RD unchanged. |
| `end_to_end_undo` | Adopt → undo → labels gone. RS/RD still unchanged. |
| `rbac_enforces_no_rs_rd_writes` | A bug that tries to call `replicationsources.Update` fails with 403 under the adopt SA. |

### Manual test (Talos cluster, one-shot)

Documented in §12.

---

## 12. First adopt canary plan (nginx-example/storage)

**Why nginx-example/storage**:
- Disposable. App is a placeholder webserver; no real data on the
  storage PVC.
- Already exercised the failed Phase 6 cutover. Re-using it closes the
  loop on the exact failure that motivated this CLI.
- Argo-owned inline RS/RD currently exist and back up daily on schedule
  `18 2 * * *`. Backup chain is healthy as of last verification.
- `dataSourceRef` drift is present (live = `storage-backup`, Git =
  `storage-dst`). This is exactly the condition the CLI is built for.

### Pre-flight (no CLI, manual verification)

1. Confirm rc4 is live in permissive mode. Operator pod healthy.
2. Confirm `/audit?ns=nginx-example&pvc=storage` returns
   `skipped-not-opted-in`.
3. Confirm `lastSyncTime` on `ReplicationSource/storage` is within
   48h.
4. Confirm namespace has `volsync.backube/privileged-movers: "true"`.

### Canary sequence

1. **Dry-run**.
   ```
   pvc-plumber adopt pvc nginx-example/storage --tier daily --dry-run --diff
   ```
   Expect: `PASS_SAFE_TO_ADOPT` (or `PASS_WITH_WARNINGS` if minor cron
   minute drift). Capture `--emit-git-patch` output.

2. **Live label write**.
   ```
   pvc-plumber adopt pvc nginx-example/storage --tier daily --yes
   ```
   Expect: labels live on PVC. RS/RD unchanged.

3. **Verify gates live**.
   ```
   kubectl get pvc storage -n nginx-example -o jsonpath='{.metadata.labels}' | jq
   ```
   Both `enabled` and `manage-volsync` present, `tier=daily`.

4. **Verify /audit transition**.
   ```
   curl <pvc-plumber>/audit?ns=nginx-example&pvc=storage
   ```
   Expect: verdict `inline-argo-observed` (because inline RS/RD still
   exist). Zero ops planned.

5. **Commit Git PR — labels in Git** (defense-in-depth).
   Add labels to `my-apps/development/nginx/pvc.yaml`. Argo sync
   attempts to apply PVC. Will likely fail with `ComparisonError`
   because of `dataSourceRef` drift — that's fine, labels are already
   live.

6. **Commit Git PR — remove inline RS/RD**.
   Delete the inline `ReplicationSource/storage` and
   `ReplicationDestination/storage-dst` from `pvc.yaml`. Sync. Argo
   prunes both.

7. **Verify operator takeover**.
   ```
   kubectl get rs,rd -n nginx-example -l app.kubernetes.io/managed-by=pvc-plumber
   ```
   Expect: `ReplicationSource/storage` + `ReplicationDestination/storage-dst`
   appear with `managed-by: pvc-plumber`. Schedule may differ from
   `18 2 * * *` — recomputed deterministically from
   `(nginx-example, storage, daily)`.

8. **Verify next backup tick** (wait one cadence — up to 24h for daily).
   `lastSyncTime` advances on the operator-owned RS.

### Stop-after rule
Hard stop after nginx-example/storage. No other adopt canary until the
CLI is reviewed and the next target (karakeep — see §13 open questions)
has its own go-ahead.

---

## 13. Open questions

| # | Question | Default if not decided |
|---|---|---|
| 1 | Should `adopt` require labels to also be committed to Git? | **No, but emit a patch.** Labels-in-Git is operator policy, not a CLI safety property. The selfHeal tests showed labels are safe live-only. Document the Git-side step in the cutover runbook as step 4 (defense-in-depth). |
| 2 | Should v1 support karakeep's `uid 1001 / gid 1001 / fsGroup 1001`? | **Yes.** That's the whole point of the `--uid/--gid/--fs-group` flags. Karakeep is the highest-value v1 adopt target. |
| 3 | Should `adopt` emit a Git patch but not write it? | **Yes.** `--emit-git-patch` produces the YAML on stdout. The CLI never touches Git. |
| 4 | How stale is too stale? | Defined in §4 freshness windows table. Tier-relative with `1.15-1.3x` cadence slack. Tunable via flag override. |
| 5 | Should batch adoption be v1 or v2? | **v2.** v1 is one PVC at a time. Per-PVC adoption forces a forced human moment. Batch ships after v1 status and freshness are battle-tested. |
| 6 | Should `BackupIntent` CRD replace this long-term? | **Yes, eventually.** A `BackupIntent` CRD lets backup policy live separate from PVC metadata and removes the "labels on the data resource" smell entirely. `adopt` is the bridge until then. Schedule the CRD design as Phase 9. |
| 7 | Should `adopt` ever take ownership of an existing `managed-by: argocd` RS/RD by relabeling it? | **No, never.** The PRD explicitly lists this as Phase 8. The cutover sequence (delete inline → operator recreates) is intentional. Relabeling lets the CLI step on Argo's field-manager territory and is the wrong shape. |
| 8 | Should `adopt status` work without an operator running? | **Yes.** Status is read-only; uses the same client-go reads the operator uses. Useful for incident response when the operator is down. |
| 9 | Should `adopt` block when permissive mode is not active (operator in audit)? | **No, but warn.** Adopt only writes PVC labels. It's safe regardless of operator mode. Warn the operator that `tier=daily` won't actually cause writes until the operator flips to permissive. |
| 10 | Should `adopt` write a sentinel annotation like `pvc-plumber.io/adopted-at: <ts>` for audit? | **Probably yes.** Cheap signal that the CLI wrote the labels rather than Argo. Helps future field-manager confusion debugging. Decide during implementation. |

---

## Cross-references

- [`docs/pvc-plumber-v4-prd.md`](pvc-plumber-v4-prd.md) — locked v4 design contract.
- [`docs/pvc-plumber-v4-cutover.md`](pvc-plumber-v4-cutover.md) — current Phase 6 runbook. This spec adds a new section for "drift-affected PVC adopt-mediated cutover."
- [`docs/pvc-plumber-v4-roadmap.md`](pvc-plumber-v4-roadmap.md) — track adopt CLI work as a Phase 6.x deliverable.
- [`~/.mink/wiki/projects/talos-argocd-proxmox/pvc-plumber-v4-nginx-canary-lessons.md`](../../.mink/wiki/projects/talos-argocd-proxmox/pvc-plumber-v4-nginx-canary-lessons.md) — the failure that motivated this spec.
- [`docs/volsync-storage-recovery.md`](volsync-storage-recovery.md) — backup/restore single source of truth.
