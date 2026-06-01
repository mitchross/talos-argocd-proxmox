# Documentation archive 🗄️

> [!WARNING]
> **Everything under `docs/archive/` is historical.** It is preserved for context — *why* the current
> design exists, what was tried, how the migration unfolded — but it is **not** current operating
> guidance. Do not follow these as runbooks. Start at the [docs index](../index.md) or
> [pvc-plumber-start-here](../pvc-plumber-start-here.md).

## What's current (do this instead)

| Need | Current doc |
|---|---|
| Understand pvc-plumber | [pvc-plumber-start-here](../pvc-plumber-start-here.md) |
| Quick reference | [pvc-plumber-cheatsheet](../pvc-plumber-cheatsheet.md) |
| How the operator decides | [pvc-plumber-dynamic-workflow](../pvc-plumber-dynamic-workflow.md) |
| Use it in this repo | [talos-argocd-pvc-plumber-integration](../talos-argocd-pvc-plumber-integration.md) |
| Backup/restore + drills | [volsync-storage-recovery](../volsync-storage-recovery.md) |
| Design / PRD | [pvc-plumber-v4-prd](../pvc-plumber-v4-prd.md) (see §0 canonical status) |

## What's in here

```text
archive/pvc-plumber/
  migration-campaign/   # pre-v4 cutovers, DR inventories/validation, point-in-time audits
  incidents/            # the nginx-canary incident record
  historical-design/    # superseded design specs (adopt-CLI, etc.)
  presentations/        # explainer/presentation/walkthrough — superseded by the visual docs
  inventories/          # point-in-time PVC inventory snapshots
```

## Also historical, but left in their existing locations (already segregated)

These were already organized into clearly non-current subdirectories and are **not** part of the
top-level current docs. Treat them as historical too:

- **`docs/research/**`** — design reviews, ecosystem research, the pvc-backup-simplification proposal, DR-drill notes.
- **`docs/plans/**`** — older project/operator plans (incl. the v3 operator design + v3 roadmap).
- **`docs/superpowers/**`** — older migration planning notes.

## Current state (as of 2026-06-01)

- pvc-plumber **v4.0.1** live (permissive). **24 PVCs / 18 namespaces** managed. **24/24 DR_COMPLETE.**
- Kyverno **removed** from the backup path. CNPG native/Barman. PostHog backup-exempt. redis-instance **backup-exempt**.
- Migration campaign **closed** — no remaining candidates.
