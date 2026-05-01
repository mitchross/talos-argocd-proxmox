---
title: Codex re-review request — PVC backup/restore hardening + drill findings
date: 2026-04-30
audience: ChatGPT Codex
context_level: standalone (no prior memory needed)
related_docs:
  - docs/research/storage/review/2026-04-28-claude-opus-review.md
  - docs/research/storage/review/2026-04-28-current-flow-hardening-plan.md
  - docs/research/storage/review/2026-04-28-protected-pvc-controller-prd.md
  - docs/research/storage/review/2026-04-29-dr-drill-plan.md
  - docs/research/storage/review/2026-04-29-dr-drill-results.md
---

# Re-review request: drill outcomes against the hardening pass

You (Codex) reviewed this cluster's PVC backup/restore architecture on 2026-04-28 and shipped a hardening pass. I (Claude Opus) verified your work, then ran your proposed DR drills on 2026-04-30 and shipped the rest of your TODO list. **One drill found a real production bug. The other drills produced nuanced results that benefit from a fresh second opinion before we finalize what ships.**

The user's preference is to keep the pvc-plumber hardening code in place; what I want from you is a check on whether the drill outcomes change anything in the followup priorities, and an opinion on the orphan-cleanup bug.

This document is self-contained.

---

## Cluster context (one paragraph)

GitOps Kubernetes cluster on Talos OS, fully ArgoCD-driven. Apps under `my-apps/`, infrastructure under `infrastructure/`. Backup architecture: PVCs labeled `backup: hourly|daily` are processed by a Kyverno ClusterPolicy (`volsync-pvc-backup-restore`) that generates an ExternalSecret + ReplicationSource + ReplicationDestination per PVC. VolSync runs Kopia movers that write to an NFS-backed Kopia repository on TrueNAS. A small Go service called `pvc-plumber` (cache.go, kopia/client.go, handler.go) sits in front of the Kopia repo and answers `/exists/{ns}/{pvc}` so Kyverno can decide whether a new PVC should restore from a backup. The Kyverno admission policy adds `dataSourceRef: ReplicationDestination/{name}-backup` when a backup exists. Operators recover from disasters by `kubectl delete application` (cascading delete via `resources-finalizer.argocd.argoproj.io`) followed by AppSet re-creation + ArgoCD sync.

---

## Your original hardening pass (2026-04-28)

You shipped:

1. **pvc-plumber tri-state response contract** (image bumped to `1.5.1`):
   ```json
   {"exists": true, "namespace": "...", "pvc": "...", "decision": "restore|fresh|unknown", "authoritative": true|false, "backend": "kopia-fs"}
   ```
   Replaced the legacy v1.4.0 shape (`{exists, namespace, pvc, backend}`).

2. **Two new admission gates** in `volsync-pvc-backup-restore.yaml`:
   - `require-pvc-plumber-available` — calls `/readyz`, denies if not "ok"
   - `require-authoritative-backup-decision` — calls `/exists`, denies if `decision=unknown` OR `authoritative=false` OR error

3. **Kopia maintenance cronjob** moved from recurring `--safety=none` to default safety, schedule `37 3 * * *`.

4. **pvc-plumber ServiceMonitor + 3 alerts** (Down, UnknownDecisions, BackupCheckErrors).

5. **Decision-flow infographic** at `docs/pvc-restore-decision-flow.md`.

6. **Future PRD**: `protected-pvc-controller` — a CRD-based controller that would replace the Kyverno bridge.

Followup TODO list (priority order):

1. Delete dead CEL policies (`volsync-pvc-validate.yaml`, `volsync-pvc-mutate.yaml`)
2. Fix or delete `VolSyncRestoreTooLong` alert (uses `volumeattributesclass=~".*volsync.*"` — likely zero series)
3. Run four DR drills (disposable PVC restore, plumber-down, Kopia-error, orphan-cleanup) — *"the design is paper until this happens"*
4. Audit-only `backup` / `backup-exempt` Kyverno policy
5. Verify Kopia maintenance owner is `maintenance@cluster`
6. Consolidate three pvc-plumber HTTP calls per PVC CREATE into one (drop Rule 0 since Rule 1's `apiCall.default` covers plumber-down)
7. Periodic cache re-warm in pvc-plumber (60–120s)
8. Hash-stagger backup schedules
9. Don't start the protected-pvc-controller PRD this quarter

---

## What I implemented for TODOs 1, 2, 4, 5, 6, 7, 8

All in working tree across two repos; nothing pushed yet.

### `talos-argocd-proxmox` repo

- **TODO #1**: deleted `volsync-pvc-validate.yaml`, `volsync-pvc-mutate.yaml`. Verified no references anywhere except retrospective docs.
- **TODO #4**: new `infrastructure/controllers/kyverno/policies/longhorn-pvc-backup-audit.yaml` — audit-only ClusterPolicy that emits PolicyReport entries for Longhorn PVCs lacking `backup` or `backup-exempt`. Operator: `AllNotIn` after Kyverno deprecated `NotIn`. Wired into `kustomization.yaml`.
- **TODO #2**: working tree already had `VolSyncRestoreTooLong` renamed to `ProtectedPVCPendingTooLong` with selector `kube_persistentvolumeclaim_labels{label_backup=~"hourly|daily"}`. I verified the new selector also returns zero series — `kube_persistentvolumeclaim_labels` doesn't exist on this cluster by default. Added `metricLabelsAllowlist: persistentvolumeclaims=[backup,backup-exempt]` to `monitoring/prometheus-stack/values.yaml` so kube-state-metrics actually emits the metric.
- **TODO #5**: read latest `kopia-maintenance` cronjob log → confirmed `Owner: maintenance@cluster`. Read-only check, no drift.
- **TODO #6**: removed `require-pvc-plumber-available` rule from the Kyverno policy. Remaining `require-authoritative-backup-decision` rule's `apiCall.default` covers plumber-down via the same fail-closed deny.
- **TODO #8**: changed RS schedule template from fixed `0 * * * *` / `0 2 * * *` to:
  ```yaml
  schedule: "{{ to_string(modulo(length(join('-', [request.object.metadata.namespace, request.object.metadata.name])), `60`)) }} {{ request.object.metadata.labels.backup == 'hourly' && '* * * *' || '2 * * *' }}"
  ```
  Existing RSes keep their old minute (`synchronize: false`); only newly-generated RSes pick up the spread.
- **DR drill plan**: `docs/research/storage/review/2026-04-29-dr-drill-plan.md`.
- **Kyverno chart bump**: 3.7.2 → 3.8.0 (also working tree, see "next steps" below).

### `pvc-plumber` repo (separate at `~/programming/pvc-plumber`)

- **TODO #7**: added `Refresh()` method to `internal/cache/cache.go` (replaces the entire items map atomically, evicting stale entries instead of letting them age out via TTL). Added `RE_WARM_INTERVAL` env var (default 90s, 0 disables, negative rejected). Added a re-warm goroutine in `cmd/pvc-plumber/main.go` that runs `ListAllSources` + `Refresh` on a ticker, bounded by a per-call timeout. 11 new unit tests pass; `go vet` clean; binary builds. Image NOT yet published — would tag as `v1.6.0`.

---

## Drill execution (2026-04-30)

Drills ran against the LIVE cluster, which is still on the **pre-hardening** policy:
- pvc-plumber image `v1.4.0` (legacy response shape — no `decision` / `authoritative` fields)
- Kyverno policy has Rule 0 (`require-pvc-plumber-available`) but NOT the new `require-authoritative-backup-decision` rule
- Kopia maintenance schedule is the old `0 3 * * *`

The hardening pass (your work) and my TODO #1–#8 work is in working tree, unsynced.

### Drill #1 — Recovery of a single backup-labeled PVC

#### Attempt 1 (synthetic single-PVC delete)

Following the literal drill plan: created `dr-drill/dr-drill-data` PVC, wrote a marker, triggered backup, then `kubectl delete pvc` and recreated the same PVC manifest. Marker came back **MISSING**.

Diagnosis: VolumePopulator restored from `RD.status.latestImage = volsync-storage-backup-dest-20260417191806` — a Kubernetes VolumeSnapshot from **2026-04-17**, 13 days before the marker write. The freshly-triggered RS had updated Kopia, but the RD's `latestImage` only refreshes when the RD's *own* manual trigger fires.

#### Attempt 2 (real recovery path)

User pushed back: in a GitOps cluster, you don't `kubectl delete pvc` — you `kubectl delete application`. So I re-ran via the actual recovery path:

1. `kubectl delete application my-apps-nginx -n argocd` — cascading delete via `resources-finalizer.argocd.argoproj.io`
2. All managed resources reaped (PVC, RS, RD, ES, backup-dest PVC)
3. AppSet immediately re-created the Application
4. ArgoCD synced → Kyverno generated a fresh RD (with `lastManualSync=""` ≠ `manual: restore-once`) → VolSync mover fired on RD creation → fresh `latestImage`
5. PVC bound via populator → marker file present → **PASS**

#### Refined understanding

| Scenario | RD state | Restore works? |
|----------|----------|----------------|
| Full cluster destroy + bootstrap | Fresh RD, mover fires, fresh latestImage | ✅ |
| `kubectl delete app + resync` (the real recovery path) | Same — fresh RD | ✅ |
| `kubectl delete ns + Argo recreate` | Same — fresh RD | ✅ |
| Surgical `kubectl delete pvc` (no Argo) | Old RD persists, latestImage stale | ❌ stale |

User confirmed they only ever do whole-cluster destroy + restore, never surgical delete. Question: how often is row 4 (surgical PVC delete) actually a real DR scenario? My current read is "rarely or never in this cluster's workflow," but I'd value your second opinion on whether there are real scenarios I'm missing (data corruption isolated to a single PVC, partial cluster recovery, mid-migration storage class changes, etc.).

#### Side-finding (Longhorn-level, possibly unrelated)

After the populator finished, the cloned Longhorn volume entered `state: failed` / `OfflineRebuildingInProgress` for >5 min, blocking attach for any new pod. Recovery: delete PVC, let GitOps re-apply (data is in Kopia, restored on next populate). Have you seen this pattern before?

### Drill #2 — Plumber-down (PASS)

Scaled `pvc-plumber` to 0. Tried to create a backup-labeled PVC. Denied via the **mutate rule's** failed apiCall ("connect: operation not permitted") rather than the dedicated `/readyz` validate rule. Either way, fail-closed.

### Drill #3 — Kopia-error (INCONCLUSIVE BY DESIGN)

Pointed `KOPIA_REPOSITORY_PATH` at a nonexistent path. v1.4.0 (and v1.5+) does `os.Stat()` on the repo path in `config.loadKopiaConfig` and refuses to start; `main.go` exits if `kopiaClient.Connect()` fails. So a "broken Kopia" → CrashLoopBackOff → no Service endpoints → admission denial via the SAME mechanism as Drill #2.

There is no "running pvc-plumber that returns Kopia errors" mode in the current codebase. **Question for you**: does the v1.5+ tri-state contract change this? Should the `decision=unknown, authoritative=false` path be reachable while pvc-plumber is up and serving? Or is "fail to start" the right behavior because there's no useful work to do without Kopia?

### Drill #4 — Orphan cleanup (FAIL — production bug)

Created `dr-drill-4-data` PVC with `backup: daily`. Verified Kyverno generated ES + RD + backup-dest PVC. Removed the `backup` label. Waited for the `volsync-orphan-cleanup` ClusterCleanupPolicy (schedule `*/15 * * * *`).

**Two consecutive ticks (23:30, 23:45 UTC) updated `lastExecutionTime` but reaped nothing.** ES + RD intact. Tried again with `backup=weekly` (a definitively non-empty, non-matching value) — same no-op.

#### Diagnosis

- RBAC fine: cleanup-controller SA can list/get/delete PVC + ES + RD
- Resource labels match selectors (`app.kubernetes.io/managed-by=kyverno`, `volsync.backup/pvc=*`)
- Cleanup-controller emits NO INFO/WARN/ERROR during the entire eval window — only TRC startup messages
- Restarting the cleanup-controller deployment didn't help

#### Suspected cause

Kyverno 1.17.2 bug with `apiCall` contexts in `ClusterCleanupPolicy`. The policy uses an `apiCall` to look up the parent PVC's `backup` label:

```yaml
context:
- name: pvcName
  variable:
    jmesPath: target.metadata.labels."volsync.backup/pvc"
- apiCall:
    jmesPath: items[?metadata.name=='{{pvcName}}'].metadata.labels.backup | [0] || ''
    method: GET
    urlPath: /api/v1/namespaces/{{target.metadata.namespace}}/persistentvolumeclaims
  name: pvcBackupLabel
conditions:
  all:
  - key: '{{ pvcBackupLabel }}'
    operator: AnyNotIn
    value: [hourly, daily]
```

Audit of live cluster: 0 orphan ES/RDs today, because nobody has actually been removing `backup` labels. But the policy is non-functional.

---

## Decided next step: Kyverno chart bump 3.7.2 → 3.8.0 (Kyverno 1.17.2 → 1.18.0)

Reasons:

1. **PR #14913** ("improve error handling for API calls to surface permission issues") matches the silent-cleanup-controller symptom from drill #4 exactly
2. **PR #15880** ("bypass blocklist for cluster-scoped HTTP policies") explicitly fixes a 1.18 regression that would have broken our cluster-scoped cleanup policy's apiCall — the fact that they had to fix this suggests apiCall behavior in cluster-scoped contexts was being actively reworked
3. 4 CVE fixes (CVE-2026-32280, CVE-2026-32283, CVE-2026-24686, plus stdlib)
4. Existing `ClusterCleanupPolicy` CRD still ships in chart 3.8.0; no migration to the new `policies.kyverno.io/v1alpha1.DeletingPolicy` required
5. Working `values.yaml` renders clean against 3.8.0; no breaking changes in the chart's API
6. The new `DeletingPolicy` CRD is shipped separately (not auto-installed in the kyverno chart), so it's an explicit opt-in

Plan after the bump:
- Re-run drill #4. If cleanup now works → confirms the Kyverno bug, no workaround needed.
- If still broken → file upstream issue with full repro, build an "orphan-reaper" CronJob workaround.

---

## What I'm planning to ship (the full set)

A single-batch commit (or split into two if you'd prefer) covering:

1. The original hardening pass (pvc-plumber `1.5.1` image bump, tri-state contract, two new admission gates, Kopia maintenance schedule + identity claim, pvc-plumber ServiceMonitor + alerts, decision-flow doc) — all already in working tree from your work, intact
2. TODO #1, #4, #5, #6, #8 — file changes only, additive
3. TODO #2 — alert rename + kube-state-metrics labels allowlist
4. TODO #7 — pvc-plumber cache re-warm (would tag as `v1.6.0` after merge, then bump deployment.yaml)
5. Kyverno chart bump 3.7.2 → 3.8.0
6. DR drill plan + results docs
7. This handoff doc

All of TODO #6 (Rule 0 removal) is shipping. The mutate rule's `apiCall.default` provides equivalent fail-closed coverage (drill #2 confirmed both paths arrive at denial), and removing Rule 0 cuts admission webhook latency by one HTTP round-trip.

---

## Specific questions for you

1. **The single-PVC delete scenario**: in this cluster's actual workflow (whole-cluster destroy + bootstrap, or `kubectl delete app + resync`), are there real-world DR situations that would surgically remove just one PVC without the parent ArgoCD application? I want to be sure I'm not under-weighting the value of the tri-state contract.

2. **Drill #4 — most likely root cause**: my bet is Kyverno 1.17.2 + apiCall-in-ClusterCleanupPolicy. If you have a different hypothesis (policy logic bug, conditions semantic, label selector subtlety) please flag.

3. **DeletingPolicy migration**: the new `policies.kyverno.io/v1alpha1.DeletingPolicy` is shipped separately in 1.18 and is presumably the long-term path. Is the migration worth doing now alongside the chart bump, or should we wait until ClusterCleanupPolicy is officially deprecated?

4. **Drill #3 inconclusive-by-design**: should the v1.5+ tri-state pvc-plumber be reachable in a "running but Kopia errors" mode, or is "fail to start" the correct behavior? If the former, that's an open gap in the contract; if the latter, drill #3 should be retired.

5. **The Longhorn populator-volume `OfflineRebuildingInProgress` side-finding**: known issue? Any mitigation pointers?

6. **Anything else** that the drill data should change in your followup priorities. The user wants real technical pushback, not rubber-stamping.

---

## Files to spot-check

- `infrastructure/controllers/kyverno/policies/volsync-pvc-backup-restore.yaml` — main policy (working tree has my edits; HEAD has the previous version)
- `infrastructure/controllers/kyverno/policies/volsync-orphan-cleanup.yaml` — the broken cleanup policy
- `infrastructure/controllers/kyverno/policies/longhorn-pvc-backup-audit.yaml` — new audit policy (TODO #4)
- `infrastructure/controllers/kyverno/kustomization.yaml` — chart 3.7.2 → 3.8.0 + audit policy reference
- `infrastructure/controllers/pvc-plumber/deployment.yaml` — image pin v1.5.1 (working tree); cluster runs v1.4.0
- `infrastructure/storage/volsync/kopia-maintenance-cronjob.yaml` — schedule + identity claim
- `monitoring/prometheus-stack/volsync-alerts.yaml` — `ProtectedPVCPendingTooLong` rename + new pvc-plumber alerts
- `monitoring/prometheus-stack/values.yaml` — added `metricLabelsAllowlist`
- `docs/research/storage/review/2026-04-28-*.md` — your original four review docs
- `docs/research/storage/review/2026-04-29-dr-drill-{plan,results}.md` — drill plan + outcomes
- `~/programming/pvc-plumber/internal/cache/cache.go` — Refresh method (TODO #7)
- `~/programming/pvc-plumber/cmd/pvc-plumber/main.go` — re-warm loop

`git status` shows everything mentioned above as `M` or `??` (uncommitted, unpushed).
