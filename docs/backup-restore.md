# Zero-Touch PVC Backup and Restore

This document describes the automated backup and restore system for Kubernetes PersistentVolumeClaims (PVCs).

## Overview

The system automatically backs up PVCs to NFS storage on TrueNAS using **Kopia** and restores them on disaster recovery or app re-deployment. Simply add a label to your PVC and backups happen automatically.

### Why Kopia?

- **Fast**: Parallel uploads, zstd compression
- **Efficient**: Content-defined chunking with deduplication
- **Encrypted**: All data encrypted with KOPIA_PASSWORD before storage
- **Maintained**: Active development, used by VolSync maintainers

### Why NFS over S3?

- **Simpler**: No S3 credentials to manage per-namespace
- **Faster**: Direct filesystem access, no HTTP overhead
- **Browsable**: Kopia UI can directly browse backups
- **Consistent**: Same approach as home-ops reference implementation

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   1Password     │────▶│ External Secrets│────▶│    Secrets      │
│   (rustfs)      │     │    Operator     │     │  (KOPIA_PASSWORD│
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
┌─────────────────┐     ┌─────────────────┐            │
│  MutatingAdm-   │────▶│    VolSync      │◀───────────┘
│  issionPolicy   │     │  Mover Jobs     │
│  (NFS inject)   │     └────────┬────────┘
└─────────────────┘              │
                                 ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   TrueNAS NFS   │◀────│    Kyverno      │◀────│  pvc-plumber    │
│ volsync-kopia-  │     │  ClusterPolicy  │     │  (backup check) │
│ nfs             │     │  (generates     │     └─────────────────┘
└─────────────────┘     │   resources)    │
                        └─────────────────┘
```

## Automatic Restore Flow

When a PVC is created with a backup label, the system automatically checks if a backup exists and restores it:

```
PVC Created ──▶ Kyverno Rule 0 ──▶ Calls pvc-plumber ──▶ Backup exists?
                                                              │
                    ┌─────────────────────────────────────────┴─────────┐
                    │ YES                                               │ NO
                    ▼                                                   ▼
            Add dataSourceRef                                   No mutation
            to PVC spec                                         (fresh PVC)
                    │
                    ▼
            VolSync populates PVC
            from Kopia backup
                    │
                    ▼
            PVC becomes Bound ──▶ Kyverno Rule 2 ──▶ Creates ReplicationSource
                                                    (backup schedule starts)
```

**Key protections:**
- **Fail-closed gate:** PVC creation denied if PVC Plumber is unreachable (prevents empty PVCs during disaster recovery)
- Backup ReplicationSource only created AFTER PVC is Bound (prevents backup/restore conflicts)
- Restore uses VolumePopulator pattern (dataSourceRef) for atomic restore

## Components

### 1. TrueNAS NFS Storage
- **Server:** `192.168.10.133`
- **Path:** `/mnt/BigTank/k8s/volsync-kopia-nfs`
- **Encryption:** Kopia encrypts all data with KOPIA_PASSWORD

### 2. Kyverno NFS Injection Policy
- Automatically injects NFS mount into all VolSync mover jobs
- Mounts `/repository` from TrueNAS NFS share
- No per-app configuration needed

### 3. pvc-plumber
- HTTP service that checks if a backup exists in Kopia repository
- Called by Kyverno before creating a PVC to determine if restore is needed
- Image: `ghcr.io/mitchross/pvc-plumber`
- Endpoint: `GET /exists/{namespace}/{pvc}` returns `{"exists": true/false}`

### 4. Kyverno ClusterPolicy
- Triggers on PVCs with label `backup: hourly` or `backup: daily`
- **Rule 0 (validate, FAIL-CLOSED):** Calls pvc-plumber `/readyz`; if unreachable, **denies PVC creation** to prevent data loss during disaster recovery
- **Rule 1 (mutate):** Calls pvc-plumber `/exists`; if backup exists, adds `dataSourceRef` to trigger restore
- **Rule 2 (generate):** Creates ExternalSecret (fetches KOPIA_PASSWORD from 1Password)
- **Rule 3 (generate):** Creates ReplicationSource (backup schedule) - only after PVC is Bound
- **Rule 4 (generate):** Creates ReplicationDestination (restore capability)

### 4a. Kyverno ClusterCleanupPolicy (Orphan Cleanup)
- **Runs every 15 minutes** to clean up orphaned backup resources
- Targets ReplicationSource, ReplicationDestination, and ExternalSecret with labels `app.kubernetes.io/managed-by=kyverno` and `volsync.backup/pvc`
- Checks if the corresponding PVC still has `backup: hourly` or `backup: daily` label
- If label was removed or PVC no longer exists, **deletes the orphaned resources**
- Prevents stale backup/restore jobs from running after backups are disabled

### 5. VolSync
- Performs actual backup/restore operations using **Kopia**
- Uses Longhorn snapshots for consistent backups
- Stores data on NFS with Kopia encryption and zstd compression

### 6. Kopia UI (Optional)
- Web interface to browse backups
- Accessible at `kopia-ui.{domain}`
- Mounts same NFS share as VolSync

## How to Disable Backup for a PVC

Remove the `backup` label from the PVC:

```yaml
metadata:
  labels:
    # backup: "hourly"   # Comment out or remove to disable backup
```

The `volsync-orphan-cleanup` ClusterCleanupPolicy runs every 15 minutes and automatically deletes the orphaned ReplicationSource, ReplicationDestination, and ExternalSecret. No manual cleanup needed.

**Note:** Removing the label does NOT delete existing backups from NFS. The Kopia repository on TrueNAS retains all previous snapshots. To re-enable backups later, simply re-add the label.

## How to Enable Backup for a PVC

Add a backup label to your PVC:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: my-data
  namespace: my-app
  labels:
    backup: "hourly"    # Backups every hour
    # OR
    backup: "daily"     # Backups at 2am daily
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: longhorn
  resources:
    requests:
      storage: 10Gi
```

That's it! Kyverno automatically generates all required resources.

## Backup Schedules

| Label | Schedule | Retention |
|-------|----------|-----------|
| `backup: hourly` | Every hour (0 * * * *) | 24 hourly, 7 daily, 4 weekly, 2 monthly |
| `backup: daily` | 2am daily (0 2 * * *) | 24 hourly, 7 daily, 4 weekly, 2 monthly |

## 1Password Configuration

The `rustfs` item in 1Password must contain:

| Field | Purpose |
|-------|---------|
| `kopia_password` | Kopia repository encryption key |

### Generated Secret Contents

Kyverno generates a secret per-PVC with:

| Key | Value | Purpose |
|-----|-------|---------|
| `KOPIA_REPOSITORY` | `filesystem:///repository` | Repository type and path |
| `KOPIA_FS_PATH` | `/repository` | Filesystem path |
| `KOPIA_PASSWORD` | (from 1Password) | Repository encryption |

## NFS Repository Structure

```
/mnt/BigTank/k8s/volsync-kopia-nfs/
├── kopia.repository           # Kopia repository config
├── kopia.blobcfg              # Blob storage config
├── p/                         # Pack files (deduplicated data)
├── q/                         # Index blobs
├── n/                         # Manifest blobs
└── x/                         # Session blobs
```

All PVC backups share the same Kopia repository, with snapshots tagged by namespace/pvc-name.

## Manual Restore

To manually trigger a restore:

1. Delete the existing PVC
2. Recreate the PVC with the same name and backup label
3. VolSync will restore from the latest snapshot

Or use the ReplicationDestination directly:

```bash
# Trigger manual restore
kubectl patch replicationdestination <pvc-name>-restore -n <namespace> \
  --type merge -p '{"spec":{"trigger":{"manual":"restore-$(date +%s)"}}}'
```

## Troubleshooting

### Check Backup Status

```bash
# List all ReplicationSources
kubectl get replicationsource -A

# Check specific backup
kubectl get replicationsource <pvc-name>-backup -n <namespace> -o yaml
```

### Check Mover Pod Logs

```bash
# Find mover pod
kubectl get pods -n <namespace> | grep volsync

# View logs
kubectl logs -n <namespace> <volsync-pod-name>
```

### Verify NFS Mount

```bash
# Check if NFS is mounted in mover pod
kubectl exec -n <namespace> <volsync-pod-name> -- df -h /repository
```

### Secret Missing or Invalid

```bash
# Check ExternalSecret status
kubectl get externalsecret -n <namespace>

# Check secret contents
kubectl get secret volsync-<pvc-name> -n <namespace> -o yaml
```

### Kyverno Not Generating Resources

```bash
# Check policy status
kubectl get clusterpolicy volsync-pvc-backup-restore

# Check policy events
kubectl describe clusterpolicy volsync-pvc-backup-restore

# Trigger regeneration by updating PVC label
kubectl label pvc <pvc-name> -n <namespace> kyverno-trigger=$(date +%s) --overwrite
```

## Excluded Namespaces

The following namespaces are excluded from automatic backup:
- `kube-system`
- `volsync-system`
- `kyverno`

## Files

| File | Purpose |
|------|---------|
| `infrastructure/controllers/pvc-plumber/` | Backup existence checker service |
| `infrastructure/storage/volsync/` | VolSync Helm chart |
| `infrastructure/controllers/kyverno/policies/volsync-nfs-inject.yaml` | Injects NFS mount into mover pods |
| `infrastructure/storage/kopia-ui/` | Kopia web UI for browsing backups |
| `infrastructure/controllers/kyverno/policies/volsync-pvc-backup-restore.yaml` | Kyverno backup/restore policy |
| `infrastructure/controllers/kyverno/policies/volsync-orphan-cleanup.yaml` | Cleanup orphaned backup resources |
| `monitoring/prometheus-stack/volsync-alerts.yaml` | Prometheus alerting rules |
| `infrastructure/database/cloudnative-pg/` | CNPG database clusters (separate backup path) |

## Database Backups (CNPG — Separate System)

The PVC backup system above covers **application data**. Database backups use a **completely separate path**:

| | PVC Backups | Database Backups |
|---|---|---|
| **Tool** | VolSync + Kopia | CNPG + Barman |
| **Destination** | TrueNAS NFS | RustFS S3 (`s3://postgres-backups/cnpg/`) |
| **Trigger** | Kyverno auto-generates on PVC label | CNPG ScheduledBackup resource |
| **Auto-restore** | Yes (PVC Plumber + Kyverno) | **No** — manual recovery required |
| **Schedule** | Hourly or daily (per PVC label) | Hourly + continuous WAL archiving |

### Why databases don't use the PVC backup system

- Filesystem-level backup of a running Postgres database can be inconsistent
- Barman uses `pg_basebackup` + WAL archiving for point-in-time recovery
- CNPG manages its own PVCs (names are auto-generated, can't add Kyverno labels)

### Database disaster recovery

After a cluster nuke, CNPG creates **fresh empty databases** — it does NOT auto-restore from Barman backups. Recovery requires manually bypassing ArgoCD (SSA + CNPG webhook conflict prevents recovery mode through GitOps).

See **[docs/cnpg-disaster-recovery.md](cnpg-disaster-recovery.md)** for full recovery procedures.
