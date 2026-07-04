Add automatic backup to PVC(s) in `$ARGUMENTS`.

Backups are **kopiur** (replaced pvc-plumber + VolSync, retired 2026-06-27).
Each PVC gets a small `SnapshotPolicy` + `SnapshotSchedule` + `Restore` stub plus
the shared `my-apps/common/kopiur-backup` Kustomize component; kopiur runs the
Snapshot/Restore Jobs and kopia moves bytes to RustFS (`s3://kopiur`). Do NOT add
inline `ReplicationSource`/`ReplicationDestination` or pvc-plumber labels — those
are gone.

> Architecture + diagrams: `docs/domains/storage/kopiur-backup-architecture.md`.
> Why the mover runs as the data owner: `docs/domains/storage/kopiur-mover-permissions.md`.

## Steps

1. Identify the normal application PVCs that need protection. Confirm each uses
   `storageClassName: longhorn` (needs CSI VolumeSnapshot).

2. **Find the data owner uid:gid** — the mover MUST run as it (under baseline Pod
   Security a root mover can't read non-root/600/700 files):

   ```bash
   pod=$(kubectl -n <ns> get pod -l app.kubernetes.io/name=<app> -o name | head -1)
   kubectl -n <ns> exec "${pod#pod/}" -- stat -c '%u:%g' <data-mountpath>
   # also check files, not just the mount root (daemon-drop apps differ): find ... -printf '%u:%g\n'
   ```

3. **Namespace** — one label (creds fanout + repo tenancy). Add the annotation
   ONLY if the data owner is `0` (root):

   ```yaml
   metadata:
     labels:
       kopiur.home-operations.com/repo: cluster-kopia
     # annotations:                                       # root-owned data only
     #   kopiur.home-operations.com/privileged-movers: "true"
   ```

4. **Per-PVC stub** `kopiur/<pvc>.yaml` — varying bits only; mover = data owner:

   ```yaml
   ---
   apiVersion: kopiur.home-operations.com/v1alpha1
   kind: SnapshotPolicy
   metadata: { name: <pvc>, namespace: <ns> }
   spec:
     sources: [{ pvc: { name: <pvc> } }]
     identity: { username: <pvc>, hostname: <ns> }
     retention: { keepDaily: 14, keepWeekly: 6, keepMonthly: 3 }   # hourly: keepHourly:24,keepDaily:7,keepWeekly:4
     mover:
       securityContext: { runAsUser: <UID>, runAsGroup: <GID>, runAsNonRoot: true }   # root: {runAsUser:0,runAsNonRoot:false}
       podSecurityContext: { fsGroup: <GID>, supplementalGroups: [<GID>] }
   ---
   apiVersion: kopiur.home-operations.com/v1alpha1
   kind: SnapshotSchedule
   metadata: { name: <pvc>-daily, namespace: <ns> }
   spec: { policyRef: { name: <pvc> }, schedule: { cron: "MM 3 * * *" } }   # distinct minute vs ALL schedules — incl. hourly "MM * * * *" tiers (an hourly at :MM collides with a daily at 03:MM)
   # Taken minutes: grep -rh 'cron:' my-apps/*/*/kopiur* my-apps/*/*/*/kopiur* | sort
   ---
   apiVersion: kopiur.home-operations.com/v1alpha1
   kind: Restore
   metadata: { name: <pvc>-restore, namespace: <ns> }
   spec:
     source: { fromPolicy: { name: <pvc>, offset: 0 } }
     mover:
       securityContext: { runAsUser: <UID>, runAsGroup: <GID>, runAsNonRoot: true }
       podSecurityContext: { fsGroup: <GID>, supplementalGroups: [<GID>] }
   ```

   The component injects the uniform fields (`repository: cluster-kopia`,
   `copyMethod: Snapshot`, `volumeSnapshotClassName: longhorn-snapclass`,
   `target.populator: {}`, `onMissingSnapshot: Continue`, schedule
   `concurrencyPolicy: Forbid`/`runOnCreate: false`) — do not duplicate them.

5. **Kustomization** — add the stub + the component:

   ```yaml
   resources:
     - kopiur/<pvc>.yaml
   components:
     - ../../common/kopiur-backup
   ```

6. **PVC** — restore-before-bind via `dataSourceRef`, keep the masking annotations:

   ```yaml
   metadata:
     annotations:
       argocd.argoproj.io/compare-options: ServerSideDiff=false
       argocd.argoproj.io/sync-options: ServerSideApply=false
   spec:
     dataSourceRef:
       apiGroup: kopiur.home-operations.com
       kind: Restore
       name: <pvc>-restore
   ```

   (Helm-rendered PVC: inject the `dataSourceRef` + annotations via a Kustomize
   `patches:` block on the chart PVC — see `my-apps/development/gitea/`.)

   **Existing/Bound PVC?** ArgoCD will show a `PVC is invalid: Forbidden`
   ComparisonError — `dataSourceRef` is immutable on a Bound PVC. This is
   EXPECTED and harmless: backups start immediately; the `dataSourceRef` arms
   on the next recreate (i.e., at DR time). The masking annotations + AppSet
   `ignoreDifferences` handle the diff — do NOT try to "fix" it by recreating
   the PVC unless you actually want a restore drill.

7. Sync through GitOps and verify:

   ```bash
   kubectl -n <ns> get snapshotpolicy,snapshotschedule,restore
   kubectl -n <ns> get secret kopiur-rustfs      # fanned in by the ClusterExternalSecret
   kubectl -n <ns> get snapshot                  # Completed with non-zero files after first run
   ```

## Exclusions

Do not back up:

- CNPG database PVCs — CNPG uses native Barman/S3.
- Redis PVCs — backup-exempt, disposable.
- PostHog PVCs — backup-exempt, disposable.
- System-namespace PVCs.
- Non-Longhorn PVCs that can't use the CSI snapshot path.

For intentionally disposable PVCs, label `backup-exempt: "true"` + the
fully-qualified annotation `storage.vanillax.dev/backup-exempt-reason: "<reason>"`.

## References

- [`docs/domains/storage/kopiur-backup-architecture.md`](../../docs/domains/storage/kopiur-backup-architecture.md)
- [`docs/domains/storage/kopiur-mover-permissions.md`](../../docs/domains/storage/kopiur-mover-permissions.md)
- [`docs/disaster-recovery.md`](../../docs/disaster-recovery.md)
