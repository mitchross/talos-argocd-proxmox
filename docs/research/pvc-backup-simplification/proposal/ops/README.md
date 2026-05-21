# Manual DR ergonomics — Taskfile + scripts

Port of the entire manual-DR shape from `mirceanton/home-ops`
(`.taskfiles/volsync.yaml` + `.scripts/volsync-*.sh`), with Flux → Argo and
Restic → Kopia substitutions.

| Task | Purpose | Equivalent author task |
|---|---|---|
| `task volsync:snapshots PVC=storage NS=open-webui` | List Kopia snapshots for a PVC's repo | `volsync:snapshots APP=...` |
| `task volsync:backup PVC=storage NS=open-webui` | Trigger a manual backup, wait for success | `volsync:backup APP=...` |
| `task volsync:restore PVC=storage NS=open-webui [TS=2026-05-15T03:00:00Z]` | Suspend Argo, scale to 0, trigger RD restore (optionally `restoreAsOf` TS), resume Argo | `volsync:restore APP=... [TS=...]` |

Why these still exist after the migration:

The chart + populator handle the **automatic** case (deploy → restore-if-
backup-exists-or-empty → done). These scripts handle the **manual** case
that the populator alone can't:

- Point-in-time recovery (`restoreAsOf TS`) — choose *which* snapshot.
- Restore over an existing PVC (the populator only runs at PVC creation;
  if the PVC is already bound to bad data, you need to manually scale the
  app down and patch the RD).
- On-demand "back up this PVC right now" between scheduled runs.

This is Decision D1 in `../../migration-plan.md` (Taskfile manual vs pure
automated) resolved as "port them" — keeping the human-gated lever the
populator doesn't give you.

## Argo vs Flux substitutions (the only non-trivial port)

| Author (Flux) | Here (Argo) |
|---|---|
| `flux suspend helmrelease <app>` | `argocd app set <app> --sync-policy none` |
| `flux resume helmrelease <app>` + `flux reconcile --force` | `argocd app set <app> --sync-policy automated && argocd app sync <app>` |
| App name == HelmRelease name | App name == ArgoCD Application name (script assumes `app == namespace`; adjust if your naming differs) |

## Object-name conventions (must match chart)

The scripts assume the chart's `vb.rsName` / `vb.rdName`:

- RS metadata.name = `<PVC>` (e.g. `storage`)
- RD metadata.name = `<PVC>-dst` (e.g. `storage-dst`)
- per-PVC mover secret = `volsync-<PVC>` (e.g. `volsync-storage`)

If you customise the chart's name helpers, update these scripts in lockstep.

## Eventual real home

`scripts/Taskfile.yaml` (or wire into the existing root Taskfile) +
`scripts/volsync-*.sh`. Today under `docs/research/` so nothing on the live
cluster picks it up.
