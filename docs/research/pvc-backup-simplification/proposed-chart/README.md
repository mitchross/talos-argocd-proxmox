# volsync-backup chart (PROPOSAL — exploratory branch only)

Declarative replacement for pvc-plumber's reconciler. One release == one
backed-up PVC. Inflated per-app via Kustomize `helmCharts:` (ArgoCD already
has `kustomize.buildOptions: --enable-helm`, see
`infrastructure/controllers/argocd/values.yaml:30`).

> Eventual real home (NOT yet, this is a branch): `infrastructure/storage/volsync-backup/`.
> Today it lives under `docs/research/` so no ApplicationSet discovers it.

## What it renders

| Resource | Replaces (pvc-plumber) |
|---|---|
| `ExternalSecret volsync-<pvc>` | reconciler-generated per-PVC ES |
| `ReplicationSource <pvc>-backup` | reconciler-generated RS (schedule + retain) |
| `ReplicationDestination <pvc>-backup` | reconciler-generated RD (the populator) |
| *(optional)* the data PVC w/ static `dataSourceRef` | the **mutating webhook** (gone) |

What does NOT come back: reconciler, mutating webhook, the post-mutate race
check, the Bound+2h timer (pending T4), cluster-wide fail-closed (replaced by
optional per-tier residual webhook — Path B, out of scope here).

## Per-app usage — worked example: `my-apps/ai/open-webui`

Today (`pvc.yaml`):

```yaml
metadata:
  name: storage
  labels:
    backup: "daily"
spec:
  storageClassName: longhorn
  # dataSourceRef added dynamically by Kyverno/pvc-plumber
```

After (`pvc.yaml` — add the static ref + tier, drop the stale comment):

```yaml
metadata:
  name: storage
  labels:
    backup: "daily"
    restore-policy: "strict"
spec:
  storageClassName: longhorn
  dataSourceRef:
    apiGroup: volsync.backube
    kind: ReplicationDestination
    name: storage-backup
```

`kustomization.yaml` (add a `helmCharts:` entry — chart renders ES/RS/RD):

```yaml
helmCharts:
- name: volsync-backup
  path: ../../../docs/research/pvc-backup-simplification/proposed-chart  # branch path
  releaseName: open-webui-storage-backup
  namespace: open-webui
  valuesInline:
    pvc: storage
    namespace: open-webui
    frequency: daily
    tier: strict
    pvc_spec:
      storage: 10Gi
```

Two backed-up PVCs in one app = two `helmCharts:` entries with distinct
`releaseName` + `pvc`.

`pvc_create: true` instead lets the chart own the PVC (closest to
mirceanton — app deletes its own `pvc.yaml`).

## Continuity guarantee (do not break)

`repositoryPrefix: volsync-` makes the Kopia repo + secret name
`volsync-<pvc>`, **identical** to pvc-plumber. The 26 existing lineages stay
restorable. Changing the prefix orphans every backup — see
`../migration-plan.md` MUST-HAVE #1.

## Not yet validated (see ../test-plan.md)

- T1: exact per-PVC secret key schema vs the live perfectra1n Kopia mover.
- T2: RD behaviour on unreachable backend (Pending vs binds-empty) — the gate.
- T4: whether the Bound+2h guard is still needed.
