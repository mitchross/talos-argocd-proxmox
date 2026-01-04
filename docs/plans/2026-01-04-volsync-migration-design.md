# VolSync Migration Design

**Date:** 2026-01-04
**Status:** Approved
**Goal:** Replace Longhorn backup/restore with VolSync + database-native backups

## Problem Statement

Longhorn's backup/restore process has been brittle and unreliable. The current restore-job hardcodes backup metadata and uses shell scripting that's fragile. We need a more dependable, unified backup approach.

## Architecture

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
│  │  (Kopia daily)   │    │  WAL + Backups   │                  │
│  └────────┬─────────┘    └────────┬─────────┘                  │
│           │                       │                             │
└───────────┼───────────────────────┼─────────────────────────────┘
            │                       │
            ▼                       ▼
     ┌─────────────────────────────────────┐
     │   RustFS (S3) on TrueNAS            │
     │   192.168.10.133                    │
     │   ├── volsync-backups/              │
     │   └── postgres-backups/             │
     └─────────────────────────────────────┘
```

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Backup tool | VolSync + Kopia | Proven on Talos, fast dedup, encryption |
| S3 target | RustFS on TrueNAS | Already deployed, on-prem, no egress |
| Schedule | Daily @ 2AM | Single schedule for all - simplicity |
| Retention | 14 days | Good balance of protection vs storage |
| Tiers | None | All backed-up data is critical |
| DB backups | Native (CNPG/Crunchy) | Point-in-time recovery, consistent |
| Restore method | Pre-provisioned ReplicationDestinations | Declarative, no shell scripts |
| S3 credentials | Reuse existing Longhorn creds | Already in 1Password |

## PVCs to Backup (17 total)

### Longhorn PVCs (VolSync)

| App | PVC | Location |
|-----|-----|----------|
| open-webui | data | `my-apps/ai/open-webui/pvc.yaml` |
| khoj | data | `my-apps/ai/khoj/pvc.yaml` |
| home-assistant | config | `my-apps/home/home-assistant/pvc.yaml` |
| paperless-ngx | data | `my-apps/home/paperless-ngx/pvc.yaml` |
| frigate/mqtt | data | `my-apps/home/frigate/mqtt/mqtt.yaml` |
| n8n | workflows | `my-apps/development/n8n/pvc.yaml` |
| nginx | config | `my-apps/development/nginx/pvc.yaml` |
| fizzy | data | `my-apps/development/fizzy/pvc.yaml` |
| immich | library | `my-apps/media/immich/library-pvc.yaml` |
| jellyfin | config | `my-apps/media/jellyfin/pvc.yaml` |
| jellyfin | media | `my-apps/media/jellyfin/jellyfin-media-pvc.yaml` |
| karakeep | data | `my-apps/media/karakeep/karakeep/pvc-data.yaml` |
| karakeep | meilisearch | `my-apps/media/karakeep/meilisearch/pvc-meilisearch.yaml` |
| plex | config | `my-apps/media/plex/pvc.yaml` |
| homepage-dashboard | config | `my-apps/media/homepage-dashboard/pvc.yaml` |
| nestmtx | data | `my-apps/media/nestmtx/pvc.yaml` |
| searxng | redis | `my-apps/privacy/searxng/redis.yaml` |
| container-registry | images | `infrastructure/storage/container-registry/pvc.yaml` |
| redis-instance | data | `infrastructure/database/redis/redis-instance/pvc.yaml` |

### Excluded - SMB Mounts (backed up on TrueNAS)

- ollama, llama-cpp, comfyui, frigate recordings, kiwix, tubesync

### Excluded - Cache (regenerable)

- immich ml-cache
- proxitok cache

### Databases (Native Backup)

- CloudNativePG: khoj-db, paperless-db
- Crunchy Postgres: immich-db

## VolSync Configuration

### Installation

```yaml
# infrastructure/storage/volsync/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: volsync-system
  labels:
    pod-security.kubernetes.io/enforce: privileged
```

### Per-App ReplicationSource Template

```yaml
apiVersion: volsync.backube/v1alpha1
kind: ReplicationSource
metadata:
  name: <app>-backup
  namespace: <namespace>
spec:
  sourcePVC: <pvc-name>
  trigger:
    schedule: "0 2 * * *"  # Daily at 2 AM
  restic:
    pruneIntervalDays: 7
    repository: <app>-repo-secret
    retain:
      daily: 14
    copyMethod: Snapshot
    storageClassName: longhorn
    cacheStorageClassName: longhorn
```

### Per-App ReplicationDestination Template

```yaml
apiVersion: volsync.backube/v1alpha1
kind: ReplicationDestination
metadata:
  name: <app>-restore
  namespace: <namespace>
spec:
  trigger:
    manual: restore-once
  restic:
    repository: <app>-repo-secret
    destinationPVC: <pvc-name>
    copyMethod: Direct
```

### Repository Secret Template

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: <app>-repo-secret
  namespace: <namespace>
type: Opaque
stringData:
  RESTIC_REPOSITORY: s3:http://192.168.10.133:9000/volsync-backups/<namespace>/<app>
  RESTIC_PASSWORD: <kopia-encryption-password>
  AWS_ACCESS_KEY_ID: <from-existing-secret>
  AWS_SECRET_ACCESS_KEY: <from-existing-secret>
```

## Database Native Backups

### CloudNativePG (khoj, paperless)

```yaml
spec:
  backup:
    barmanObjectStore:
      destinationPath: s3://postgres-backups/cnpg/<cluster-name>
      endpointURL: http://192.168.10.133:9000
      s3Credentials:
        accessKeyId:
          name: s3-creds
          key: ACCESS_KEY_ID
        secretAccessKey:
          name: s3-creds
          key: SECRET_ACCESS_KEY
      wal:
        compression: gzip
      data:
        compression: gzip
    retentionPolicy: "14d"

  scheduledBackups:
    - name: daily-backup
      schedule: "0 3 * * *"
      backupOwnerReference: self
```

### Crunchy Postgres (immich)

Similar configuration using pgBackRest stanza pointing to S3.

## Longhorn Changes

### Files to Delete

- `infrastructure/storage/longhorn/recurring-jobs.yaml`
- `infrastructure/storage/longhorn/backup-settings.yaml`
- `infrastructure/storage/longhorn/restore-job.yaml`

### values.yaml Changes

Remove:
- `defaultSettings.backupTarget`
- `defaultSettings.backupTargetCredentialSecret`
- `defaultRecurringJobGroup`

Longhorn becomes pure runtime replication only.

## ArgoCD Sync Waves

| Wave | Components |
|------|------------|
| 0 | ArgoCD, External Secrets, Cilium, 1Password |
| 1 | Longhorn, VolSync |
| 2 | Infrastructure (CNPG, Crunchy, Redis, etc.) |
| 3 | Monitoring |
| 4 | Apps (with ReplicationSource/Destination) |

## Talos Configuration

No changes required. Current Omni-managed Talos has:
- MutatingAdmissionWebhook enabled by default
- Pod Security handled at namespace level

## Restore Procedure

### For App PVCs (VolSync)

1. Delete the existing PVC
2. Update PVC manifest with `dataSourceRef`:
   ```yaml
   spec:
     dataSourceRef:
       kind: ReplicationDestination
       apiGroup: volsync.backube
       name: <app>-restore
   ```
3. Trigger the ReplicationDestination:
   ```bash
   kubectl patch replicationdestination <app>-restore \
     -n <namespace> \
     --type merge \
     -p '{"spec":{"trigger":{"manual":"restore-'$(date +%s)'"}}}'
   ```
4. Apply the PVC manifest

### For Databases (Native)

- CNPG: Update cluster with `bootstrap.recovery.source`
- Crunchy: Use pgBackRest restore command

## Testing Plan

1. Deploy VolSync, verify pods running
2. Check ReplicationSource status for successful backups
3. Verify S3 bucket contains backup data
4. Test restore on a non-critical PVC (e.g., nginx)
5. Validate database backup/restore cycle

## Rollback Plan

If issues arise:
1. VolSync can be removed without affecting running apps
2. Longhorn backup files can be restored from git history
3. Existing S3 backups from Longhorn remain accessible
