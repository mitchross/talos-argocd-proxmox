# Multi-Cluster PRD — Handoff Notes & TODO

> **Status: TODO / for later.** This is the companion handoff brief for
> [`prd.md`](prd.md) (the Talos + OpenShift SNO
> heterogeneous fleet PRD). The PRD body is the spec; this file captures the
> *reviewer's caveats and the intended working style* so whoever picks this up
> later (likely a fresh Claude Code session) starts with the right posture.
>
> Captured 2026-06-01.

---

## Recommended opening prompt (forces reconcile-first behavior)

> "Read `docs/domains/multicluster/prd.md`, then read the current repo and tell me where
> the repo differs from the PRD's assumptions before doing anything. Then propose
> a Phase 1 plan and ask me any open questions."

The PRD was written **partly blind** (no live-repo access during planning). Its
first job in every phase is to read the real repo and **reconcile**, treating the
PRD as a brief, not gospel.

## What was deliberately built into the PRD to make the agent re-prompt

- **Header caveat** — states the doc was written without live-repo access and
  that the agent's first job each phase is to read the real repo and reconcile.
  Treat the PRD as a brief, not gospel.
- **§5 "Open Questions to Resolve Against the Live Repo"** — lists things that
  could not be verified during planning: the ArgoCD CR schema field, the current
  post-Kyverno PVC-plumber design, the exact AppSet syntax, the Cilium gateway
  name. The agent should go look or ask rather than assume.
- **§7 "Working Style"** — explicitly instructs: ask focused questions at
  decision points and before any destructive/structural change; work in small
  reviewable commits on a branch; validate with `kustomize build` /
  `argocd appset generate` / dry diffs before applying. Re-prompting is named as
  the intended workflow.
- **Per-phase acceptance criteria** — so both the agent and the human know when a
  chunk is truly done before moving on.

## Known-stale points (flagged honestly)

The PRD encodes an understanding proven stale on at least two points:

1. **Kyverno removal / PVC-plumber rework.** The PVC backup/safety design has
   moved on (Kyverno admission webhook → MutatingAdmissionPolicy + pvc-plumber
   v4). The PRD's assumptions here are out of date. See §5 #2, §6, and Phase 5 in
   the PRD; reconcile against the live repo and current `CLAUDE.md` / pvc-plumber
   docs.
2. **General repo evolution** since the public index was last crawled. When the
   agent reads the live tree it may find more divergence. That is expected and is
   the whole reason for the hand-off-to-Claude-Code approach. **Let the agent
   correct the PRD against reality** — consider having it open a quick PR updating
   the PRD itself once it has read the repo, so the doc stays true.

## Highest-risk action in the whole plan

**Phase 4 — Talos ArgoCD-CR migration.** Marked deferrable because it is the one
step that touches the ~200 live apps. The acceptance gate is:

> **Rendered Applications must be byte-identical before/after.**

Make sure the agent actually runs that dry-diff validation on a branch **before
merging**. This is the single highest-risk change in the plan — do not let it
barrel ahead.

---

## TODO checklist when this work resumes

- [ ] Run the recommended opening prompt against a fresh session.
- [ ] Reconcile PRD §5 open questions against the live repo (ArgoCD CR field,
      pvc-plumber v4 design, AppSet syntax, Cilium gateway name).
- [ ] Have the agent open a PR updating `docs/domains/multicluster/prd.md` to match the
      reconciled reality.
- [ ] Treat Phase 4 (Talos migration) as gated on a verified before/after
      rendered-Application dry diff on a branch.
