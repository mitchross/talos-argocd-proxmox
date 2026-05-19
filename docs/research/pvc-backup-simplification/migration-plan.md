# Migration plan — pvc-plumber → declarative VolSync (author-spec)

Status: PROPOSAL on exploratory branch. Not for merge. No PR.
Date: 2026-05-19. Read `00-compare-and-contrast.md` and `test-plan.md` first.

Goal: get as close to mirceanton's operator-free model as ArgoCD allows,
keeping the things that genuinely earn their keep, and **never silently
losing data during the migration itself.**

---

## MUST-HAVES (non-negotiable; violating any aborts the migration)

1. **Kopia repo-name continuity.** Every chart-rendered RS/RD/ES MUST use
   `volsync-<pvc>` (chart `repositoryPrefix: volsync-`). The 26 existing
   lineages are addressed by that name. A prefix change orphans all backup
   history — unrecoverable. Verified per-app in T3.
2. **T2 gate before any strict-tier PVC migrates.** Do not point a
   source-of-truth PVC at the declarative populator until the unreachable-
   backend behaviour (Pending vs binds-empty) is empirically confirmed on
   the perfectra1n Kopia fork. The author's "stays Pending" is Restic +
   untested. This is the single gating test.
3. **No flag-day.** pvc-plumber and the chart MUST coexist during cutover.
   Migrate **one low-stakes best-effort app first**, prove backup+restore,
   then proceed. pvc-plumber stays fully deployed until the last app is off
   it.
4. **Avoid double-management.** A PVC must never be simultaneously
   reconciled by pvc-plumber AND chart-managed (two RS on one PVC = racing
   snapshots / retention fights). Cutover per-PVC is: chart-render →
   verify → *then* drop the `backup:` label so pvc-plumber's reconciler
   `cleanup()` releases it (it reaps by `volsync.backup/pvc=` label —
   confirm the chart's RS/RD survive cleanup, see RISK R1).
5. **CNPG untouched.** Database PVCs are Barman→S3, never in scope. No
   `backup:`/chart wiring on them. (CLAUDE.md rule.)
6. **System-namespace exclusions stay.** If any residual webhook is kept
   (Path B), its `namespaceSelector NotIn` list (kube-system, argocd,
   longhorn-system, volsync-system, …) is preserved verbatim.

---

## RISKS / OPEN PROBLEMS

- **R1 (blocker until tested):** pvc-plumber's reconciler `cleanup()` reaps
  ES/RS/RD by label `volsync.backup/pvc=<pvc>`. The chart uses the *same*
  label for continuity/observability — so dropping the `backup:` label
  could make pvc-plumber **delete the chart's resources**. Mitigation
  options to test in T5: (a) chart uses a *different* owner label and only
  keeps `volsync.backup/pvc` off; (b) scale pvc-plumber's reconciler to 0
  before relabeling; (c) decommission pvc-plumber entirely *before*
  relabeling (riskier — see phasing). **Unresolved; T5 decides.**
- **R2:** exact per-PVC secret schema for the perfectra1n Kopia mover
  (KOPIA_REPOSITORY vs discrete KOPIA_S3_*). T1 resolves; chart has both +
  a VALIDATE marker.
- **R3:** schedule minutes shift (adler32 vs operator's sha256). Spread
  preserved, individual times change → first post-migration run at a new
  minute. Cosmetic; documented; pin via `schedule:` for anything sensitive.
- **R4:** losing admission-time *visibility* (see compare §3). Not data
  loss, but a silently-Pending PVC is operationally worse than a loud deny.
  Decision D2 below.

---

## PHASING

### Phase 0 — Validate (no cluster changes that touch data)
- Run T1 (dump live ES/secret schema), reconcile chart templates.
- Run **T2** (the gate) in a scratch namespace.
- Run T5 (cleanup-label interaction) in a scratch namespace.
- Exit criteria: T1 reconciled, T2 = Pending-on-unreachable, T5 has a safe
  relabel procedure. **If T2 fails (binds empty), STOP** — author-spec is
  not safe for strict tier on this fork; fall back to Path B only.

### Phase 1 — Pilot (one best-effort app)
- Pick a disposable, NAS-backed or reproducible app (a `backup-exempt`-
  adjacent candidate that currently has `backup:`; NOT Sonarr/DB-bearing).
- Add `helmCharts:` entry, `restore-policy: best-effort`, keep pvc-plumber
  managing nothing for it yet.
- Verify: ES renders, RS runs on schedule, a manual RD restore round-trips
  (T3 per-app drill). Then relabel-off pvc-plumber per T5 procedure.
- Bake for 1 week. Confirm scheduled snapshots land in the same Kopia
  lineage (continuity proof).

### Phase 2 — Best-effort fleet
- Migrate remaining best-effort-classifiable PVCs in small batches
  (≤5/batch), each through T3. These are the ones for which author-spec's
  fail-open is an accepted, recoverable-until-prune risk (compare §5).

### Phase 3 — Strict tier
- Only after T2 has held in practice through Phases 1–2.
- Migrate source-of-truth PVCs (Sonarr/*arr, embedded-SQLite, anything
  where empty-over-good is unacceptable). Each: T3 drill + an explicit
  **DR rehearsal** (delete PVC, confirm populator restores real data, app
  comes up with history intact).
- Apply Decision D2 (visibility) before/with this phase.

### Phase 4 — Decommission pvc-plumber
- Only when `kubectl get pvc -A -l backup` returns nothing pvc-plumber
  still owns and every app is chart-managed.
- Order (reverse of deploy waves): delete webhooks FIRST (removes the
  cluster-wide SPOF), then Deployment/RBAC/cert/ES, then update
  `pvc-plumber-app.yaml` discovery. Keep `infrastructure/controllers/
  pvc-plumber/` in git one release for rollback, then remove.
- Update docs: `docs/volsync-storage-recovery.md`, `pvc-plumber-*.md`,
  `.claude/commands/add-backup.md`, root + `my-apps/` CLAUDE.md backup
  sections, `infrastructure/CLAUDE.md` debug commands.

### Rollback (any phase)
Per-PVC: re-add `backup:` label, remove `helmCharts:` entry + static
`dataSourceRef`; pvc-plumber reconciler re-adopts (it is stateless — it
re-derives from the label). Because the Kopia repo name is unchanged,
**no backup history is lost on rollback.** This reversibility is *why* the
repo-name MUST-HAVE is non-negotiable.

---

## OPEN DECISIONS (yours, not baked in)

- **D1 — Taskfile/manual DR ergonomics (your stated 50/50).**
  - *Port them* (recommended if Phase 3 proceeds): mirceanton's
    `volsync-*` scripts become Kopia/Argo equivalents (suspend auto-sync,
    throwaway kopia pod, manual RD trigger, point-in-time). Adds the one
    place his setup is ergonomically ahead; pure UX, operator-agnostic;
    valuable in *every* path.
  - *Leave automated*: rely on the declarative RD + populator only; DR is
    "delete PVC, let populator restore." Less to maintain; no
    point-in-time / pre-app-start manual gate.
  - Recommendation: **port them**, because Phase 3 strict-tier DR wants a
    human-gated "restore *this* point before the app starts" lever that the
    automated populator alone doesn't give. But this is a genuine judgement
    call — flagged, not decided.
- **D2 — Buy back failure *visibility* (compare §3, R4)?** Options:
  (a) nothing — accept silent Pending (closest to author);
  (b) **alerting-only** watcher: a small CronJob/PrometheusRule that fires
      when a `restore-policy: strict` PVC is Pending > N min (visibility,
      zero admission risk, no SPOF) — recommended middle;
  (c) **Path B** residual validate-only webhook on strict tier only (loud
      deny, reintroduces a *scoped* SPOF). Full design in
      `path-b-shrink-operator.md`.
- **D3 — chart owns PVC (`pvc_create: true`, closest to author) vs app
  keeps `pvc.yaml` + static ref (`false`, smaller per-app diff)?** Default
  in plan: `false` for migration (minimal blast radius), revisit to `true`
  for new apps post-migration.

---

## DEFINITION OF DONE (for this branch — it's a study deliverable)
- [x] Declarative chart that reproduces ES/RS/RD with repo-name continuity.
- [x] Worked per-app example (open-webui) showing exact before/after.
- [x] Compare/contrast with the author-reply analysis folded in.
- [x] Test plan with the explicit migration gate (T2).
- [x] Phased plan + must-haves + risks + rollback.
- [ ] D1/D2/D3 chosen by operator.
- [ ] T1/T2/T5 executed against a live cluster (cannot be done from here).
