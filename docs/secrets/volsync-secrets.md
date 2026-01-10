# VolSync Secrets Setup

## ✅ Fully Automated via Kyverno

**Zero-touch backup system: Create PVC with label → automatic backups!**

### How It Works

1. **Label a PVC** with `backup: "hourly"` or `backup: "daily"`
2. **Kyverno auto-generates**:
   - Secret with S3 credentials (unique path per PVC)
   - ReplicationSource (backup scheduler)
   - ReplicationDestination (restore capability)
3. **Backups run automatically** on schedule
4. **PVCs bind immediately** to fresh storage (no restore blocking)

### Disaster Recovery (Manual Restore)

When you need to restore from backup:
1. Create new PVC (without dataSource)
2. Wait for PVC to bind
3. Patch PVC to add `dataSourceRef` pointing to ReplicationDestination
4. VolSync populates PVC from latest backup snapshot

No manual YAML creation. No pending PVCs. **Set and forget.**

## Required 1Password Item

### rustfs

Create a **Password** item in your 1Password vault:

| Field | Value |
|-------|-------|
| **Item name** | `rustfs` |
| **access_key** | RustFS access key |
| **secret_key** | RustFS secret key |
| **restic_password** | A strong random password (32+ characters) |
| **restic_repository** | `s3:http://192.168.10.133:30292/volsync-backup/` |

**Path Structure:** Kyverno computes unique paths as `volsync-backup/namespace/pvcname`

Example paths:
- `volsync-backup/karakeep/data-pvc`
- `volsync-backup/immich/library`
- `volsync-backup/home-assistant/config`

The `restic_password` encrypts all backup repositories stored in S3.

**Generate a secure password:**
```bash
openssl rand -base64 32
```

Example output: `K7x9mP2nL4qR8vT1wY5zA3cF6hJ0bN+dG=`

**That's it!** When you add `backup: "hourly"` or `backup: "daily"` to a PVC, Kyverno automatically:
1. Removes any `dataSource` field (prevents binding issues)
2. Generates Secret with S3 credentials (unique path: `namespace/pvcname`)
3. Creates ReplicationSource (backup scheduler)
4. Creates ReplicationDestination (restore capability)
5. PVC binds immediately to fresh storage and backups begin

**No manual YAML. No pending PVCs. No touching VolSync resources directly.**

## Verification

After creating the `rustfs` item and labeling PVCs, verify auto-generated resources:

```bash
# Check all PVCs with backup labels
kubectl get pvc -A -l backup

# Check auto-generated Secrets (Kyverno created these!)
kubectl get secret -A -l volsync.backube/secret-type=restic

# Check ReplicationSources (backup schedulers)
kubectl get replicationsource -A

# Check backup status
kubectl get replicationsource -n <namespace> <pvc>-backup -o yaml
```

All Secrets should have the `volsync.backube/secret-type: restic` label and contain:
- `RESTIC_REPOSITORY` (unique path: `s3:.../volsync-backup/namespace/pvcname`)
- `RESTIC_PASSWORD`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`

## S3 Bucket Setup

Ensure the `volsync-backup` bucket exists in RustFS (192.168.10.133:30292):

| Bucket | Purpose |
|--------|---------|
| `volsync-backup` | VolSync PVC backups (Restic repositories) |

Create it if it doesn't exist:
```bash
mc alias set rustfs http://192.168.10.133:30292 <access_key> <secret_key>
mc mb rustfs/volsync-backup
```

## Auto-Generated Resources

For each PVC with `backup: hourly` or `backup: daily`, Kyverno creates:

### Secret
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: <pvc-name>-volsync-secret
  namespace: <pvc-namespace>
  labels:
    volsync.backube/secret-type: restic
type: Opaque
data:
  RESTIC_REPOSITORY: <base64: s3://.../<namespace>/<pvcname>>
  RESTIC_PASSWORD: <base64: from 1Password>
  AWS_ACCESS_KEY_ID: <base64: from 1Password>
  AWS_SECRET_ACCESS_KEY: <base64: from 1Password>
```

### ReplicationSource (Backup Scheduler)
```yaml
apiVersion: volsync.backube/v1alpha1
kind: ReplicationSource
metadata:
  name: <pvc-name>-backup
spec:
  sourcePVC: <pvc-name>
  trigger:
    schedule: "0 * * * *"  # hourly tier
    manual: "initial"      # allows manual triggers
  restic:
    repository: <pvc-name>-volsync-secret
    pruneIntervalDays: 7
    retain:
      hourly: 24
      daily: 7
```

### ReplicationDestination (Restore Capability)
```yaml
apiVersion: volsync.backube/v1alpha1
kind: ReplicationDestination
metadata:
  name: <pvc-name>-restore
spec:
  trigger:
    manual: restore-once
  restic:
    repository: <pvc-name>-volsync-secret
    copyMethod: Direct
```

**All generated automatically by Kyverno ClusterPolicy `generate-volsync-backup`**
