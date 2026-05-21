Add automatic backup to PVC(s) in `$ARGUMENTS`.

## Pattern (post-pvc-plumber decommission, 2026-05-21+)

Backups are no longer triggered by a `backup:` label + operator reconciler.
Each app now has an explicit `helmCharts:` entry that inflates the
`volsync-backup` chart at `infrastructure/storage/volsync-backup/`.

## Steps

1. **Identify the PVC(s)** in the specified app directory that need backup. Note `name`, `namespace`, `storage`, `storageClassName`, `accessModes`.

2. **Edit each PVC manifest:**
   - Add a `restore-policy: "strict"` label (or `"best-effort"` for disposable / reproducible data).
   - Add a static `dataSourceRef:` block pointing at `ReplicationDestination/<pvc>-dst`.
   - Strip any stale "dataSourceRef added dynamically by Kyverno/pvc-plumber" comment.

   ```yaml
   apiVersion: v1
   kind: PersistentVolumeClaim
   metadata:
     name: data
     namespace: my-app
     labels:
       app: my-app
       restore-policy: "strict"
   spec:
     accessModes:
       - ReadWriteOnce
     resources:
       requests:
         storage: 10Gi
     storageClassName: longhorn
     dataSourceRef:
       apiGroup: volsync.backube
       kind: ReplicationDestination
       name: data-dst
   ```

3. **Edit the app's `kustomization.yaml`:**
   - Add `helmGlobals.chartHome: ../../../infrastructure/storage/` (count `../` to reach `infrastructure/`).
   - Append a `helmCharts:` entry per backed-up PVC.

   ```yaml
   helmGlobals:
     chartHome: ../../../infrastructure/storage/
   helmCharts:
   - name: volsync-backup
     releaseName: my-app-data-backup
     namespace: my-app
     valuesInline:
       pvc: data
       namespace: my-app
       frequency: hourly          # or "daily" — defines the cron schedule
       tier: strict               # or "best-effort" — matches the restore-policy label
       pvc_create: false          # app keeps its own pvc.yaml
       pvc_spec:                  # mirrored from the PVC manifest above
         accessModes: ["ReadWriteOnce"]
         storage: 10Gi
         storageClassName: longhorn
   ```

   If the app already has a `helmCharts:` block (e.g. an upstream Helm chart), append the volsync-backup entry as another list item under the same `helmCharts:`, with matching indentation.

## Schedule Guide

- `frequency: "hourly"` — every hour (cron minute computed from adler32(ns/pvc) % 60), for frequently changing data.
- `frequency: "daily"` — daily at the computed minute past 02:00 UTC, for most apps.

## Restore-policy Guide

- `restore-policy: "strict"` — source-of-truth data.
- `restore-policy: "best-effort"` — disposable / reproducible (NAS-backed caches, model downloads).

## What NOT to backup with this system

- **CNPG database PVCs** — they use Barman to S3 in a separate code path. See `infrastructure/database/cloudnative-pg/`.
- System namespace PVCs.
- Temporary/cache data — use the `backup-exempt: "true"` label + the FULLY-QUALIFIED `storage.vanillax.dev/backup-exempt-reason: "<reason>"` annotation.
- Non-Longhorn PVCs (kopia mover needs CSI volume snapshots).

## Verification

```bash
# 1. Confirm chart rendered the per-PVC artifacts
kubectl get externalsecret,replicationsource.volsync.backube,replicationdestination.volsync.backube -n <ns>

# 2. Trigger a manual backup
kubectl patch replicationsource.volsync.backube <pvc> -n <ns> --type=merge \
  -p '{"spec":{"trigger":{"manual":"verify-'$(date +%s)'"}}}'

# 3. Watch the mover pod come up; confirm wait-for-rustfs init container ran
kubectl get pods -n <ns> -l app.kubernetes.io/created-by=volsync
kubectl logs -n <ns> <mover-pod> -c wait-for-rustfs

# 4. Confirm snapshot in the kopia repo
task volsync:snapshots PVC=<pvc> NS=<ns>
```

## Removing Backups

Remove the `helmCharts:` entry from the app's kustomization.yaml AND the `dataSourceRef:` from the PVC manifest. Optionally remove the `restore-policy:` label. ArgoCD prune will tear down the chart-rendered ES/RS/RD.

## Reference

- Migration design: `docs/research/pvc-backup-simplification/`
- Chart source: `infrastructure/storage/volsync-backup/`
- Cluster-wide safety interlock (MAP): `infrastructure/storage/volsync-backup-cluster/`
- Credential conventions: `docs/rustfs-credential-runbook.md`
- DR Taskfile + scripts: `docs/research/pvc-backup-simplification/proposal/ops/`
