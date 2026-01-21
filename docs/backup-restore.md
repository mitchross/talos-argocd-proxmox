# Zero-Touch PVC Backup and Restore

This document describes the automated backup and restore system for Kubernetes PersistentVolumeClaims (PVCs).

## Overview

The system automatically backs up PVCs to S3-compatible storage (RustFS/MinIO) and restores them on disaster recovery or app re-deployment. It uses a "look-before-you-leap" pattern to conditionally restore only when backups exist.

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
- Performs actual backup/restore operations using Restic
- Uses Longhorn snapshots for consistent backups
- Stores data in S3 with Restic encryption

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
| `restic_password` | (password) | Restic encryption key |
| `restic_repository` | `s3:http://192.168.10.133:30292/volsync-backup/` | Base S3 path |
| `endpoint` | `http://192.168.10.133:30292` | S3 endpoint (for pvc-plumber) |
| `bucket` | `volsync-backup` | S3 bucket (for pvc-plumber) |

## S3 Bucket Structure

```
volsync-backup/
├── {namespace}/
│   └── {pvc-name}/
│       ├── config          # Restic repository config
│       ├── data/           # Deduplicated backup data
│       ├── index/          # Restic index files
│       ├── keys/           # Encryption keys
│       ├── locks/          # Lock files
│       └── snapshots/      # Snapshot metadata
```

## Troubleshooting

### PVC Stuck in Pending
1. Check if ReplicationDestination exists: `kubectl get replicationdestination -n <namespace>`
2. Check pvc-plumber logs: `kubectl logs -n volsync-system -l app.kubernetes.io/name=pvc-plumber`
3. Check VolSync mover pod: `kubectl get pods -n <namespace> | grep volsync`

### Backup Not Running
1. Check ReplicationSource: `kubectl get replicationsource -n <namespace>`
2. Check secret exists: `kubectl get secret -n <namespace> | grep volsync`
3. Check ExternalSecret status: `kubectl get externalsecret -n <namespace>`

### Test pvc-plumber
```bash
kubectl port-forward -n volsync-system svc/pvc-plumber 8080:80
curl http://localhost:8080/exists/karakeep/data-pvc
# Expected: {"exists":true} or {"exists":false}
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
| `infrastructure/controllers/kyverno/policies/volsync-pvc-backup-restore.yaml` | Kyverno policy |
| `infrastructure/storage/volsync/` | VolSync Helm chart + VolumeSnapshotClass |
| `infrastructure/controllers/argocd/apps/pvc-plumber-app.yaml` | ArgoCD Application |
