---
title: Codex re-review response — agreed actions
date: 2026-04-30
relates_to:
  - docs/research/storage/review/2026-04-30-codex-rebuttal-handoff.md
  - docs/research/storage/review/2026-04-29-dr-drill-results.md
---

# Codex re-review response — agreed actions

Codex re-reviewed the drill outcomes + my "what to ship vs skip" calls. They
broadly agreed with the shipping plan and pushed back constructively on three
specific framings + added action items. This is the digest + follow-up TODO list.

## Where Codex pushed back (and we agree)

### 1. Surgical PVC delete is **not** artificial

> "It is not your normal DR workflow, but it is a credible ops workflow after
> Longhorn attach failure, accidental PVC deletion, isolated app corruption,
> storage-class migration, or 'repair one app without reaping the whole Argo
> app.' The stale-RD behavior is a real footgun."

**Action**: drill results doc updated. Confidence map's row 4 ("surgical PVC
delete") now framed as realistic break-glass + documents the safe procedure
(delete the matching ReplicationDestination too, OR just delete the Argo app).

### 2. The schedule stagger is **not** a real hash

> "Using length(namespace-name) % 60 is deterministic but not a real hash. It
> may cluster badly because PVC names often have similar lengths. I'd still
> ship it as better than top-of-hour, but call it a temporary spread, not
> hash-staggering."

**Action**: terminology in `infrastructure/controllers/kyverno/policies/volsync-pvc-backup-restore.yaml`
+ `infrastructure/controllers/kyverno/CLAUDE.md` reworded to "length-based
deterministic spread (TEMPORARY)" with a note to replace with a sha256-derived
minute (or controller-driven scheduling) when inventory grows past ~50
backup-labeled PVCs.

### 3. The new alert needs verification, not just deployment

> "The kube_persistentvolumeclaim_labels alert fix only works after
> kube-state-metrics is actually reconfigured and scraped. After the
> metricLabelsAllowlist change syncs, verify the series exists before trusting
> ProtectedPVCPendingTooLong."

**Action**: post-sync checklist item added below.

## Where Codex confirmed Claude's read

- **DeletingPolicy migration**: don't migrate now. Bump 1.18, rerun #4, then
  decide. Mixing variables makes the drill result less useful.
- **Drill #3 inconclusive-by-design**: failing-to-start IS correct for bad
  static config. But `decision=unknown, authoritative=false` should remain
  reachable for **runtime** failures (Kopia CLI timeout, JSON parse error,
  NFS issue after startup). Retire the bogus-repo-path live drill, not the
  unknown contract. Replace with a unit test using a failing executor.
- **Drill #4 root cause**: apiCall hypothesis is plausible but unproven.
  Codex proposed a narrower test (see action item below).
- **Longhorn `OfflineRebuildingInProgress`**: matches known Longhorn behavior
  for detached-volume rebuild + "volume not ready for workloads." Suggested
  mitigations captured below.
- **Tri-state contract value**: protects "unknown backup truth" — still
  worth shipping even though it doesn't help the surgical-delete case.

## Action items — pre-commit (done in this session)

- [x] Reword schedule stagger in policy YAML + kyverno CLAUDE.md
- [x] Update drill results doc with the surgical-delete realism + safe procedure
- [x] Capture Codex's full review in this followup doc

## Action items — post-sync

- [ ] **Verify the PVC backup metric lands**. After kube-state-metrics picks up
  the `metricLabelsAllowlist` config:
  ```promql
  count(kube_persistentvolumeclaim_labels{label_backup=~"hourly|daily"})
  ```
  Should be > 0. If it isn't, `ProtectedPVCPendingTooLong` is still dead.

- [ ] **Re-run drills #1 + #2** against the synced hardened policy. The drills
  ran tonight tested pre-hardening behavior because the working tree wasn't
  synced yet. Re-running gives evidence the new tri-state contract works
  end-to-end against the real flow.

- [ ] **If drill #4 still fails post-1.18**, run Codex's narrower test before
  declaring it the apiCall path:
  > "Create a temporary cleanup policy with the same match selector and a
  > simple target-local condition, no apiCall. If that deletes, the bug is
  > almost certainly the apiCall context path. If it does not, the issue is
  > match/GVK/controller/RBAC, not JMESPath."

  Concretely: clone `volsync-orphan-cleanup.yaml`, strip the `context` block
  and replace `conditions.all` with something local like
  `key: "{{ target.metadata.labels.\"app.kubernetes.io/managed-by\" }}", operator: Equals, value: "kyverno"`.
  Apply, watch the next `*/15` tick.

- [ ] **Add "PVC actually mounts" assertion to future drill scripts**. Tonight's
  drills checked PVC `phase=Bound`, but the Longhorn side-finding showed a PVC
  can be Bound while still being unattachable. Future drills should mount a
  reader pod and read the marker file as a positive assertion, not just bind.

- [ ] **Longhorn populator-clone playbook** — next time the
  `OfflineRebuildingInProgress` happens, capture:
  - `kubectl get volume -n longhorn-system <vol> -o yaml`
  - `kubectl get engine -n longhorn-system -l longhornvolume=<vol> -o yaml`
  - `kubectl get replica -n longhorn-system -l longhornvolume=<vol> -o yaml`
  - longhorn-manager logs from the affected node
  - related events
  - check Longhorn version against known fixes
  - check replica scheduling capacity + offline-rebuilding settings

- [ ] **Replace drill #3's bogus-repo-path test with a unit test**. In the
  pvc-plumber repo, add a test that injects a failing executor and asserts
  `decision=unknown, authoritative=false` is returned by `CheckBackupExists`.

## Action items — followup work (not blocking commit)

- [ ] **Surgical-restore runbook entry** in `docs/backup-restore.md` (or
  `infrastructure/controllers/kyverno/CLAUDE.md`) pointing at the safe
  procedure documented in the drill results doc.

- [ ] **Future schedule-stagger upgrade**: when crossing ~50 backup-labeled
  PVCs, swap the length-based template for a sha256-derived minute. The
  Kyverno expression is feasible (`truncate(sha256(...), N)` with hex-decode
  + modulo) but messy in JMESPath; cleaner if scheduling moves into the
  future protected-pvc-controller.

## Commit decision (unchanged)

Ship the full batch as planned. The corrections above land in the same
commit; the post-sync action items are followups, not blockers.
