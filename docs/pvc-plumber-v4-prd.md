# pvc-plumber v4 — Platform Controller PRD

| | |
|---|---|
| Status | **v4.0.1 SHIPPED (permissive); migration + DR-completeness campaign COMPLETE (24/24 DR_COMPLETE, 2026-06-01).** See **§0 CANONICAL STATUS** for shipped-vs-design. The locked design's strict/webhook half (§6–§10, phases 8–12) is FUTURE v5, not built. |
| Decision lock | pvc-plumber is the intended long-term platform abstraction for label-driven, fail-closed, GitOps-friendly PVC backup and restore. The 2026-05-21 decommission is reversed by this PRD. |
| Operator repo | <https://github.com/mitchross/pvc-plumber> (`v4.0.1` shipped/proven). |
| GitOps repo | This repository (`talos-argocd-proxmox`). |
| Author / operator | Mitch (single-operator homelab). |
| First written | 2026-05-22. |

> **Execution status (2026-06-01, not part of the locked design):** v4.0.1 is shipped and proven in permissive mode. The migration and DR-completeness campaign is complete: 24 operator-managed PVCs across 18 namespaces, 24/24 DR_COMPLETE before the full cluster nuke.

---

## 0. CANONICAL STATUS (2026-06-01) — shipped reality vs original design

> This section is the **source of truth for what is actually live**. The locked design
> below (§1–§19) is preserved as the original PRD record; where the two differ, this
> section wins. Added after the migration + DR-completeness campaign closed.

### SHIPPED — pvc-plumber v4.0.1 (live, permissive mode)
- Operator image `4.0.1@sha256:721d770…`, deployed at **Wave 2**, **permissive** mode, healthy (0 restarts).
- **Label/RBAC model as built (differs from the §3/§8/§16 webhook-centric design):**
  - Namespace **software write-gate**: `pvc-plumber.io/managed-namespace: "true"`.
  - PVC **fuse labels**: `pvc-plumber.io/enabled`, `pvc-plumber.io/manage-volsync`, `pvc-plumber.io/tier`.
  - A single **cluster-wide `ClusterRoleBinding pvc-plumber:volsync-writer`** (RS/RD verbs) — **no per-namespace RoleBindings**.
  - The controller **watches PersistentVolumeClaims** and reconciles RS/RD; it forces mover `568/568/568`.
- Generated RS (`<pvc>`) + RD (`<pvc>-dst`) carry `app.kubernetes.io/managed-by: pvc-plumber`.
- `/audit` HTTP endpoint live (port 8080) — reports `action`, `owner_classification`, `label_source`, `stale` per PVC.
- A scheduled `kopia-maintenance` CronJob (volsync-system, every 6h) handles repo maintenance.

### PROVEN — restore-drill behavior (end-to-end, byte-identical)
Four delete→recreate→VolSync-populator-restore drills passed (sentinel sha256 match, old-uid embedded):
- `copyparty/copyparty-data` (had dsr) — baseline restore proof.
- `paperless-ngx/data` (empty-reset; **dsr added**) — hit the stale-render race → needed a double-recreate.
- `paperless-ngx/media` (empty-reset; **dsr added**) — no double-recreate (mitigation held).
- `immich/library` (empty-reset; **dsr added**) — no double-recreate; both consumers quiesced; marker initContainer OK.
Runbook: `docs/volsync-storage-recovery.md` → "Restore drill runbook".

### MIGRATION CAMPAIGN STATUS — COMPLETE for normal app PVCs
- **24 operator-managed PVCs across 18 namespaces.** **24/24 are DR_COMPLETE** (Git `dataSourceRef → matching managed RD`).
- **PostHog** (4 PVCs) — `backup-exempt`/disposable; never migrate.
- **CNPG** (8 PVCs) — never generic-migrated; native Barman→S3 (RustFS). Permanent exclusion.
- **redis-instance/redis-master-0** — `backup-exempt`/disposable; never migrate.
- No remaining normal app-PVC migration work.

### DEPRECATED — Kyverno path (fully removed)
Kyverno is **not** in the backup path: no live Kyverno install, zero ClusterPolicies/Policies, zero policy
manifests in Git (verified 2026-06-01). The label→RS/RD generation Kyverno once did is now the operator's
reconciler. Remaining Kyverno mentions are historical (research/plans/presentation docs + the 2026-04-08
webhook-deadlock incident note). Per §2 this was always a non-goal for v4.

### FUTURE — v5 "strict restore" architecture (NOT shipped; do not overclaim)
The locked design's webhook/decision-engine vision (§6–§10, §14 phases 8–12) is **not built**. v4.0.1 ships the
*reconciler + permissive* half only. A future **v5** would add: admission **mutating/validating webhooks**,
the **cache-first backup-truth engine** with stale detection, **`enforce`/`strict` modes** (fail-closed on
unknown backup state), **source gating / `min-backup-age`**, **duplicate-identity** enforcement, full
**metrics/events**, and **whole-cluster-nuke restore protection**. These remain design-only until a v5 PRD
amendment + the §10 failure-matrix drills pass.

### OPEN QUESTIONS (still unresolved)
- Whether to build v5 strict mode at all, or keep permissive + the existing MAP backend-gate as "good enough". **NEW framing (2026-06-01): v5 is a fork — (A) a stricter VolSync layer vs (B) a Kopia-native operator (per community ADR-0001). Parked, decision deferred. See [pvc-plumber-v5-kopia-native-future.md](pvc-plumber-v5-kopia-native-future.md).**
- Naming-strategy / backup-identity uniqueness (original §17 items 1–2) — moot unless v5 proceeds.

### OPS FOLLOW-UPS (tracked, not done in this PRD)
1. **Kopia maintenance** — healthy scheduled maintenance; manual full maintenance is not required. See `docs/domains/storage/kopia-maintenance-plan.md`.
2. **Rollback PV cleanup** — 7 retained `Released/Retain` PVs; plan in `docs/volsync-storage-recovery.md` (not yet executed).
3. **Longhorn / storage policy review** — tiered local-restore vs replicated-critical; `docs/domains/storage/architecture-future.md`.
4. **Longhorn health** — keep `0` faulted / `0` degraded / `0` rebuilding as the pre-nuke baseline.

---

## 1. Problem and goal

> [!NOTE]
> Sections 1-19 preserve the original locked design record. Current shipped behavior is defined by section 0 above.

The cluster has been through three backup architectures in twelve months:

1. **pvc-plumber operator + Kyverno** (pre-2026-04). Reverse-mapped PVCs from labels and rendered RS/RD via Kyverno generators.
2. **Helm chart per app** (2026-04 → 2026-05-21). 26 apps were bulk-migrated to a `helmCharts:` entry inflating an in-repo `volsync-backup` chart.
3. **Inline RS/RD per PVC + `ClusterExternalSecret` + `MutatingAdmissionPolicy`** (2026-05-21 transitional snapshot). Chart killed in commit `c401822a`. Each PVC carried its own RS+RD as additional documents.

The current state is **defensible but not the destination**:

- Every backed-up PVC carries ~80 lines of VolSync YAML I now own forever.
- The job-level MAP (`volsync-mover-backend-availability`) protects against empty-baseline backup overwriting good restore points, but only via a Job-creation-time TCP probe of RustFS — not via authoritative backup-existence truth.
- 27 PVCs in 7 apps still carry orphan RS/RD created by the deleted operator. Those objects live in the cluster but not in Git; a PVC recreate is a silent data-loss landmine.
- A full cluster nuke / Talos rebuild / Argo bootstrap currently relies on operator memory of the inline-pattern conventions. There is no platform-level guarantee that the first reconcile of a labeled PVC will inject a `dataSourceRef` against an authoritatively-known backup.

The goal is to re-adopt the operator as a **boring, safe, testable, observable, GitOps-friendly platform abstraction** that:

- Owns the companion VolSync resources for opted-in PVCs.
- Owns the restore decision (does a backup exist? should this PVC bind empty or restored?).
- Fails closed in strict mode when backup truth is unknown.
- Coexists with Argo-managed inline RS/RD during migration without fighting Argo for ownership.
- Survives a full cluster nuke / rebuild / restore.

## 2. Non-goals (the decision lock)

This PRD does **not** propose any of the following, and discussion of them is closed unless concrete repo evidence, failure modes, Kubernetes API constraints, or test results force a re-open:

- Verbose inline VolSync YAML as the **final** architecture (acceptable as transitional).
- A Helm chart for VolSync/PVC generation.
- Kyverno generate/mutate policies in the critical path.
- Flux-style postBuild substitution.
- Kustomize component / namePrefix tricks as the abstraction.
- A different backup product.
- A new unrelated operator framework.

Comparison against these alternatives is allowed only to validate migration risks, not to revisit the architectural choice.

## 3. Locked constraints from the 2026-05-22 planning session

These are non-negotiable rules adopted alongside the rest of this PRD. Every implementation phase must enforce them.

1. **Phase 1 (full inventory) is mandatory** before any pvc-plumber code change merges into the operator repo or any Application manifest is added to this repo. The inventory must map every protected PVC to:
   - namespace
   - app / repo path
   - workload `claimName` references (Deployment, StatefulSet, Helm-rendered manifests)
   - current PVC name (must remain unchanged)
   - expected `ReplicationSource` name
   - expected `ReplicationDestination` name
   - current owner: `inline-argo` / `orphan-cluster-only` / `helm-rendered` / `exempt` / `unknown`
   - repository Secret / ClusterExternalSecret reference
   - backup identity (default: `<namespace>/<pvc>`)
   - size
   - mover UID/GID
   - schedule / tier
   - restore policy / mode (current label and target v4 mode)

2. **pvc-plumber must not adopt or mutate any `ReplicationSource`, `ReplicationDestination`, `ExternalSecret`, or `Secret` that is still rendered by Argo from Git.** During migration:
   - Argo-owned resources are **audit-only** to the operator. The operator may compare them against its computed expectation and emit `BackupExpectedDriftFound` events, but it must not patch or recreate them.
   - Orphan cluster resources may be **adoption candidates** only after Phase 1 inventory proves they are not Git-owned.
   - Actual adoption happens **namespace-by-namespace or app-by-app** with explicit cutover (inline RS/RD removed from Git in the same or adjacent commit as the operator adoption).

3. **Webhook admission must not match the legacy `backup: hourly|daily` label.** The controller may read the legacy label for inventory and backward-compatibility reporting (this is helpful during migration). Admission webhooks register `objectSelector: matchLabels: pvc-plumber.io/enabled: "true"` exclusively, so a forgotten legacy label cannot brick PVC creation.

4. **Phase 2 must not become a feature pile before the decision engine is tested.** The operator-repo work in Phase 2 ships, in order:
   - Pure decision engine (no Kubernetes client calls).
   - Label / annotation parser.
   - Mode semantics (audit / permissive / enforce / strict / never / force).
   - Unit tests covering the failure-mode matrix in §10.
   - **No cluster-writing behavior is added in Phase 2.** No webhook is registered. No reconciler writes child resources. Audit mode is the only behavior available.

5. **Default rollout mode is `audit` (Phase 3-6), then `permissive` (Phase 6-7).** `enforce` is a canary-then-global flip in Phase 10-11. `strict` is the destination only after the failure-mode matrix and a real restore drill pass in Phase 9. No phase makes `strict` the default.

## 4. North-star user contract

A protected PVC declares intent with labels and annotations:

```yaml
metadata:
  labels:
    pvc-plumber.io/enabled: "true"
    pvc-plumber.io/tier: "hourly"          # hourly | daily | weekly | manual | disabled
  annotations:
    pvc-plumber.io/uid: "568"              # mover runAsUser
    pvc-plumber.io/gid: "568"              # mover runAsGroup / fsGroup
    # Optional knobs:
    # pvc-plumber.io/mode: "audit"         # per-PVC mode override
    # pvc-plumber.io/restore-mode: "force" # never | audit | permissive | enforce | strict | force
    # pvc-plumber.io/backup-identity: "immich-library"   # stable cross-namespace identity
    # pvc-plumber.io/min-backup-age: "2h"  # source gate against empty baselines
    # pvc-plumber.io/skip-restore: "true"
    # pvc-plumber.io/skip-restore-reason: "intentional fresh test PVC"
```

**Backward compatibility**: the operator reads the legacy `backup: hourly|daily` label for inventory and reporting, but it does **not** consider a legacy-labeled PVC opted in. Migration requires explicit `pvc-plumber.io/enabled: "true"`.

**PVC name immutability**: pvc-plumber must never force apps into generic names (`data`, etc.). Existing names — `config`, `library`, `data`, `data-pvc`, `media`, `output`, `redis-master-0`, `postgres`, `kafka`, `zomboid-data` — remain unchanged.

**Multi-PVC apps are first-class**: copyparty (config + data + media), paperless-ngx (data + media + archive + consume), karakeep (data-pvc + meilisearch-pvc), posthog (postgres + redis + kafka + clickhouse), immich (library + ml-cache + nfs-photos), swarmui (data + outputs + inputs + models), and the rest. Each PVC has independent identity, source, destination, and restore decision.

`persistentVolumeClaim.claimName` references in Deployments / StatefulSets / Helm charts must not break under any phase of this rollout.

## 5. Responsibilities

### pvc-plumber owns

- Watching opted-in PVCs (label-selector).
- Creating / updating `ReplicationDestination` for each opted-in PVC.
- Creating / updating `ReplicationSource` for each opted-in PVC (subject to source gating, §9).
- Referencing the shared `volsync-kopia-repository` Secret (already provided by `ClusterExternalSecret/volsync-kopia-repository`). The operator does **not** create per-PVC `ExternalSecret` resources in this cluster — that's already solved at the cluster level.
- Deciding whether a restore exists for a given PVC identity (§7-8).
- Injecting `dataSourceRef` into new PVCs at admission time when restore is appropriate.
- Failing closed in strict mode when backup truth is unknown.
- Allowing fresh empty PVC creation when it can authoritatively determine no backup exists, or when restore mode explicitly says to skip / never.
- Gating `ReplicationSource` enablement until the PVC is `Bound`, restore is complete (or skipped), and `min-backup-age` has elapsed.
- Cleaning up generated resources when a PVC is deleted or unlabeled.
- Emitting Kubernetes Events, Prometheus metrics, and structured logs.
- Supporting `audit` mode so we can observe parity before enforcing.

### pvc-plumber does NOT own

- Installing VolSync, Longhorn, External Secrets, ArgoCD, snapshot-controller, cert-manager. Those are Wave 0-1 dependencies.
- Generic app deployment.
- Secret values.
- VolSync mover-Job jitter (the existing `MutatingAdmissionPolicy/volsync-mover-backend-availability` plus per-PVC schedule hashing handles thundering-herd well enough; a separate jitter MAP is optional and not required for v4).
- Kyverno policies.
- The shared `ClusterExternalSecret/volsync-kopia-repository` (that's a cluster-wide concern, not per-PVC).

## 6. Modes

Modes are evaluated in this precedence order: per-PVC annotation `pvc-plumber.io/mode` → operator config default. `restore-mode` is independent and per-PVC only.

| Mode | Admission validator | Mutator dataSourceRef injection | Reconciler writes | Default for |
|---|---|---|---|---|
| `audit` | Never denies. Emits Events only. | Never. | Computes expectation, emits Events. No K8s writes. | Phases 3-5 bootstrap. |
| `permissive` | Warns on unknown; does not deny. | Injects when authoritatively-restore. Allows fresh when unknown (warn). | Creates and reconciles RS/RD/Secret for opted-in PVCs. | Phase 6-7 migration. |
| `enforce` | Denies on `Decision == unknown` for opted-in PVCs (per the §7 decision table). Allows opt-out via skip-restore + reason. | Same as permissive. | Same as permissive. | Phase 10-11 production. |
| `strict` | All of `enforce`, plus: cache-stale denies, duplicate backup-identity denies, missing repo config denies, invalid annotations deny. Source gating mandatory. | Same as enforce. | Same as permissive + drift correction. | Phase 11 destination. |
| `never` | Per-PVC. Never injects `dataSourceRef`. RS may still be created for backups. | Never. | Creates RS if tier enabled. No RD. | Disposable PVCs that should not restore. |
| `force` | Per-PVC. Denies if no backup exists or backup state is unknown. | Always injects (if backup exists). | Same as enforce. | DR drills, intentional restore tests. |

## 7. Decision model

The mutator and validator both call into the **decision engine**. The decision engine is pure: input is the PVC object + cache state + operator config; output is `(allow|deny, injectDataSourceRef?, reason)`.

| Case | Cache | Backup exists | Mode | Mutator | Validator |
|---|---|---|---|---|---|
| A | fresh | yes | enforce / strict / permissive | inject `dataSourceRef → <pvc>-dst` | allow |
| B | fresh | no | any | no mutation | allow (mark `BackupStateKnown / fresh`) |
| C | stale or backend unreachable | unknown | `strict` | no mutation | **deny** with explicit reason |
| C' | stale or backend unreachable | unknown | `enforce` | no mutation | deny |
| C'' | stale or backend unreachable | unknown | `permissive` / `audit` | no mutation | allow (warn) |
| D | any | any | per-PVC skip-restore + reason | no mutation | allow (emit `RestoreSkipped`) |
| D' | any | any | per-PVC skip-restore **without** reason | no mutation | **deny** |
| E | any | any | per-PVC `restore-mode: never` | no mutation | allow |
| F | any | no or unknown | per-PVC `restore-mode: force` | no mutation | **deny** |
| G | any | yes | per-PVC `restore-mode: force` | inject | allow |

Duplicate backup identities (two PVCs in different namespaces declaring the same `pvc-plumber.io/backup-identity`):
- `strict`: deny the second PVC.
- `enforce` / `permissive` / `audit`: warn.

## 8. Backup-truth cache

Admission **must** be cache-first. The operator runs an indexer goroutine that:

- Pre-warms the cache on startup by listing kopia snapshots for every known identity. Until pre-warm completes, the cache is `unknown` and admission behaves per the decision table.
- Refreshes per-repository on a configurable interval (default 60s).
- Uses `singleflight` to dedupe concurrent identity lookups.
- Exposes `pvc_plumber_cache_age_seconds`, `pvc_plumber_cache_refresh_total`, `pvc_plumber_cache_refresh_errors_total`.
- Backs off on backend errors with jittered exponential backoff (cap 5m).
- Maintains a `last-successful-refresh-at` timestamp per repository. Cache is "stale" if `now - last-successful-refresh > 2 × refresh-interval`.

The v3.1.0 operator already implements pre-warm + singleflight + tri-state result. v4 work extends this with stale detection (the `last-successful-refresh` clock) and per-repository granularity.

Live-lookup mode is configurable but **not the default**. Default is cache-first with `strict` denying on stale.

State persistence: the cache is in-memory only. A CRD is **not** added in v4 just to persist cache state; controller restarts re-warm from kopia. If restart-time pre-warm becomes a bottleneck (>2 min for the production set), persistence is revisited in a v4.1 PRD with concrete evidence.

## 9. Source gating

`ReplicationSource` must not run too early. The reconciler maintains a per-PVC `source-state` (exposed via the `pvc-plumber.io/source-state` annotation on the PVC and via Events):

| State | Meaning |
|---|---|
| `waiting_for_pvc_bound` | PVC is `Pending`. Do not create RS. |
| `waiting_for_restore` | RD exists, PVC has `dataSourceRef`, but VolSync hasn't reported restore complete. Do not create RS. |
| `waiting_for_min_age` | PVC is `Bound`, no restore was required, but `min-backup-age` (default 2h) has not yet elapsed since PVC `creationTimestamp`. Do not create RS. |
| `ready` | RS exists / will be reconciled. |
| `disabled` | `pvc-plumber.io/tier: disabled` or `pvc-plumber.io/enabled: false`. RS is removed. |
| `error` | Reconcile failure. RS state is preserved; event emitted. |

Manual backup trigger (`kubectl patch replicationsource ... --type=merge -p '{"spec":{"trigger":{"manual":"..."}}}'`) bypasses `waiting_for_min_age` only — never the other gates.

## 10. Failure-mode test matrix

Must be covered by unit tests in the decision engine and by integration tests in the reconciler / admission. No phase past 9 ships until this matrix is green.

1. Fresh app, no backup exists → allow fresh; no `dataSourceRef`.
2. Backup exists → inject `dataSourceRef → <pvc>-dst`.
3. Backup backend unreachable; mode = `strict` → deny.
4. Backup backend unreachable; mode = `audit` / `permissive` → allow + warn.
5. Cache stale; mode = `strict` → deny.
6. Cache stale; mode = `audit` / `permissive` → allow + warn.
7. Duplicate backup identity; mode = `strict` → deny second PVC.
8. Duplicate backup identity; mode = `audit` / `permissive` → warn.
9. Skip-restore without reason → deny.
10. Skip-restore with reason → allow + `RestoreSkipped` event.
11. Restore required but RD missing → reconciler creates RD before admission completes (or admission denies if RD cannot be created).
12. PVC restored but app not yet started → RS gated `waiting_for_restore`.
13. PVC created empty intentionally → RS gated `waiting_for_min_age`.
14. pvc-plumber pod down → opted-in `strict` PVCs fail closed. Unrelated PVCs (no `pvc-plumber.io/enabled` label) admit normally. **Webhook `objectSelector` is load-bearing here.**
15. VolSync CRD missing → reconciler surfaces `DependencyNotReady` condition; does not wedge unrelated resources.
16. ClusterES Secret not yet present in namespace → operator delays RS creation; emits `WaitingForRepoSecret`.
17. Namespace migration with stable `pvc-plumber.io/backup-identity` → restore works.
18. Multi-PVC app (e.g., copyparty) → each PVC has independent identity, source, destination, and decision.

## 11. Naming and labeling of generated resources

To match the transitional inline pattern in this repo and minimize migration churn:

- ReplicationSource: `metadata.name = <pvc-name>` (bare).
- ReplicationDestination: `metadata.name = <pvc-name>-dst`.
- ExternalSecret: **not generated by v4** — the shared `volsync-kopia-repository` Secret is materialized by `ClusterExternalSecret`. Operator config has a `repoSecretName` knob defaulting to `volsync-kopia-repository`.

Labels on every operator-generated resource:

```yaml
labels:
  app.kubernetes.io/managed-by: pvc-plumber
  pvc-plumber.io/source-namespace: <namespace>
  pvc-plumber.io/source-pvc: <pvc-name>
  pvc-plumber.io/backup-identity: <identity>
  pvc-plumber.io/tier: <tier>
  volsync.backup/pvc: <pvc-name>      # preserve existing convention
```

`app.kubernetes.io/managed-by` is the discriminator between operator-owned RS/RD and Argo-owned (inline) RS/RD. The operator must **never** patch a resource that does not already carry `app.kubernetes.io/managed-by: pvc-plumber`. Adoption is an explicit, opt-in act in Phase 6 / 7 — a separate code path that labels an orphan, gated by the inventory.

OwnerReferences on operator-generated RS/RD point at the PVC. Tradeoff: PVC deletion cascades through to RS/RD, which is acceptable because in a full cluster nuke the PVC is recreated and the operator regenerates them. RD is created **before** the PVC is bound (during admission flow) so the `dataSourceRef` resolves.

## 12. Native MAP / VAP scope

Reserved for **deterministic** mutations / validations only. Never queries external backup state.

Acceptable:
- Existing `MutatingAdmissionPolicy/volsync-mover-backend-availability` (Job-level backend gate). Keep as-is.
- New `ValidatingAdmissionPolicy` (optional, Phase 8) that validates label / tier values on opted-in PVCs without needing the operator running. Acts as a defensive co-pilot to the validating webhook.

Not acceptable:
- Querying kopia / S3 / NFS from a MAP/VAP.
- Creating RS or RD from a MAP/VAP.
- Replacing pvc-plumber's external-state-aware logic.

Kubernetes API versions for MAP/VAP must be verified against the live cluster (`kubectl api-versions`, `kubectl version`) before writing manifests. Do not assume.

## 13. Argo ownership rule during migration

This is the second locked constraint, repeated for visibility.

| Resource state | Operator behavior |
|---|---|
| In Git as inline RS/RD; cluster-live with `managed-by: argocd` label | **Audit-only.** Compare against expectation. Emit drift events. **Do not patch.** |
| In cluster only (orphan from deleted operator); not in Git | **Adoption candidate.** Only after Phase 1 inventory confirms the resource is not Git-owned. Adoption = relabel `managed-by: pvc-plumber`. |
| In Git with `pvc-plumber.io/enabled` and no inline RS/RD | **Owned by operator.** Reconcile RS/RD as needed. |
| In Helm chart values (`extraDeploy`) | Same as inline-Argo: audit-only until the chart's owner namespace is explicitly cut over. |

Cutover (Phase 7) is **namespace-by-namespace or app-by-app**. The same commit (or adjacent commits within hours) must:

1. Add `pvc-plumber.io/enabled: "true"` + `pvc-plumber.io/tier` to the PVC(s).
2. Remove the inline `ReplicationSource` and `ReplicationDestination` documents from `pvc.yaml`. Keep the PVC and its `dataSourceRef`.
3. Verify the operator's audit log shows "would recreate identical resource".
4. Merge. Argo prunes the inline RS/RD; the operator recreates them under `managed-by: pvc-plumber` within one reconcile loop.
5. Verify the next scheduled backup completes.

## 14. Phased rollout

Twelve phases. Each phase is independently mergeable, individually rollback-safe, and gated by explicit user GO before proceeding.

| Phase | Title | Scope | Risk | Exit criterion |
|---|---|---|---|---|
| 0 | Docs alignment (this patch) | CLAUDE.md + add-backup.md + this PRD. No code, no manifests, no cluster change. | Zero | No live doc instructs the use of the deleted chart. PRD in repo. |
| 1 | Inventory (mandatory, locked) | `hack/render-pvc-inventory.py` (read-only). Produces a CSV/table with every column listed in §3 rule 1. | Very low | Single table covers every protected PVC. Orphan-vs-inline classification accurate. |
| 2 | Operator: decision engine + parser + modes + tests | Operator-repo code only. Pure decision engine, label / annotation parser, mode enum, failure-matrix unit tests. **No webhook, no reconciler writes.** Audit-only `/audit` HTTP endpoint. | Low (no cluster touch) | `go test ./...` green; binary runs with `mode: audit`; `/audit` returns parity table on a real PVC list piped in. |
| 3 | talos repo: pvc-plumber Wave-2 App in audit mode | `manifests/infra/pvc-plumber/deploy-targets/talos/` plus `clusters/talos/argocd/core-dependencies/pvc-plumber-app.yaml`. Deployment, RBAC (least-privilege), Service, ServiceMonitor, PrometheusRule. **No webhook configurations.** Argo Application entrypoint. | Low | Operator running healthy. `/audit` serves parity for live PVCs. Zero generated resources. Zero PVC denials. |
| 4 | Parity verification | Compare `/audit` against orphan cluster RS/RD and inline RS/RD. Document mismatches in tracker. | Very low | ≥95% PVC parity; per-app exceptions documented. |
| 5 | Operator: source-gating + naming strategy + metrics | Source-state machine. Naming strategy option (default matches current inline: bare RS, `-dst` RD). Prometheus metrics per §15. | Low (still audit-only) | Tests green; `/audit` output uses correct names. |
| 6 | Operator: switch to permissive mode + adopt orphans | Permissive mode default. Adoption code path: relabel unmanaged orphan RS/RD with `managed-by: pvc-plumber`. Inline-Argo resources remain audit-only per rule 2. | Medium (first cluster write) | 27 orphan apps adopted. Inline apps unchanged. Backups continue. |

> **SUPERSEDED IN PRACTICE (2026-05-29):** the 27-orphan adoption figure is stale (inventory found 0 orphan-cluster RS/RD), and the live Phase 6 implementation uses a NO-adoption model — inline RS/RD are removed from Git first and the operator recreates managed RS/RD. See docs/pvc-plumber-v4-cutover.md (Ownership section) and docs/pvc-plumber-v4-migration-readiness.md.

| 7 | Migrate inline-RS/RD apps to operator ownership, app-by-app | Per app: add `pvc-plumber.io/enabled` + tier; remove inline RS/RD from `pvc.yaml`. Verify audit said "would recreate identical". Verify backup post-cutover. | Medium per-app | Zero inline RS/RD in `manifests/apps/**`. All protected PVCs carry `pvc-plumber.io/enabled`. |
| 8 | Webhook deployment in permissive mode | `ValidatingWebhookConfiguration` + `MutatingWebhookConfiguration`. `objectSelector: matchLabels: pvc-plumber.io/enabled: "true"` exclusively (rule 3). 9-namespace system exclusion in `namespaceSelector`. 2 replicas + PDB. cert-manager Certificate for TLS. | Medium-high (SPOF re-entry point) | Webhook fires on test-namespace PVC; deny path tested but disabled by mode. **Pre-merge gate: explicit user GO.** |
| 9 | Failure-matrix drills | Run all 18 §10 cases against a dev namespace. Restore-honesty: sentinel data → backup → delete PVC → recreate → read sentinel → check ownership. | Low (dev scope) | `docs/pvc-plumber-v4-failure-matrix-results.md` committed with all 18 cases green. |
| 10 | Enforce mode for one canary namespace | Promote one well-behaved app (e.g., `nginx` or `open-webui`) to `mode: enforce` via per-PVC annotation. 48h observation. | Low | Zero unexpected denials. Canary survives restart drill. |
| 11 | Global enforce → strict | Flip operator default to `enforce` cluster-wide. Observe one full backup cycle (24h+). Flip to `strict`. Restore drill against a random app. | High (SPOF concretized; rule 5 ensures this is the latest possible phase) | All backups green. Restore drill passes. |
| 12 | Full cluster nuke / rebuild / restore | **Only on explicit `GO NUKE CLUSTER`.** Runbook execution, no code changes. | Owned by user, not agent | All apps healthy, data verified, no empty-baseline contamination, no Argo / operator ownership fights. |

## 15. Observability

Metrics (Prometheus):

- `pvc_plumber_cache_age_seconds{repo}`
- `pvc_plumber_cache_refresh_total{repo,outcome}`
- `pvc_plumber_cache_refresh_errors_total{repo,error_type}`
- `pvc_plumber_admission_requests_total{operation,result,mode}`
- `pvc_plumber_admission_denied_total{reason,mode}`
- `pvc_plumber_restore_injections_total`
- `pvc_plumber_backup_exists_total`
- `pvc_plumber_backup_unknown_total`
- `pvc_plumber_generated_resources_total{kind}`
- `pvc_plumber_reconcile_errors_total{kind,reason}`
- `pvc_plumber_source_gated_total{state}`
- `pvc_plumber_duplicate_identity_total`

Events (`Reason` field):

- `BackupStateKnown` / `BackupStateUnknown`
- `RestoreInjected` / `RestoreSkipped` / `RestoreDenied`
- `SourceGated` / `SourceReady`
- `GeneratedResourceCreated` / `GeneratedResourceUpdated` / `GeneratedResourceDriftCorrected`
- `DuplicateBackupIdentity`
- `BackupExpectedDriftFound` (audit-mode diff against Argo-owned resource)
- `DependencyNotReady`
- `WaitingForRepoSecret`

Logs: structured, namespace + name + identity + tier + mode + decision reason. **Never log secret values.**

## 16. Security and RBAC

Least-privilege ClusterRole:

| Resource | Verbs |
|---|---|
| `persistentvolumeclaims` | `get, list, watch, patch` (patch for annotation status only) |
| `replicationsources.volsync.backube` | `get, list, watch, create, update, patch, delete` |
| `replicationdestinations.volsync.backube` | `get, list, watch, create, update, patch, delete` |
| `events.events.k8s.io` | `create, patch` |
| `leases.coordination.k8s.io` | `get, list, watch, create, update, patch` (leader election) |

The operator does **not** need `secrets` read access broadly — kopia credentials are loaded from a mounted Secret volume (the shared `volsync-kopia-repository`), not via the Kubernetes API. This is a hard rule: if a future feature needs to read other Secrets, that feature gets its own narrow scoped RBAC and a justification in a v4.x amendment to this PRD.

Pod security: `runAsNonRoot`, `readOnlyRootFilesystem` where practical, drop all capabilities, resource requests / limits, `NetworkPolicy` allowing only egress to RustFS endpoint + DNS + kube-apiserver.

Webhook TLS via cert-manager `Certificate`. Webhook configs use `cert-manager.io/inject-ca-from` annotation.

## 17. Open questions (to resolve in later phases, do not block Phase 0)

1. **Naming strategy for legacy operator-era RS/RD that are still in cluster.** The v3.1.0 operator used `<pvc>-backup` for both RS and RD. The current inline pattern uses `<pvc>` and `<pvc>-dst`. The 27 orphan objects from the deleted operator use `<pvc>-backup`. The v4 operator should support a `naming-strategy: legacy-backup | bare-dst` config knob, default `bare-dst`. Adoption code path detects the legacy name and either renames (risky, breaks the kopia identity?) or rebuilds (loses retention history). Decide in Phase 6.
2. **Backup identity uniqueness enforcement.** Default identity is `<namespace>/<pvc>`. A `pvc-plumber.io/backup-identity` annotation overrides for cross-namespace stability. Strict mode denies duplicates — but the kopia repo already uses `username`/`hostname` (current inline pattern: `<pvc>`/`<namespace>`). The identity-to-kopia mapping needs to be explicit. Decide in Phase 5.
3. **MAP RustFS endpoint hardcoding.** `192.168.10.133:30292` is in the MAP YAML. v4 could read this from a `ConfigMap` shared with the operator. Decide in Phase 5 or punt to v4.1.
4. **Multi-replica leader election cost.** 2 replicas + PDB is required to defeat the SPOF risk that decommissioned v3. But two pods running a kopia subprocess on every cache refresh doubles RustFS load. Singleflight is in-pod, not cross-pod. Decide whether to gate refresh on leader only in Phase 5.
5. **Helm-rendered PVCs cutover plan.** gitea, n8n, headlamp, strimzi, temporal mount PVCs that are owned by upstream charts. Kustomize `patches:` inject the `dataSourceRef`; `extraDeploy:` provides RS/RD. Phase 7 needs an app-specific plan for each.

## 18. References

- Operator repo: <https://github.com/mitchross/pvc-plumber>
- Transitional inline pattern used during migration: `manifests/apps/ai/open-webui/deploy-targets/talos/pvc.yaml`
- Application guidelines: `manifests/apps/CLAUDE.md`
- MAP + ClusterES: `manifests/infra/volsync-backup-cluster/deploy-targets/talos/`
- VolSync operator: `manifests/infra/volsync/deploy-targets/talos/`
- Decommission history: `docs/research/pvc-backup-simplification/`
- Add-backup workflow (transitional): `.claude/commands/add-backup.md`
- VolSync DR runbook: `docs/volsync-storage-recovery.md`
- CNPG DR (separate system): `docs/domains/cnpg/disaster-recovery.md`
- RustFS credential conventions: `docs/domains/rustfs/credential-runbook.md`

## 19. Change log

| Date | Phase | Change |
|---|---|---|
| 2026-05-22 | 0 | PRD created. CLAUDE.md and `.claude/commands/add-backup.md` aligned with current live pattern. No operator code, no cluster manifests, no cluster state changed. |
