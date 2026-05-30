# pvc-plumber v4 — Roadmap (post-PRD working backlog)

Companion to [`pvc-plumber-v4-prd.md`](pvc-plumber-v4-prd.md). The PRD is the
locked design contract; this file is the working backlog for follow-ups that
were identified during execution but should not block the phased rollout.
Day-of cutover operations live in
[`pvc-plumber-v4-cutover.md`](pvc-plumber-v4-cutover.md); per-app status
lives in [`pvc-plumber-v4-inventory.md`](pvc-plumber-v4-inventory.md).

Each item carries an explicit start gate. **Do not begin work on an item until
its gate condition is met,** unless the user explicitly redirects.

## Completed

- **Patch 7.7 — operator volsync-writer RBAC + managed-namespace contract.**
  ClusterRole `pvc-plumber:volsync-writer` (`volsync.backube/replicationsources`
  and `replicationdestinations`: get/list/watch/create/patch/delete; no update,
  no status subresource writes, no PVC mutation, no Secret access, no Argo
  access). One per-namespace RoleBinding required per managed namespace; first
  managed namespace is `nginx-example`. Six-step preflight checklist in
  [`pvc-plumber-v4-cutover.md`](pvc-plumber-v4-cutover.md) gates inline RS/RD
  removal from Git. Driving incident: `nginx-example/storage`, 2026-05-27 —
  inline RS/RD were removed before operator-writer RBAC was in place, Argo
  selfHeal pruned them, operator could not recreate, PVC left without a
  backup chain.

- **rc6 — invalid-label-value fix (backup-identity moved to annotation;
  operator RS/RD creates now valid).**

- **rc7 — RS/RD watch + child→PVC reverse-map + self-heal requeue + /audit
  staleness (`age_seconds`/`stale`); nginx-example/storage canary completed
  operator-managed, first backup Successful 2026-05-29.**

- **v4.0.0 (final/stable) — 2026-05-29.** Promotes `v4.0.0-permissive-rc7`
  to the final non-RC release with no code change (both tags = commit
  `3c40a1f`). Image
  `ghcr.io/mitchross/pvc-plumber:4.0.0@sha256:93df441fc50a4bc90ce2f88544977ca7d96b72d0383d9cfa27f2efa5ae5726dd`
  live in the cluster (permissive mode). **Three app classes proven
  operator-managed:** (1) `nginx-example/storage` — demo/canary; (2)
  `homepage-dashboard/config` — low-risk real app; (3) `karakeep/data-pvc`
  + `karakeep/meilisearch-pvc` — high-risk app (hourly, non-568 mover,
  immutable-dsr defect) repaired via Option R and migrated at `tier=hourly`,
  both backups Successful, mover 1001→568 proven safe.

- **Karakeep Gate 3 — complete (2026-05-30, commit `93b2b5cb`).** Both
  Karakeep PVCs handed off to operator management at `tier=hourly` (cadence
  preserved) after the data-pvc immutable-`dataSourceRef` repair (Option R).
  Old pre-repair PV `pvc-4cb90a74-…` retained as rollback (do not delete
  until approved).

## Open items

### 1. Phase 6.9 / 7 — Visual explainer + interactive lifecycle guide

**Gate to start:** Phase 6 code complete AND the gating canary complete. The
gating/first canary was `nginx-example/storage` (NOT karakeep — karakeep was
never the gate; it has since been migrated separately, 2026-05-30).
`nginx-example/storage` completed under rc7
operator-managed, first backup Successful 2026-05-29, so **the gate is MET**.
With the operator in a known-good state, this can become the next priority.
Acceptable to start during downtime if no code/cluster work is pending.

**Why this matters:** the v4 design is small in surface but conceptually
dense (two-label fuse, ownership rules, audit/permissive distinction,
no-adoption posture). A public-facing visual explainer turns pvc-plumber
from "weird homelab operator" into something people can read and
understand without running away. Also unlocks a blog post / YouTube
walkthrough.

**Deliverables:**

1. **`docs/pvc-plumber-v4-explained.md`** — ELI5-first, technically
   accurate markdown explainer. Audience: homelab Kubernetes users,
   GitOps users, people who understand PVCs/VolSync a little but not
   the full system. Must cover:
   - The problem (verbose inline RS/RD, drift, DR timing, empty-PVC
     hazard)
   - Simple mental model: Argo → labels → pvc-plumber → VolSync →
     Kopia/RustFS, with Longhorn as the PVC layer
   - The label contract:
     - `pvc-plumber.io/enabled: "true"` — visibility / reporting
     - `pvc-plumber.io/tier: hourly|daily|weekly` — desired cadence
     - `pvc-plumber.io/manage-volsync: "true"` — the **write fuse**;
       absent = read-only even with enabled
     - Legacy `backup: hourly|daily` — reporting-only, never write
       eligibility
     - `backup-exempt: "true"` + the FQ
       `storage.vanillax.dev/backup-exempt-reason` annotation — wins
       over everything
   - Lifecycle: PVC in Git → Argo syncs → pvc-plumber parses → planner
     decides → audit reports OR permissive writes → VolSync backs up
     → future restore injection
   - Modes: audit (observe), permissive (bounded writes), enforce
     (future), strict (future), never/force (future restore policies)
   - Ownership model: only `app.kubernetes.io/managed-by=pvc-plumber`
     resources are write-eligible; inline-argo is observed; unmanaged
     is observed or human-review; no adoption in Phase 6; migration
     path is remove-inline-then-recreate
   - Current talos repo shape: RS=`<pvc>`, RD=`<pvc>-dst`, shared
     `volsync-kopia-repository` Secret, no per-PVC ExternalSecret,
     no `-backup` suffix
   - Karakeep canary writeup (filled in after the canary): before
     state, label diff, inline removal, operator-managed result,
     backup verification, restore result if tested, what went well /
     what broke / rollback notes

2. **`docs/visual/pvc-plumber-lifecycle.html`** — self-contained
   single-file HTML/CSS/JS explainer with **zero external network
   dependencies**. Vanilla, no framework. Dark-mode-friendly, readable
   on screen share, suitable for a YouTube walkthrough. Must include:
   - **Step-by-step lifecycle viewer**: clickable sequence (PVC in
     Git → Argo syncs → labels parsed → planner decides → builder
     renders → executor writes (if allowed) → VolSync backs up →
     future restore via `dataSourceRef`). Each step shows plain
     English, a tiny YAML snippet, responsible component, allowed /
     not-allowed actions.
   - **Mode toggle**: audit / permissive / future strict. Same PVC
     state, different action.
   - **Label toggle**: checkboxes for `enabled`, `manage-volsync`,
     legacy `backup`, `backup-exempt`. Shows resulting planner
     verdict (`skipped-not-opted-in` / `write-gate-missing` /
     `already-matches` / `would-create` / `skipped-exempt`).
   - **Ownership visual**: argocd-owned → observe only;
     pvc-plumber-owned → may update/delete; unmanaged → human
     review; absent → create only if enabled+manage.
   - **Safety callout cards**: why legacy doesn't write, why two
     labels exist, why no adoption in Phase 6, why no webhooks yet,
     why backup-exempt needs a reason, why permissive ≠ YOLO.

3. **Mermaid/ASCII diagrams in the markdown**:
   - Component map: `Argo → PVC labels → pvc-plumber → VolSync → Kopia/RustFS`
   - Planner decision flow: exempt? → parse errors? → opted in? →
     write gate? → owner? → create/update/delete/observe?
   - Migration flow: inline Git-owned → audit report → add v4 labels
     → remove inline RS/RD → pvc-plumber creates managed RS/RD

4. **Blog / YouTube outline section** in the markdown:
   - Why Kubernetes app restores are awkward with GitOps
   - Why plain VolSync YAML works but gets repetitive
   - The pvc-plumber idea
   - Safety-first rebuild: audit mode before writes
   - The two-label write fuse
   - The karakeep canary
   - What's next: restore injection and full DR drill

**Truth-in-claims rule (load-bearing):**

The explainer must clearly separate **what is implemented today**, **what is
currently in canary**, and **what is future work**. Use the phrasings:

- "Current" / "Today"
- "Phase 6" (for items shipped in the v4 audit-then-permissive rollout)
- "Future restore injection"
- "Future strict mode"

Do **not** imply any of the following are live unless they actually are at
publication time:
- webhooks enabled
- strict mode enabled
- full cluster nuke / restore validated
- every app migrated

If reality differs at publication time, the explainer is wrong and must be
held until reality catches up or the language is corrected.

---

(Add new backlog items below as they come up.)
