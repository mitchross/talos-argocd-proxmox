# volsync-backup chart (PROPOSAL — exploratory branch only)

Per-app declarative replacement for pvc-plumber's reconciler. One release ==
one backed-up PVC. Inflated via Kustomize `helmCharts:` (ArgoCD already has
`kustomize.buildOptions: --enable-helm`, see
`infrastructure/controllers/argocd/values.yaml:30`).

Mirrors `mirceanton/home-ops/components/volsync/` 1:1 in shape:

| Author's file | Chart template |
|---|---|
| `external-secret.yaml` | `templates/externalsecret.yaml` |
| `replication-source.yaml` | `templates/replicationsource.yaml` |
| `replication-destination.yaml` | `templates/replicationdestination.yaml` |
| `pvc.yaml` | `templates/pvc.yaml` (optional, `pvc_create: true`) |

Only meaningful divergence from author's component: **Restic → Kopia** field
names (we run perfectra1n/volsync's Kopia mover) and the variable mechanism
(Helm values instead of Flux `postBuild.substitute`, since Argo has no
postBuild). Field-for-field translation:

| Author (Restic) | Here (Kopia) | Notes |
|---|---|---|
| `spec.restic.repository` | `spec.kopia.repository` | references mover Secret by name |
| `RESTIC_REPOSITORY` in Secret | `KOPIA_REPOSITORY` in Secret | `s3://volsync-kopia/volsync-<pvc>` |
| `RESTIC_PASSWORD` | `KOPIA_PASSWORD` | shared 1Password `rustfs.kopia_password` |
| RS name `${APP}` | RS name `<pvc>` (= `vb.rsName`) | identical to author |
| RD name `${APP}-dst` | RD name `<pvc>-dst` (= `vb.rdName`) | identical to author |
| schedule `0 */2 * * *` (fixed) | spread by adler32(ns/pvc) % 60 | parity with pvc-plumber's herd-avoidance |

> Eventual real home (NOT yet, this is a branch): `infrastructure/storage/volsync-backup/`.
> Today under `docs/research/` so no ApplicationSet discovers it.

## What it renders

| Resource | Replaces (pvc-plumber) |
|---|---|
| `ExternalSecret volsync-<pvc>` | reconciler-generated per-PVC ES |
| `ReplicationSource <pvc>` | reconciler-generated RS (schedule + retain) |
| `ReplicationDestination <pvc>-dst` | reconciler-generated RD (the populator) |
| *(optional)* the data PVC w/ static `dataSourceRef → <pvc>-dst` | the **mutating webhook** (gone) |

What does NOT come back: reconciler, mutating webhook, the post-mutate race
check, the Bound+2h timer (pending T4), the cluster-wide fail-closed-via-
PVC-admission (replaced by Job-level MAP — see `../cluster/`).

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

After (`pvc.yaml` — static ref + tier, drop the stale comment):

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
    name: storage-dst        # = chart's vb.rdName
```

`kustomization.yaml` (add the `helmCharts:` entry):

```yaml
helmCharts:
- name: volsync-backup
  path: ../../../docs/research/pvc-backup-simplification/proposal/chart  # branch path
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
`releaseName` + `pvc`. `pvc_create: true` lets the chart own the PVC (the
mirceanton-closest shape — app deletes its own `pvc.yaml`).

## Continuity guarantee (do not break)

`repositoryPrefix: volsync-` → Kopia repo + mover-secret name `volsync-<pvc>`,
**identical** to pvc-plumber. The 26 existing lineages stay restorable. RS/RD
*object* names change (to `<pvc>` / `<pvc>-dst`) — that's safe; nothing
external references them by name, and the Kopia repo identity is what
preserves backup history. Changing the prefix orphans every backup; see
`../../migration-plan.md` MUST-HAVE #1.

## Not yet validated (see `../../test-plan.md`)

- **T1** — per-PVC secret key schema vs the live perfectra1n Kopia mover.
- **T2** — populator behaviour on hard-unreachable backend (Pending vs
  binds-empty). Less critical with the MAP in place (the MAP fail-closes
  the mover Job regardless), but still worth confirming.
- **T4** — whether the Bound+2h guard is still needed under the populator.
- **T7** — the cluster MAP actually fails Jobs when RustFS is unreachable.
