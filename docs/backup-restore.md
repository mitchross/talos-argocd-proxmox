# Zero-Touch PVC Backup and Restore

This document describes the automated backup and restore system for Kubernetes PersistentVolumeClaims (PVCs).

## Overview

The system automatically backs up PVCs to S3-compatible storage (RustFS/TrueNAS) using **Kopia** and restores them on disaster recovery or app re-deployment. It uses a "look-before-you-leap" pattern to conditionally restore only when backups exist.

### Why Kopia over Restic?

- **Faster**: Parallel uploads, better compression (zstd)
- **Efficient**: Content-defined chunking with deduplication
- **Maintained**: Active development, used by VolSync maintainers

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   1Password     │────▶│ External Secrets│────▶│    Secrets      │
│   (rustfs)      │     │    Operator     │     │  (per-PVC)      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
┌─────────────────┐     ┌─────────────────┐            │
│   pvc-plumber   │◀────│    Kyverno      │◀───────────┘
│  (backup check) │     │  ClusterPolicy  │
└────────┬────────┘     └────────┬────────┘
         │                       │
         ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│   RustFS S3     │     │    VolSync      │
│ volsync-backup  │◀────│  ReplicationSrc │
└─────────────────┘     │  ReplicationDst │
                        └─────────────────┘
```

## Components

### 1. RustFS S3 Storage
- **Endpoint:** `http://192.168.10.133:30292`
- **Bucket:** `volsync-backup`
- **Access Key:** `k8s-admin` (stored in 1Password `rustfs` item)

### 2. pvc-plumber Service
- Lightweight Go service that checks if backups exist in S3
- Endpoint: `http://pvc-plumber.volsync-system.svc.cluster.local/exists/{namespace}/{pvc-name}`
- Returns: `{"exists": true/false}`
- Deployed at sync wave 2 (before Kyverno)

### 3. Kyverno ClusterPolicy
- Triggers on PVCs with label `backup: hourly` or `backup: daily`
- **Only triggers on CREATE operations** (not UPDATE/DELETE) to avoid race conditions
- Calls pvc-plumber to check for existing backups
- Generates:
  - ExternalSecret (per-PVC S3 credentials)
  - ReplicationSource (backup schedule)
  - ReplicationDestination (restore capability)
- If backup exists: mutates PVC with `dataSourceRef` for auto-restore

### 4. VolSync
- Performs actual backup/restore operations using **Kopia**
- Uses Longhorn snapshots for consistent backups
- Stores data in S3 with Kopia encryption and zstd compression
- Parallel uploads (parallelism: 2) for faster backups

## Sync Wave Order

| Wave | Component | Purpose |
|------|-----------|---------|
| 0 | 1Password Connect, External Secrets | Secret management foundation |
| 1 | Longhorn, VolSync, Snapshot Controller | Storage foundation |
| 2 | pvc-plumber | Backup existence checker |
| 4 | Kyverno | Policy engine (calls pvc-plumber) |
| 6 | My Apps | Application workloads with PVCs |

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

## Backup Schedules

| Label | Schedule | Retention |
|-------|----------|-----------|
| `backup: hourly` | Every hour (0 * * * *) | 24 hourly, 7 daily, 4 weekly, 2 monthly |
| `backup: daily` | 2am daily (0 2 * * *) | 24 hourly, 7 daily, 4 weekly, 2 monthly |

## Scenario Behavior

### Fresh Cluster (No Backups)
1. PVC created with backup label
2. Kyverno calls pvc-plumber → no backup found
3. PVC created normally (empty)
4. Backup schedule begins

### Disaster Recovery (Backups Exist)
1. PVC created with backup label
2. Kyverno calls pvc-plumber → backup found
3. Kyverno adds `dataSourceRef` to PVC
4. VolSync VolumePopulator restores data
5. PVC bound with restored data

### App Re-deployment
Same as disaster recovery - existing backups are automatically restored.

## 1Password Configuration

The `rustfs` item in 1Password must contain:

| Field | Example Value | Purpose |
|-------|--------------|---------|
| `k8s-admin-access-key` | `k8s-admin` | S3 access key ID |
| `k8s-admin-secret-key` | (secret) | S3 secret access key |
| `kopia_password` | (password) | Kopia repository encryption key |
| `endpoint` | `http://192.168.10.133:30292` | S3 endpoint (for pvc-plumber) |
| `bucket` | `volsync-backup` | S3 bucket (for pvc-plumber) |

### Generated Secret Contents

Kyverno generates a secret per-PVC with:

| Key | Source | Purpose |
|-----|--------|---------|
| `KOPIA_PASSWORD` | 1Password | Repository encryption |
| `KOPIA_S3_BUCKET` | Template | Bucket name |
| `KOPIA_S3_ENDPOINT` | Template | S3 endpoint (without http://) |
| `KOPIA_S3_PREFIX` | Template | `{namespace}/{pvc-name}` path |
| `KOPIA_S3_DISABLE_TLS` | Template | `true` for http endpoints |
| `KOPIA_S3_ACCESS_KEY_ID` | 1Password | S3 access key |
| `KOPIA_S3_SECRET_ACCESS_KEY` | 1Password | S3 secret key |

## S3 Bucket Structure

```
volsync-backup/
├── {namespace}/
│   └── {pvc-name}/
│       ├── kopia.repository    # Kopia repository config
│       ├── kopia.blobcfg       # Blob storage config
│       ├── p/                  # Pack files (deduplicated data)
│       ├── q/                  # Index blobs
│       ├── n/                  # Manifest blobs
│       └── x/                  # Session blobs
```

Note: Kopia uses content-addressable storage with pack files for efficient deduplication.

## Critical Implementation Details

### Kyverno Policy: Operations Filter (Race Condition Fix)

**Problem:** Without an operations filter, Kyverno intercepts ALL PVC operations including DELETE, preventing PVC deletion.

**Solution:** All rules must include `operations: [CREATE]`:

```yaml
match:
  any:
    - resources:
        kinds:
          - PersistentVolumeClaim
        operations:
          - CREATE  # CRITICAL: Only trigger on create, not delete
        selector:
          matchExpressions:
            - key: backup
              operator: In
              values: ["hourly", "daily"]
```

### External Secrets: mergePolicy (Template + Data Merge)

**Problem:** Kyverno uses `{{ }}` syntax, External Secrets uses `{{ }}` syntax. They conflict.

**Solution:** Use `mergePolicy: Merge` to combine:
- `template.data` - RESTIC_REPOSITORY (Kyverno substitutes namespace/pvc-name)
- `data` section - Credentials fetched from 1Password

```yaml
target:
  name: "volsync-{{request.object.metadata.name}}"
  creationPolicy: Owner
  template:
    engineVersion: v2
    mergePolicy: Merge  # CRITICAL: Merge template with fetched data
    data:
      # Kyverno substitutes these variables at generate time
      RESTIC_REPOSITORY: "s3:http://192.168.10.133:30292/volsync-backup/{{request.object.metadata.namespace}}/{{request.object.metadata.name}}"
data:
  # External Secrets fetches these from 1Password and merges them
  - secretKey: AWS_ACCESS_KEY_ID
    remoteRef:
      key: rustfs
      property: k8s-admin-access-key
  - secretKey: AWS_SECRET_ACCESS_KEY
    remoteRef:
      key: rustfs
      property: k8s-admin-secret-key
  - secretKey: RESTIC_PASSWORD
    remoteRef:
      key: rustfs
      property: restic_password
```

**Result:** Secret contains all 4 required fields:
- `RESTIC_REPOSITORY` - from template (Kyverno-substituted)
- `AWS_ACCESS_KEY_ID` - from 1Password
- `AWS_SECRET_ACCESS_KEY` - from 1Password
- `RESTIC_PASSWORD` - from 1Password

### Kyverno RBAC Requirements

Kyverno needs permissions to generate ExternalSecrets and VolSync resources:

```yaml
# infrastructure/controllers/kyverno/rbac-patch.yaml
rules:
- apiGroups: [""]
  resources: ["secrets"]
  verbs: ["get", "list", "watch", "create", "update", "delete"]
- apiGroups: ["external-secrets.io"]
  resources: ["externalsecrets"]
  verbs: ["get", "list", "watch", "create", "update", "delete"]
- apiGroups: ["volsync.backube"]
  resources: ["replicationsources", "replicationdestinations"]
  verbs: ["get", "list", "watch", "create", "update", "delete"]
```

## Troubleshooting

### PVC Stuck in Pending
1. Check if ReplicationDestination exists: `kubectl get replicationdestination -n <namespace>`
2. Check pvc-plumber logs: `kubectl logs -n volsync-system -l app.kubernetes.io/name=pvc-plumber`
3. Check VolSync mover pod: `kubectl get pods -n <namespace> | grep volsync`

### PVC Stuck in Terminating (Race Condition)
**Symptom:** PVCs won't delete, Kyverno keeps intercepting patches.

**Cause:** Missing `operations: [CREATE]` filter in Kyverno policy.

**Fix:** Ensure all rules have `operations: [CREATE]` in match clause.

### Secret Missing Credentials
**Symptom:** VolSync fails with "access_key: placeholder" or missing credentials.

**Cause:** `mergePolicy: Replace` (default) overwrites fetched data with template.

**Fix:** Add `mergePolicy: Merge` to ExternalSecret template.

**Verify:** `kubectl get secret volsync-<pvc-name> -n <namespace> -o json | jq '.data | keys'`
Should show: `["KOPIA_PASSWORD", "KOPIA_S3_ACCESS_KEY_ID", "KOPIA_S3_BUCKET", "KOPIA_S3_DISABLE_TLS", "KOPIA_S3_ENDPOINT", "KOPIA_S3_PREFIX", "KOPIA_S3_SECRET_ACCESS_KEY"]`

### Backup Not Running
1. Check ReplicationSource: `kubectl get replicationsource -n <namespace>`
2. Check secret exists: `kubectl get secret -n <namespace> | grep volsync`
3. Check ExternalSecret status: `kubectl get externalsecret -n <namespace>`

### Test pvc-plumber
```bash
kubectl run -n volsync-system test --rm -it --image=curlimages/curl --restart=Never -- \
  curl -s http://pvc-plumber.volsync-system.svc.cluster.local/exists/karakeep/data-pvc
# Expected: {"exists":true,"keyCount":1} or {"exists":false}
```

## Excluded Namespaces

The following namespaces are excluded from automatic backup:
- `kube-system`
- `volsync-system`
- `kyverno`

## Prometheus Monitoring

VolSync alerts are configured in `monitoring/prometheus-stack/volsync-alerts.yaml`:

| Alert | Severity | Description |
|-------|----------|-------------|
| `VolSyncControllerDown` | Critical | VolSync controller unavailable |
| `VolSyncVolumeOutOfSync` | Critical | Backup failed or never completed |
| `VolSyncMissedScheduledBackup` | Warning | Scheduled backup was skipped |
| `VolSyncDurationTooLong` | Warning | Backup taking > 1 hour |
| `PvcPlumberDown` | Critical | pvc-plumber service unavailable |

## Files

| File | Purpose |
|------|---------|
| `infrastructure/controllers/pvc-plumber/` | Backup existence checker service |
| `infrastructure/controllers/kyverno/policies/volsync-pvc-backup-restore.yaml` | Kyverno policy (Kopia) |
| `infrastructure/storage/volsync/` | VolSync Helm chart + VolumeSnapshotClass |
| `infrastructure/controllers/argocd/apps/pvc-plumber-app.yaml` | ArgoCD Application |
| `monitoring/prometheus-stack/volsync-alerts.yaml` | Prometheus alerting rules |
