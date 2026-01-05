# Storage Architecture & Disaster Recovery

This document outlines the storage architecture for the cluster, focusing on data persistence, backup strategies, and disaster recovery workflows.

## Overview

The cluster uses a layered storage approach:
- **Longhorn**: Distributed block storage for runtime replication (2 replicas per volume)
- **VolSync**: Daily backups of all PVCs to S3 using Restic
- **Database-native backups**: CloudNativePG and Crunchy Postgres backup directly to S3

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        Talos Cluster                            │
│  ┌──────────────────┐    ┌──────────────────┐                  │
│  │   App PVCs       │    │  Postgres DBs    │                  │
│  │  (Longhorn)      │    │  (CNPG/Crunchy)  │                  │
│  └────────┬─────────┘    └────────┬─────────┘                  │
│           │                       │                             │
│           ▼                       ▼                             │
│  ┌──────────────────┐    ┌──────────────────┐                  │
│  │    VolSync       │    │  Native PG       │                  │
│  │  (Restic daily)  │    │  WAL + Backups   │                  │
│  └────────┬─────────┘    └────────┬─────────┘                  │
│           │                       │                             │
└───────────┼───────────────────────┼─────────────────────────────┘
            │                       │
            ▼                       ▼
     ┌─────────────────────────────────────┐
     │   RustFS (S3) on TrueNAS            │
     │   192.168.10.133:30292              │
     │   └── volsync/<app>/                │
     └─────────────────────────────────────┘
```

## 1. Normal Operation (Write Path)

When an application writes data, it flows through Kubernetes to Longhorn, which maintains 2 replicas:

```mermaid
graph LR
    subgraph "Application Pod"
        App[Application] --> Mount["/data (Mount)"]
    end

    subgraph "Kubernetes Storage"
        Mount --> PVC[PersistentVolumeClaim]
        PVC --> PV[PersistentVolume]
    end

    subgraph "Longhorn Storage Engine"
        PV --> LH_Vol[Longhorn Volume]
        LH_Vol --> Replica1[Replica 1 Node A]
        LH_Vol --> Replica2[Replica 2 Node B]
    end

    style App fill:#f9f,stroke:#333,stroke-width:2px
    style LH_Vol fill:#bbf,stroke:#333,stroke-width:2px
```

**Longhorn provides:**
- Runtime replication (survives single node failure)
- Fast replica rebuild
- Automatic rebalancing

**Longhorn does NOT provide:**
- Off-cluster backups (handled by VolSync)
- Point-in-time recovery (handled by VolSync)

## 2. Backup Strategy

### PVC Backups (VolSync)

All application PVCs are backed up daily at 2 AM using VolSync with Restic:

| Setting | Value |
|---------|-------|
| Schedule | `0 2 * * *` (daily at 2 AM) |
| Retention | 14 days |
| Backend | Restic |
| Target | RustFS S3 on TrueNAS (192.168.10.133:30292) |
| Bucket | `volsync` |
| Copy Method | Snapshot |

Each app has:
- `ReplicationSource` - Defines backup schedule and retention
- `ReplicationDestination` - Pre-provisioned for restore capability
- `ExternalSecret` - Pulls S3 credentials from 1Password

### Database Backups (Native)

PostgreSQL databases use their native backup tools:

**CloudNativePG (khoj, paperless)**
- Barman for WAL archiving
- Daily base backups at 3 AM
- 14-day retention
- Point-in-time recovery capable

**Crunchy Postgres (immich)**
- pgBackRest for backups
- Weekly full + daily differential
- 14-day retention

## 3. Disaster Recovery

### Restoring a PVC (VolSync)

When you need to restore a PVC from backup:

1. **Trigger the ReplicationDestination**:
```bash
kubectl patch replicationdestination <app>-restore -n <namespace> \
  --type merge \
  -p '{"spec":{"trigger":{"manual":"restore-'$(date +%s)'"}}}'
```

2. **Wait for restore to complete**:
```bash
kubectl get replicationdestination <app>-restore -n <namespace> -w
```

3. **Update PVC to use restored data** (if needed):
```yaml
spec:
  dataSourceRef:
    kind: ReplicationDestination
    apiGroup: volsync.backube
    name: <app>-restore
```

### Restoring a Database

**CloudNativePG:**
```yaml
spec:
  bootstrap:
    recovery:
      source: <cluster-name>
      # Optional: recoveryTarget for point-in-time
```

**Crunchy Postgres:**
Use pgBackRest restore commands or recreate cluster with recovery settings.

### Full Cluster Rebuild

After a complete cluster rebuild:

1. Deploy infrastructure (ArgoCD, External Secrets, Longhorn, VolSync)
2. VolSync operator syncs with S3
3. For each app, trigger ReplicationDestination to restore data
4. Deploy applications - they bind to restored PVCs

## 4. What Changed from Longhorn Backups

| Feature | Before (Longhorn) | Now (VolSync) |
|---------|-------------------|---------------|
| Backup tool | Longhorn built-in | VolSync + Kopia |
| Backup schedule | RecurringJobs (tiered) | Single daily schedule |
| Restore method | Hardcoded restore-job.yaml | Declarative ReplicationDestination |
| Database backups | PVC snapshots (inconsistent) | Native WAL archiving (consistent) |
| Complexity | Multiple tiers, shell scripts | Simple, uniform config |

## 5. Monitoring

### Check VolSync Status
```bash
# All ReplicationSources
kubectl get replicationsource -A

# Specific app
kubectl describe replicationsource home-assistant-config-backup -n home-assistant
```

### Check Database Backups
```bash
# CNPG
kubectl get backup -n cloudnative-pg

# Crunchy
kubectl exec -it <postgres-pod> -n postgres-operator -- pgbackrest info
```

### S3 Bucket Contents
```bash
# VolSync backups (RustFS)
mc alias set rustfs http://192.168.10.133:30292 <access_key> <secret_key>
mc ls rustfs/volsync/

# List specific app backup
mc ls rustfs/volsync/home-assistant/
```

## 6. Configuration Files

| Component | Location |
|-----------|----------|
| VolSync operator | `infrastructure/storage/volsync/` |
| Longhorn (replication only) | `infrastructure/storage/longhorn/` |
| App VolSync configs | `my-apps/<category>/<app>/replicationsource.yaml` |
| CNPG backup config | `infrastructure/database/cloudnative-pg/*/cluster.yaml` |
| Crunchy backup config | `infrastructure/database/crunchy-postgres/*/cluster.yaml` |
| 1Password setup | `docs/secrets/volsync-secrets.md` |
