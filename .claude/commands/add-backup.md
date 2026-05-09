Add automatic backup to PVC(s) in `$ARGUMENTS`.

## Steps

1. Find the PVC YAML file(s) in the specified app directory
2. Add the backup label to the PVC metadata:
   ```yaml
   metadata:
     labels:
       backup: "daily"  # or "hourly" for frequently changing data
   ```
3. Ensure `storageClassName: longhorn` is set (required for volumesnapshots)
4. Update `kustomization.yaml` if any new files were created

## Schedule Guide

- `backup: "hourly"` — every hour, for frequently changing data (photos, uploads, active databases)
- `backup: "daily"` — daily at 2am, for most apps

## What NOT to backup with this system

- **CNPG database PVCs** — they use Barman to S3, not VolSync
- System namespace PVCs (auto-excluded by the operator's webhook namespaceSelector)
- Temporary/cache data — use the `backup-exempt: "true"` label + `storage.vanillax.dev/backup-exempt-reason: "<reason>"` annotation to declare these intentionally
- Non-Longhorn PVCs (snapshot support required)

## Verification

After applying, the pvc-plumber v2 operator auto-generates backup resources:
```bash
kubectl get replicationsource,replicationdestination,externalsecret -n <namespace> \
  -l app.kubernetes.io/managed-by=pvc-plumber
```

## Removing Backups

Just remove the `backup` label (or add `backup-exempt: "true"` + a reason annotation if the intent is permanent exemption). The pvc-plumber operator's PVC reconciler `cleanup()` reaps orphaned ES/RS/RD resources by the `volsync.backup/pvc=<pvcname>` label on the next reconcile pass — no separate orphan-reaper CronJob.
