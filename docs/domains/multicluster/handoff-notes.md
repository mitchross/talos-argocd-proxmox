# Multi-Cluster PRD — Handoff Notes

> Status: TODO / for later. Companion to [`prd.md`](prd.md) (the Talos + OpenShift SNO fleet). The PRD is the spec; this file is the posture for whoever picks it up.

## Opening prompt (forces reconcile-first)

> "Read `docs/domains/multicluster/prd.md`, then read the current repo and tell me where the repo differs from the PRD's assumptions before doing anything. Then propose a Phase 1 plan and ask me any open questions."

The PRD was written partly blind (no live-repo access during planning). Every phase starts by reading the real repo and reconciling — treat the PRD as a brief, not gospel. See PRD §"Open questions" for the specific things to verify (ArgoCD CR schema field, backup design, AppSet syntax, Cilium gateway name).

## Known-stale point

**Backup design.** The PRD originally assumed a Kyverno/pvc-plumber backup path. That stack is **retired** — backups are now **kopiur** (Kopia-native: per-PVC `kopiur-backup` component + `dataSourceRef` → `Restore`). Reconcile Phase 5 against the live kopiur setup and `CLAUDE.md`; do not resurrect Kyverno, pvc-plumber, or VolSync.

## Highest-risk action

**Phase 4 — Talos migration into `clusters/talos/`.** The one step that touches the ~200 live apps. Gate: rendered Applications must be **identical before/after** so ArgoCD adopts rather than recreates. Run the dry-diff validation on a branch **before merging**. Deferrable — do not let it barrel ahead.

## TODO when work resumes

- [ ] Run the opening prompt against a fresh session.
- [ ] Reconcile PRD open questions against the live repo (ArgoCD CR field, kopiur backup design, AppSet syntax, Cilium gateway name).
- [ ] Open a PR updating `prd.md` to match reconciled reality.
- [ ] Treat Phase 4 as gated on a verified before/after rendered-Application dry diff on a branch.
