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

- **CNPG database PVCs** — they use Barman to S3, not Kyverno/VolSync
- System namespace PVCs (auto-excluded by Kyverno)
- Temporary/cache data
- Non-Longhorn PVCs (snapshot support required)

## Verification

After applying, Kyverno auto-generates backup resources:
```bash
kubectl get replicationsource,replicationdestination,externalsecret -n <namespace>
```

## Removing Backups

Just remove the `backup` label. The `volsync-orphan-cleanup` ClusterCleanupPolicy runs every 15 minutes and auto-deletes orphaned resources.
