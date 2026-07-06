# kopiur backup architecture — the instruction manual

> How the pieces fit together for backup **and** restore, and which part lives
> where. If you're new to Kustomize **components**, start at §2 — that's the bit
> that trips people up. Permissions deep-dive: [`kopiur-mover-permissions.md`](kopiur-mover-permissions.md).

kopiur is the cluster's backup system: a Kopia-native operator. You declare small
CRs, it runs Jobs, kopia moves bytes to RustFS.

## Lifecycle and Flows

<div class="grid cards" markdown>

-   **1. GitOps & Kustomize Assembly**

    `Build time`

    1. The **app stub** declares the policy, schedule, restore target, and mover
       UID:GID.
    2. The shared **kopiur component** adds the repository, copy method, and
       volume-populator settings.
    3. **ArgoCD** combines both with Kustomize and applies the rendered resources
       to Kubernetes.

-   **2. Scheduled Backup**

    `Runtime`

    1. A **SnapshotSchedule** creates a Snapshot custom resource.
    2. The **kopiur operator** takes a Longhorn CSI snapshot and starts a mover
       Job as the data owner.
    3. The mover reads S3 credentials from `kopiur-rustfs` and uploads encrypted,
       deduplicated data to `s3://kopiur`.

-   **3. Restore Before Bind**

    `Disaster recovery`

    1. **ArgoCD** recreates a PVC that references a kopiur Restore.
    2. Kubernetes keeps the PVC `Pending` while the **restore populator** starts
       a mover Job.
    3. The mover restores data from RustFS; only then does Kubernetes bind the
       PVC and start the application.

</div>

---

## 1. The pieces (what exists, and where)

**Cluster-wide — set up once**

- `infrastructure/controllers/kopiur/` defines the `cluster-kopia` repository,
  the `kopiur-rustfs` credential fanout, and `longhorn-snapclass`.
- The operator in `kopiur-system` watches kopiur resources and runs snapshot and
  restore Jobs.
- `my-apps/common/kopiur-backup/` holds the shared Kustomize component.

**Per app — add for every protected PVC**

- Label `namespace.yaml` to receive repository credentials.
- Point `pvc.yaml` at the Restore with `dataSourceRef`.
- Add the `kopiur/<pvc>.yaml` stub.
- Include the stub under `resources:` and the shared component under
  `components:` in `kustomization.yaml`.

| Piece | Scope | What it does |
|---|---|---|
| `ClusterRepository cluster-kopia` | cluster | the kopia repo definition → RustFS `s3://kopiur` |
| `ClusterExternalSecret kopiur-rustfs` | cluster | fans the repo creds into any namespace labeled `kopiur.home-operations.com/repo: cluster-kopia` |
| `VolumeSnapshotClass longhorn-snapclass` | cluster | how CSI snapshots are taken (Longhorn) |
| kopiur operator | cluster | reconciles the CRs; launches the mover Jobs |
| **component** `common/kopiur-backup` | shared | injects the **uniform** fields into your stub |
| **stub** `kopiur/<pvc>.yaml` | per-PVC | the **varying** bits: name, identity, cron, **mover UID** |
| namespace label | per-app | turns on creds + repo access for that namespace |
| PVC `dataSourceRef` | per-PVC | wires restore-before-bind to the `Restore` |

---

## 2. How a Kustomize component composes (read this if components are new)

A **component** is a reusable bundle of patches. Your app's `kustomization.yaml`
"pulls it in" with `components:`. At build time Kustomize takes the resources you
list, then lets the component **patch** them. So the per-PVC stub stays tiny (just
the bits that differ); the component fills in everything that's the same for every
backup.

```yaml
resources:
  - namespace.yaml
  - pvc.yaml
  - kopiur/<pvc>.yaml
components:
  - ../../common/kopiur-backup
```

| Resource | App stub supplies | Component adds |
|---|---|---|
| `SnapshotPolicy` | name, source PVC, identity, retention, mover UID:GID | repository, `copyMethod: Snapshot`, `volumeSnapshotClassName` |
| `SnapshotSchedule` | cron schedule | `concurrencyPolicy: Forbid`, `runOnCreate: false` |
| `Restore` | source policy, mover UID:GID | repository, `target.populator`, `onMissingSnapshot: Continue` |

`kubectl kustomize <app>` combines both sets of fields into the complete custom
resources that ArgoCD applies.

**Keep the mover UID in the stub, not the component:** it varies per PVC (the
data owner differs app to app — even within one namespace), and a component
patches *all* resources of a kind the same way, so it can't set a per-PVC value.
The component sets only what's identical everywhere.

---

## 3. Backup flow (what happens on a schedule)

1. A `SnapshotSchedule` fires on its cron, for example `10 3 * * *`, and creates
   a Snapshot custom resource.
2. The kopiur operator creates a point-in-time CSI `VolumeSnapshot` through
   `longhorn-snapclass`.
3. The operator launches a mover Job as the data owner UID:GID and mounts the
   snapshot read-only.
4. The mover reads S3 credentials from the local `kopiur-rustfs` Secret, which
   the `ClusterExternalSecret` placed in the namespace.
5. Kopia uploads deduplicated, encrypted data to RustFS at `s3://kopiur`, then
   marks the Snapshot `Completed` with its file and byte counts.

The mover must run as the **data owner** or it can't read the files — see
[`kopiur-mover-permissions.md`](kopiur-mover-permissions.md).

A backup against an unreachable repo errors: the Snapshot Job fails and retries,
nothing garbage is written.

---

## 4. Restore-before-bind flow (the DR magic)

The whole point: when a PVC is recreated, it does **not** come up empty — it
holds at `Pending` until kopiur restores its data, *then* binds.

1. ArgoCD recreates the PVC from Git after a PVC deletion, namespace recreation,
   or full disaster recovery.
2. The PVC's `dataSourceRef` points to `<pvc>-restore`, so Kubernetes withholds
   binding and leaves the PVC `Pending`.
3. The kopiur restore populator checks the repository and decides how to proceed.

| Repository state | Result |
|---|---|
| Reachable, snapshot exists | A mover restores the data, the PVC binds, and the pod starts. |
| Reachable, no snapshot yet | `onMissingSnapshot: Continue` binds an empty PVC, which backs up forward. |
| Unreachable | The restore errors and retries; the PVC stays `Pending` and never binds empty. |

> A restore against an unreachable repo leaves the PVC `Pending` — kopiur raises
> the backend error *before* the "no snapshot → empty" decision, so an outage can
> never bind an empty volume. (Source: `crates/controller/src/restore/mod.rs`
> `resolve_snapshot`.) `onMissingSnapshot: Continue` means a brand-new PVC with a
> *reachable* repo but no snapshot still binds empty and backs up forward —
> deploy-or-restore in one path.

---

## 5. To add a backup (checklist)

1. `kubectl -n <ns> exec <pod> -- stat -c '%u:%g' <data-mountpath>` → note the **owner uid:gid**.
2. Namespace: add label `kopiur.home-operations.com/repo: cluster-kopia` (+ the
   `privileged-movers` annotation only if owner is `0`).
3. Add `kopiur/<pvc>.yaml` stub (SnapshotPolicy + Schedule + Restore) with the
   mover set to that uid:gid; pick a distinct cron minute — check **both**
   tiers: an hourly `MM * * * *` occupies minute MM of *every* hour, so a
   daily `MM 3 * * *` with the same MM collides at 03:MM (caught in the
   2026-07-04 audit: mysql 03:25 vs meilisearch hourly :25). List the taken
   minutes before picking:
   ```bash
   grep -rh 'cron:' my-apps/*/*/kopiur* my-apps/*/*/*/kopiur* | sort
   ```
4. PVC: `dataSourceRef -> Restore/<pvc>-restore` + the two `ServerSide*` annotations
   (`argocd.argoproj.io/compare-options: ServerSideDiff=false` and
   `argocd.argoproj.io/sync-options: ServerSideApply=false` — the immutable-`dataSourceRef` diff mask).
   **Retrofitting a running app?** Expected: ArgoCD shows a
   `PVC is invalid: Forbidden` ComparisonError — `dataSourceRef` is immutable
   on a Bound PVC. Harmless: backups start immediately anyway, and the
   `dataSourceRef` arms on the next recreate (which is exactly what DR is).
   The annotations + AppSet `ignoreDifferences` mask the diff.
5. Kustomization: add the stub to `resources:` and `../../common/kopiur-backup` to `components:`.
6. Verify: `kubectl -n <ns> get snapshotpolicy,snapshotschedule,restore,snapshot,secret`.

Copy from [`my-apps/ai/open-webui/`](https://github.com/mitchross/talos-argocd-proxmox/tree/main/my-apps/ai/open-webui) (simple)
or [`my-apps/home/project-nomad/mysql/`](https://github.com/mitchross/talos-argocd-proxmox/tree/main/my-apps/home/project-nomad/mysql)
(daemon-drop uid `999:568`). Full step-by-step: [`.claude/commands/add-backup.md`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/.claude/commands/add-backup.md).

---

## 6. Upstream 0.5.x notes (assessed 2026-07-04, chart pinned `0.5.1`)

What changed upstream in 0.5.0/0.5.1 and how it lands here:

- **`copyMethod` now defaults to `Snapshot` upstream** (was `Direct`). We were
  already pinning `Snapshot` via the component — **keep the explicit pin**:
  upstream warns a server-defaulted field has no SSA field owner, so a GitOps
  re-apply of a manifest that *omits* the field can silently flip it on a CRD
  upgrade. Explicit value = owned field = immune. (Comment lives on the patch
  in `my-apps/common/kopiur-backup/kustomization.yaml`.)
- **`verification.quick` reshaped** to `{ schedule: { cron, jitter, timezone } }`
  (was a bare `{ cron, jitter }`). We don't use `verification` yet; if you add
  it, use the nested shape — the old shape is rejected on new writes.
  Verification is also now **gated on a verifiable snapshot existing** (no more
  verify-Job-fails-against-empty-repo on a fresh policy).
- **Metrics renamed / store-backed** (`kopiur_snapshot_*` →
  `kopiur_policy_last_backup_*`; `kopiur_resource_phase` emits active-only
  series). Irrelevant here today: the chart's ServiceMonitor/PrometheusRule/
  dashboard are all disabled and nothing in `monitoring/` scrapes kopiur metric
  names. If you ever enable scraping, use the new names.
- **`scheduleDefaults.timezone`** can now be set once on the
  `ClusterRepository` and every cron (backup schedules, verification,
  maintenance) inherits it. We deliberately stay on UTC — setting it would
  shift every existing schedule slot.
- **`failedJobsHistoryLimit`** on `SnapshotSchedule` (default 10) bounds failed
  `Snapshot` CRs; *succeeded* ones are pruned by the policy's GFS `retention` —
  which is why **every SnapshotPolicy must set `retention`** (audit-verified:
  all 22 do).
- **`files.ignoreRules` defaults** to OS-artifact junk (`/lost+found`,
  `System Volume Information`, `$RECYCLE.BIN`, `@eaDir`, `.snapshot`) — free
  win, no action.
- **`kubectl kopiur` CLI shipped in 0.5.1** (krew + Homebrew). Friendliest
  debugging surface for backup state — worth installing on workstations:
  `kubectl krew install kopiur`, then `kubectl kopiur --help`.
- **`credentialProjection` is heading for removal** (maintainer is migrating
  off it upstream). We never used it — the ESO `ClusterExternalSecret` fanout
  in `infrastructure/controllers/kopiur/externalsecret.yaml` is exactly the
  replacement pattern upstream recommends — so the eventual removal is a
  no-op here.
- **Known upstream race (#194):** in a namespace with the `privileged-movers`
  annotation, the grant event can be missed when namespace + CRs land together
  (DR cold-start), leaving `MoverPermitted=False` until a ~5 min backstop.
  Only the three root-mover namespaces (home-assistant, tubesync,
  nginx-example) qualify; the nudge is any no-op metadata touch on the CR.
  See the DR runbook.
- **Least-privilege reminder:** the `privileged-movers` annotation belongs
  ONLY on namespaces whose mover is elevated (uid 0, `runAsNonRoot: false`,
  added caps, or `privilegedMode`). The 2026-07-04 audit stripped it from 15
  namespaces where it had been blanket-copied during the VolSync migration.
