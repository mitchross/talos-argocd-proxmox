# Migration plan — full pvc-plumber decommission to author-spec + MAP

Status: PROPOSAL on exploratory branch (`claude/analyze-k8s-backup-transcript-eRrS2`). Not for merge. No PR.
Date: 2026-05-21. Read `00-compare-and-contrast.md` first, then `proposal/README.md`.

**Direction is locked**: full migration to mirceanton-style declarative
VolSync (per-app Helm chart) + a single cluster-scoped MAP that fail-closes
mover Jobs on hard-unreachable backend. pvc-plumber operator goes away
entirely. The soft "authoritative no-snapshot" failure class is consciously
accepted as future-burn (Kopia append-only + `restoreAsOf` recoverability
mitigates it).

---

## MUST-HAVES (non-negotiable; violating any aborts the migration)

1. **Kopia repo-name continuity.** Every chart-rendered ES/RS/RD MUST use
   `volsync-<pvc>` (chart `repositoryPrefix: volsync-`). The 26 existing
   lineages are addressed by that name. A prefix change orphans all backup
   history — unrecoverable. Verified per-app in T3.
2. **Cluster MAP + Talos patch deployed BEFORE per-app migration.**
   `proposal/cluster/talos-patch.yaml` (Omni rolling apply) then
   `proposal/cluster/mutating-admission-policy.yaml` (kubectl/Argo).
   Verified by T7. Without the MAP the migration is operating under
   author-spec's accidental fail-closed (Restic-side, untested on Kopia
   here) — acceptable for best-effort tier, NOT acceptable for strict.
3. **Avoid double-management.** A PVC must never be simultaneously
   reconciled by pvc-plumber AND chart-managed (two RS on one PVC = racing
   snapshots / retention fights). The chart uses *different* object names
   from pvc-plumber (RS = `<pvc>` vs pvc-plumber's `<pvc>-backup`; RD =
   `<pvc>-dst` vs `<pvc>-backup`) so both can transiently exist without
   colliding by name — but they'd still race on the same Kopia repo
   identity. Cutover per-PVC (see Phase 2/3): apply chart resources with
   schedule paused → confirm → drop `backup:` label so pvc-plumber's
   reconciler `cleanup()` releases its RS/RD/ES → enable chart RS schedule.
4. **CNPG untouched.** Database PVCs are Barman→S3, never in scope. No
   `backup:`/chart wiring on them. (CLAUDE.md rule.)
5. **System-namespace exclusions: not needed.** The MAP scopes itself to
   Jobs whose name starts `volsync-src-`/`volsync-dst-` AND labelled
   `app.kubernetes.io/created-by=volsync` — not by namespace. The
   cluster-wide PVC-admission blast radius pattern that pvc-plumber's
   webhook had structurally cannot recur here.

---

## RESOLVED OPEN DECISIONS

| Decision | Resolution | Where |
|---|---|---|
| **D1** Taskfile manual DR ergonomics | **Port them** (suspend/resume Argo, throwaway kopia pod, manual RD trigger, `restoreAsOf` point-in-time) | `proposal/ops/` |
| **D2** Failure visibility buy-back | **MAP-based init container** on mover Jobs (Option C in compare §6) | `proposal/cluster/` |
| **D3** Chart owns PVC vs app keeps it | **App keeps `pvc.yaml`** during migration (smaller diff, easier rollback). Flip to chart-owned for new apps post-migration if desired. | `proposal/chart/values.yaml` `pvc_create: false` default |

---

## RISKS / OPEN PROBLEMS

- **R1 (blocker — T5):** pvc-plumber's reconciler `cleanup()` reaps ES/RS/RD
  by label `volsync.backup/pvc=<pvc>`. The chart uses the same label. If
  the chart-rendered resources also carry that label, pvc-plumber may
  delete them when the source `backup:` label is dropped. Mitigation
  options: (a) chart uses a *different* owner label and drops
  `volsync.backup/pvc`; (b) scale pvc-plumber reconciler to 0 before
  relabeling; (c) decommission pvc-plumber Deployment *before* the last
  per-app relabel (the chart resources are then safe — but the webhook
  needs to come down first or those PVC creates would be denied). T5
  selects.
- **R2:** exact per-PVC Kopia mover Secret schema (KOPIA_REPOSITORY vs
  discrete KOPIA_S3_*). T1 resolves; chart includes both and is marked
  VALIDATE-AGAINST-LIVE.
- **R3:** schedule minutes shift (chart uses adler32 vs operator's sha256).
  Spread preserved, individual times change → first post-migration run at a
  new minute. Cosmetic; pin via `schedule:` for anything sensitive.
- **R4:** the MAP backend probe is hardcoded to `192.168.10.133:30293`
  (RustFS endpoint). If RustFS moves, the MAP needs updating in lockstep.
  No templating — accept it (it's one place, the IP changes rarely).
- **R5 — original-burn reproducibility:** author reports "I use volsync to
  back up SQLite and never ran into" the corruption-on-restore burn that
  motivated pvc-plumber. T3 includes a sub-test on a previously-burned
  SQLite app (Karakeep, an *arr) under the new pattern. If it reproduces,
  the migration model has a real failure we did not anticipate and Phase 3
  pauses. If not, the burn was Kyverno/timing-specific and the new pattern
  is genuinely safer in shape, not just simpler.

---

## PHASING

### Phase 0 — Cluster preparation (no per-app changes)
1. Apply `proposal/cluster/talos-patch.yaml` via Omni (rolling control-plane
   reboot enables MAP feature gate). Verify with `kubectl api-resources |
   grep mutatingadmissionpolic`.
2. Apply `proposal/cluster/` via kubectl or move to ArgoCD-managed.
   Verify MAP+Binding exist with `kubectl get mutatingadmissionpolicy,
   mutatingadmissionpolicybinding`.
3. Run **T7** (MAP fail-closed on unreachable RustFS) in `vb-test` ns.
4. Run **T1** (per-PVC Kopia mover Secret schema). Reconcile chart if needed.
5. Run **T5** (cleanup-label interaction with pvc-plumber). Decide R1.

Exit criteria: T7 = MAP correctly fails Jobs; T1 = chart Secret keys match
live; T5 = safe relabel procedure known.

T2 is no longer the gate — the MAP fail-closes mover Jobs independent of
populator behaviour. T2 remains as an *alignment check* (good to know) but
not a Phase blocker.

### Phase 1 — Pilot (one best-effort app)
- Pick a disposable, reproducible app currently labeled `backup:`. **Not**
  SQLite-bearing yet (that comes in Phase 3 R5 sub-test).
- Apply chart `helmCharts:` entry. Initially set chart RS `schedule:` to
  pause (`spec.trigger.manual` only, no schedule field) so it doesn't race
  pvc-plumber's RS.
- Manually trigger one backup via `task volsync:backup`. Verify lands in
  the **same Kopia lineage** (continuity proof). Verify restore round-trips
  via `task volsync:restore`.
- Drop `backup:` label per T5 procedure (pvc-plumber cleans its `<pvc>-backup`
  RS/RD/ES; chart's `<pvc>` / `<pvc>-dst` survive).
- Enable schedule on chart RS. Bake for 1 week, verify scheduled snapshots.

### Phase 2 — Best-effort fleet
- Migrate remaining best-effort-classifiable PVCs in small batches (≤5/batch)
  through the same cutover sequence as Phase 1. T3 per app.

### Phase 3 — Strict tier + the burn sub-test
- Pick one previously-burned SQLite app first (R5 sub-test). Full restore
  drill: delete PVC → populator restores → app comes up with DB intact.
  If corruption reproduces, **STOP** and triage; if not, proceed.
- Migrate remaining source-of-truth PVCs (\*arr, embedded-SQLite,
  user-content apps). Each: T3 + explicit DR rehearsal.

### Phase 4 — Decommission pvc-plumber
- Pre-condition: `kubectl get pvc -A -l backup` returns nothing pvc-plumber
  still owns; every backup-labeled PVC has been chart-migrated.
- Order:
  1. Delete the **MutatingWebhookConfiguration + ValidatingWebhookConfigurations** first (`infrastructure/controllers/pvc-plumber/webhooks.yaml`). This removes the cluster-wide SPOF immediately. Apps can still create labeled PVCs (the chart no longer needs the label for restore-vs-fresh; it uses static `dataSourceRef`).
  2. Delete the Deployment / RBAC / cert / per-operator ExternalSecret.
  3. Remove `pvc-plumber-app.yaml` from `infrastructure/controllers/argocd/apps/`. Argo will prune.
  4. Keep `infrastructure/controllers/pvc-plumber/` in git for one release for rollback. Then delete.
- Doc sweep: rewrite `docs/volsync-storage-recovery.md`, archive
  `docs/pvc-plumber-*.md` (link from a deprecation note), update
  `.claude/commands/add-backup.md` to the chart workflow, update root +
  `my-apps/` + `infrastructure/` CLAUDE.md backup sections, drop the
  pvc-plumber debug commands from `infrastructure/CLAUDE.md`.

### Rollback (any phase before Phase 4)
Per-PVC: remove `helmCharts:` entry + static `dataSourceRef`; re-add
`backup:` label; pvc-plumber reconciler re-adopts (stateless — re-derives
from the label). Because the Kopia repo name is unchanged, **no backup
history is lost on rollback.** Reversibility is *why* the repo-name
MUST-HAVE is non-negotiable. Post-Phase 4 rollback requires re-applying
pvc-plumber from git history.

---

## DEFINITION OF DONE (this branch — study deliverable)
- [x] Declarative chart that reproduces ES/RS/RD with repo-name continuity.
- [x] MAP + Talos patch for backend-availability fail-closed.
- [x] Worked per-app example (open-webui) showing exact before/after.
- [x] DR Taskfile + ported scripts (snapshots, backup, restore w/ `restoreAsOf`).
- [x] Compare/contrast finalised with author Discord follow-up + MAP option.
- [x] Migration plan finalised with all decisions resolved.
- [x] Test plan covering T1/T2/T3/T4/T5/T7 + R5 burn sub-test.
- [ ] T1/T5/T7 executed against live cluster (cannot be done from here).
- [ ] Phase 0 cluster prep merged into `infrastructure/storage/` (post-branch).
- [ ] Per-app migrations executed (Phases 1–3, post-branch).
- [ ] pvc-plumber decommissioned (Phase 4, post-branch).
