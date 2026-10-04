# Glossary

**Purpose:** give each overloaded word in this repo one meaning.
**Status:** current. Docs, PR text, and agent replies use these meanings.

Several words here name two or three different things. "Restore" can mean a
kopiur `Restore` object or a manual recovery. "Repo" can mean Git or Kopia.
When a word has a second meaning, write the longer name from the table.

## Rules

1. Use the **Term** column exactly. Do not switch to a synonym.
2. When you mean something in the **Not this** column, use the name given there.
3. Write Kubernetes kinds in code style (`Restore`, `Snapshot`) when you mean
   the object, not the idea.

## Backup and restore

| Term | Means | Not this — say instead |
|---|---|---|
| **backup** | A kopiur `Snapshot` upload of one PVC to the Kopia repository | A Longhorn or CSI snapshot — say **CSI snapshot** |
| **CSI snapshot** | The point-in-time `VolumeSnapshot` (via `longhorn-snapclass`) that the mover reads from | A backup; it stays in the cluster |
| **`Snapshot`** | The kopiur object that records one backup run; it should reach `Succeeded` | A `VolumeSnapshot` — say **CSI snapshot** |
| **Kopia repository** | The encrypted backup store that `ClusterRepository cluster-kopia` points at, on RustFS `s3://kopiur` | The Git repo — say **Git repo** |
| **mover** | The Job that kopiur starts to copy data to or from the Kopia repository; it runs as the data owner uid:gid | The kopiur operator itself |
| **`Restore`** | The kopiur object that a PVC's `dataSourceRef` points at; it fills an empty PVC before it binds | A hand-run recovery — say **manual recovery** |
| **restore-before-bind** | The PVC stays `Pending` until the restore mover finishes, then it binds with the data in place | Restoring into a running app |
| **stub** | The per-PVC file `kopiur/<pvc>.yaml`: `SnapshotPolicy`, `SnapshotSchedule`, and `Restore` with the per-PVC values | The shared `kopiur-backup` Kustomize component |
| **backup-exempt** | A PVC labelled to have no backup, with the reason in `storage.vanillax.dev/backup-exempt-reason` | A PVC that is simply missing its stub |
| **restore canary** | `my-apps/system/restore-canary/`, which runs the real restore path on a test volume | Any other restore test |

## GitOps

| Term | Means | Not this — say instead |
|---|---|---|
| **Git repo** | This repository: the desired state | The Kopia repository |
| **Application** | An Argo CD `Application`; one per discovered directory | The workload it deploys — say **app** |
| **app** | The workload (Deployments, PVCs, routes) in one directory | The Argo CD object — say **Application** |
| **sync** | Argo CD applies Git's desired state to the cluster | A backup or data copy |
| **sync wave** | The order number on a root entrypoint (0–6) | An Argo CD sync of one Application |
| **Synced** | Argo CD status: live objects match Git | Healthy — that is a separate status |

## Policies

"Policy" alone is ambiguous here. Always name the kind.

| Say | Means |
|---|---|
| **`SnapshotPolicy`** | kopiur: what to back up, retention, mover uid:gid |
| **NetworkPolicy** | Cilium/Kubernetes traffic rules |
| **lifecycle policy** | RustFS bucket expiry rules in `infrastructure/backup/rustfs-lifecycle/` |

## Related

- [Kopiur backup architecture](domains/storage/kopiur-backup-architecture.md) — owns the backup and restore flow.
- [Root entrypoints and sync waves](domains/argocd/entrypoints.md) — owns wave order.
- [Documentation reader contract](documentation-standard.md) — owns the writing rules.
