# Database Guidelines (CNPG CloudNativePG)

> **Required reading before performing DR recovery or modifying database backups:**
> - `docs/cnpg-disaster-recovery.md` — Full DR procedures, bootstrap decision tree, serverName versioning, troubleshooting

Databases use **CloudNativePG** with Barman backups to RustFS S3 — a **separate backup path** from the PVC/VolSync system.

- **PVC backups**: Kopia on NFS via VolSync (automated by Kyverno)
- **Database backups**: Barman to S3 (SQL-aware `pg_basebackup` + WAL archiving for point-in-time recovery)

Each tool uses its native backup mechanism — see [backup-restore.md](../../docs/backup-restore.md#why-two-backup-systems-nfs-for-pvcs-s3-for-databases) for the full rationale.

## CNPG Cluster Template

```yaml
# infrastructure/database/cloudnative-pg/<app>/cluster.yaml
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: <app>-database
  namespace: cloudnative-pg
spec:
  instances: 1
  imageName: ghcr.io/cloudnative-pg/postgresql:16.2
  bootstrap:
    initdb:
      database: <app>
      owner: <app>
  storage:
    size: 20Gi
    storageClass: longhorn
  backup:
    barmanObjectStore:
      serverName: <app>-database      # IMPORTANT: bump on DR recovery (see below)
      destinationPath: s3://postgres-backups/cnpg/<app>
      endpointURL: http://192.168.10.133:30293
      s3Credentials:
        accessKeyId:
          name: cnpg-s3-credentials
          key: AWS_ACCESS_KEY_ID
        secretAccessKey:
          name: cnpg-s3-credentials
          key: AWS_SECRET_ACCESS_KEY
    retentionPolicy: "14d"
```

**Key differences from PVC backups**:
- Backups use **Barman** (SQL-aware) to RustFS S3, not Kopia to NFS
- **No automatic restore** — recovery requires manual intervention
- **Cannot go through ArgoCD** for recovery — CNPG webhook + SSA = `initdb` always wins
- `serverName` must be bumped after each recovery (e.g. `-v2`, `-v3`) to avoid WAL archive conflicts

**Auto-discovery**: The database AppSet discovers `infrastructure/database/*/*` via glob — no need to add paths to `infrastructure-appset.yaml`. The database AppSet uses `selfHeal: false` so `skip-reconcile` annotations stick during DR recovery.

**Post-recovery ArgoCD sync**: The database AppSet has `ignoreDifferences` for `.spec.bootstrap` and `.spec.externalClusters` on CNPG Clusters, so ArgoCD won't show OutOfSync after recovery (bootstrap diffs between live `recovery` and Git `initdb` are ignored).

**Deprecation notice**: CNPG native Barman support (`spec.backup.barmanObjectStore`) will be removed in CNPG 1.29.0. Migration to the Barman Cloud Plugin is required before upgrading.

## Database Disaster Recovery

**Recovery procedure** (must bypass ArgoCD — SSA + CNPG webhook makes `initdb` always win):

```bash
# 1. Pause ArgoCD (database AppSet preserves skip-reconcile annotations)
kubectl annotate application immich -n argocd argocd.argoproj.io/skip-reconcile=true --overwrite
kubectl annotate application my-apps-immich -n argocd argocd.argoproj.io/skip-reconcile=true --overwrite

# 2. Edit cluster.yaml locally: replace initdb with recovery + externalClusters
#    Set externalClusters.serverName = current backup version
#    Bump backup.serverName to next version

# 3. Render recovery manifest (bypass ArgoCD):
kubectl kustomize infrastructure/database/cloudnative-pg/immich/ \
  | awk '/^apiVersion: postgresql.cnpg.io\/v1/{p=1} p{print} /^---/{if(p) exit}' \
  > /tmp/recovery.yaml

# 4. Delete and recreate:
kubectl delete cluster immich-database -n cloudnative-pg --wait=false
kubectl wait --for=delete cluster/immich-database -n cloudnative-pg --timeout=180s
kubectl create -f /tmp/recovery.yaml

# 5. Wait for recovery:
kubectl get clusters -n cloudnative-pg -w

# 6. Verify data:
kubectl exec -n cloudnative-pg immich-database-1 -- \
  psql -U postgres -d immich -c "SELECT count(*) FROM \"user\";"

# 7. Revert cluster.yaml to initdb (DELETE recovery code, keep bumped serverName)
# 8. Commit and push
# 9. Remove skip-reconcile annotations
```

## Current serverName Versions

Track these — must match for recovery:

| Database | Current backup serverName |
|----------|--------------------------|
| immich | `immich-database-v6` |
| khoj | `khoj-database` (original) |
| paperless | `paperless-database` (original) |

See [docs/cnpg-disaster-recovery.md](../../docs/cnpg-disaster-recovery.md) for full details.
