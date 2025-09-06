# Longhorn Backup Configuration Summary

Generated on: September 5, 2025

## Overview

Your k3s-argocd-proxmox cluster now has comprehensive Longhorn backup coverage with MinIO S3 storage on TrueNAS. All PVCs using `storageClassName: longhorn` are configured for automatic backups.

## Backup Infrastructure

### S3 Backend Configuration
- **Target**: `s3://longhorn-backups@us-east-1/`
- **Storage**: MinIO on TrueNAS at `192.168.10.133`
- **Credentials**: Managed via External Secrets (1Password)
- **Compression**: gzip
- **Concurrent Limit**: 2 backups at once

### Backup Tiers & Schedules

#### 🔴 Critical Tier (Databases, Core Infrastructure)
- **Snapshots**: Every hour (24 retained = 1 day)
- **Backups**: Daily at 2 AM (30 retained = 1 month)
- **Applications**: Redis, PostgreSQL, Container Registry

#### 🟡 Important Tier (User Data, Configurations)
- **Snapshots**: Every 4 hours (12 retained = 2 days)  
- **Backups**: Daily at 3 AM (14 retained = 2 weeks)
- **Applications**: Immich, Home Assistant, Paperless-NGX, AI workloads, Monitoring

#### 🔵 Standard Tier (Cache, Logs, Development)
- **Snapshots**: Daily at 4 AM (7 retained = 1 week)
- **Backups**: Weekly on Sunday at 5 AM (4 retained = 1 month)
- **Applications**: Jellyfin config, Development tools, Cache storage

#### 🌐 Weekly Full System Backup
- **Schedule**: Sunday at 1 AM
- **Scope**: ALL volumes (critical + important + standard)
- **Retention**: 8 weeks (2 months)

## PVC Backup Configuration by Application

### Infrastructure Components

| PVC Name | Namespace | Storage | Backup Tier | Application |
|----------|-----------|---------|-------------|-------------|
| `registry-pvc` | kube-system | 10Gi | 🔴 Critical | Container Registry |
| `redis-data-redis-master-0` | redis-instance | 10Gi | 🔴 Critical | Redis Database |

### Monitoring Stack

| PVC Name | Namespace | Storage | Backup Tier | Application |
|----------|-----------|---------|-------------|-------------|
| Prometheus PVC | monitoring | 20Gi | 🟡 Important | Prometheus Metrics |
| Alertmanager PVC | monitoring | 2Gi | 🟡 Important | Alert Management |
| Grafana PVC | monitoring | 5Gi | 🟡 Important | Dashboard Data |

### AI Applications

| PVC Name | Namespace | Storage | Backup Tier | Application |
|----------|-----------|---------|-------------|-------------|
| `khoj-data` | khoj | 10Gi | 🟡 Important | AI Assistant Data |
| `khoj-postgres-data` | khoj | 5Gi | 🟡 Important | AI Assistant DB |
| `ollama-webui-data` | ollama-webui | 5Gi | 🟡 Important | Chat Interface |
| `ollama-webui-storage-pvc` | ollama-webui | 5Gi | 🟡 Important | Chat Storage |

### Home Automation

| PVC Name | Namespace | Storage | Backup Tier | Application |
|----------|-----------|---------|-------------|-------------|
| `home-assistant-config` | home-assistant | 10Gi | 🟡 Important | Smart Home Config |
| `frigate-config-pvc` | frigate | 5Gi | 🟡 Important | Video Surveillance |
| `mqtt-data-pvc` | frigate | 1Gi | 🟡 Important | MQTT Broker |
| `paperless-data-pvc` | paperless-ngx | 10Gi | 🟡 Important | Document Data |
| `paperless-media-pvc` | paperless-ngx | 20Gi | 🟡 Important | Document Media |
| `paperless-consume-pvc` | paperless-ngx | 5Gi | 🟡 Important | Document Intake |
| `paperless-export-pvc` | paperless-ngx | 5Gi | 🟡 Important | Document Export |

### Media Applications

| PVC Name | Namespace | Storage | Backup Tier | Application |
|----------|-----------|---------|-------------|-------------|
| `immich-data` | immich | 20Gi | 🟡 Important | Photo Management |
| `immich-library` | immich | 100Gi | 🟡 Important | Photo Library |
| `immich-cache` | immich | 10Gi | 🟡 Important | ML Cache |
| `plex-config` | plex | 10Gi | 🟡 Important | Media Server Config |
| `plex-transcode` | plex | 10Gi | 🔵 Standard | Transcode Cache |
| `plex-logs` | plex | 1Gi | 🔵 Standard | Application Logs |
| `jellyfin-config-pvc` | jellyfin | 1Gi | 🔵 Standard | Media Server Config |
| `data-pvc` | hoarder | 10Gi | 🟡 Important | Bookmark Data |
| `meilisearch-pvc` | hoarder | 10Gi | 🔵 Standard | Search Index |
| `homepage-config-pvc` | homepage-dashboard | 1Gi | 🔵 Standard | Dashboard Config |
| `tubearchivist-cache-pvc` | tubearchivist | 50Gi | 🔵 Standard | Video Cache |
| `tubearchivist-redis-pvc` | tubearchivist | 1Gi | 🔵 Standard | Cache Database |
| `es-data` | tubearchivist | 50Gi | 🟡 Important | Search Data |
| `nestmtx-storage-pvc` | nestmtx | 10Gi | 🔵 Standard | Streaming Cache |

### Privacy Applications

| PVC Name | Namespace | Storage | Backup Tier | Application |
|----------|-----------|---------|-------------|-------------|
| `proxitok-cache-pvc` | proxitok | 10Gi | 🔵 Standard | TikTok Proxy Cache |
| `redis-data-pvc` | searxng | 1Gi | 🔵 Standard | Search Cache |

### Development Tools

| PVC Name | Namespace | Storage | Backup Tier | Application |
|----------|-----------|---------|-------------|-------------|
| `nginx-storage` | nginx | 1Gi | 🔵 Standard | Web Server Config |

## MinIO S3 Bucket Structure

```
longhorn-backups/
├── backupstore/
│   ├── volumes/
│   │   ├── <volume-name>/
│   │   │   ├── backups/
│   │   │   │   ├── backup-<timestamp>/
│   │   │   │   └── backup-<timestamp>/
│   │   │   └── volume.cfg
│   │   └── ...
│   └── backup_volumes.cfg
```

## Monitoring & Verification

### Key Commands

```bash
# Check backup system health
./scripts/verify-longhorn-backups.sh

# View all backups
kubectl get backups -n longhorn-system

# Check backup target status  
kubectl get backuptarget -n longhorn-system

# Monitor recurring jobs
kubectl get recurringjobs -n longhorn-system

# View volume backup status
kubectl get volumes -n longhorn-system
```

### Web Interfaces

- **Longhorn UI**: Access via HTTPRoute at your cluster domain
- **MinIO Console**: `http://192.168.10.133:9002`
- **TrueNAS**: `http://192.168.10.133` (main interface)

## Backup Verification Checklist

- [ ] All Longhorn PVCs have `longhorn.io/recurring-job-*` annotations
- [ ] BackupTarget shows as "Available"
- [ ] External Secrets are syncing credentials
- [ ] MinIO bucket `longhorn-backups` exists and is accessible
- [ ] Recent backups are appearing in `kubectl get backups`
- [ ] No backup job failures in recurring job status

## Emergency Procedures

For disaster recovery procedures, see:
- `docs/runbooks/longhorn-emergency-procedures.md`
- `docs/longhorn-backup-guide.md`

## Next Steps

1. **Verify Configuration**: Run `./scripts/verify-longhorn-backups.sh`
2. **Test Restore**: Practice restoring a volume from backup
3. **Monitor**: Set up alerts for backup failures
4. **Document**: Update any application-specific restore procedures

---

**Last Updated**: September 5, 2025  
**Configuration Files**: 
- `infrastructure/storage/longhorn/backup-settings.yaml`
- `infrastructure/storage/longhorn/recurring-jobs.yaml`
- All PVC files with `storageClassName: longhorn`