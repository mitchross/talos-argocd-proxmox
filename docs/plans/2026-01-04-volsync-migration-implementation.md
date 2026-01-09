# VolSync Migration Implementation Plan

---

## ⚠️ THIS PLAN IS OBSOLETE

**Status:** ❌ **REPLACED** (2026-01-08)

**This manual approach was replaced with Kyverno auto-generation:**
- Single ClusterPolicy generates ExternalSecret + ReplicationSource + ReplicationDestination
- Just add `backup: "hourly"` or `backup: "daily"` label to PVC
- Zero manual YAML files needed (down from 36+ files)

**See current implementation:**
- [storage-architecture.md](../storage-architecture.md)
- [infrastructure/controllers/kyverno/volsync-clusterpolicy.yaml](../../infrastructure/controllers/kyverno/volsync-clusterpolicy.yaml)

---

**Original plan below for historical reference:**

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace Longhorn backup/restore with VolSync + database-native backups for reliable daily backups to RustFS.

**Architecture:** VolSync with Kopia backs up 17 Longhorn PVCs daily to RustFS (S3) on TrueNAS. CloudNativePG and Crunchy Postgres use native WAL archiving. Longhorn remains for runtime replication only.

**Tech Stack:** VolSync, Kopia, CloudNativePG barman, Crunchy pgBackRest, External Secrets, ArgoCD

**Design Doc:** `docs/plans/2026-01-04-volsync-migration-design.md`

---

## Phase 1: Install VolSync Operator

### Task 1.1: Create VolSync Directory Structure

**Files:**
- Create: `infrastructure/storage/volsync/`

**Step 1: Create the directory**

```bash
mkdir -p infrastructure/storage/volsync
```

**Step 2: Commit**

```bash
git add infrastructure/storage/volsync
git commit --allow-empty -m "chore: create volsync directory structure"
```

---

### Task 1.2: Create VolSync Namespace

**Files:**
- Create: `infrastructure/storage/volsync/namespace.yaml`

**Step 1: Create namespace manifest**

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: volsync-system
  labels:
    pod-security.kubernetes.io/enforce: privileged
```

**Step 2: Commit**

```bash
git add infrastructure/storage/volsync/namespace.yaml
git commit -m "feat(volsync): add namespace with privileged pod security"
```

---

### Task 1.3: Create VolSync ExternalSecret for S3 Credentials

**Files:**
- Create: `infrastructure/storage/volsync/externalsecret.yaml`

**Step 1: Create ExternalSecret**

This pulls the same MinIO/RustFS credentials from 1Password that Longhorn uses.

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: volsync-s3-credentials
  namespace: volsync-system
spec:
  refreshInterval: "1h"
  secretStoreRef:
    kind: ClusterSecretStore
    name: 1password
  target:
    name: volsync-s3-credentials
    creationPolicy: Owner
  data:
    - secretKey: AWS_ACCESS_KEY_ID
      remoteRef:
        key: minio
        property: minio_access_key
    - secretKey: AWS_SECRET_ACCESS_KEY
      remoteRef:
        key: minio
        property: minio_secret_key
    - secretKey: RESTIC_REPOSITORY
      remoteRef:
        key: minio
        property: minio_endpoint
```

**Step 2: Commit**

```bash
git add infrastructure/storage/volsync/externalsecret.yaml
git commit -m "feat(volsync): add ExternalSecret for S3 credentials from 1Password"
```

---

### Task 1.4: Create Kopia Repository Secret Template

**Files:**
- Create: `infrastructure/storage/volsync/repo-secret-template.yaml`

**Step 1: Create secret template**

This is a reference template. Each app will have its own secret with a unique repository path.

```yaml
# Template for per-app repository secrets
# Copy to each app directory and customize
apiVersion: v1
kind: Secret
metadata:
  name: APP_NAME-volsync-secret
  namespace: APP_NAMESPACE
type: Opaque
stringData:
  # Format: s3:http://TRUENAS_IP:9000/BUCKET/namespace/app
  RESTIC_REPOSITORY: "s3:http://192.168.10.133:9000/volsync-backups/APP_NAMESPACE/APP_NAME"
  RESTIC_PASSWORD: "CHANGE_ME_UNIQUE_PER_REPO"
  AWS_ACCESS_KEY_ID: "FROM_EXTERNAL_SECRET"
  AWS_SECRET_ACCESS_KEY: "FROM_EXTERNAL_SECRET"
```

**Step 2: Commit**

```bash
git add infrastructure/storage/volsync/repo-secret-template.yaml
git commit -m "docs(volsync): add repository secret template for apps"
```

---

### Task 1.5: Create VolSync HelmRelease

**Files:**
- Create: `infrastructure/storage/volsync/helmrelease.yaml`

**Step 1: Create HelmRelease**

```yaml
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmRepository
metadata:
  name: backube
  namespace: volsync-system
spec:
  interval: 24h
  url: https://backube.github.io/helm-charts
---
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: volsync
  namespace: volsync-system
spec:
  interval: 30m
  chart:
    spec:
      chart: volsync
      version: "0.11.0"
      sourceRef:
        kind: HelmRepository
        name: backube
        namespace: volsync-system
  values:
    manageCRDs: true
    metrics:
      enabled: true
```

**Step 2: Commit**

```bash
git add infrastructure/storage/volsync/helmrelease.yaml
git commit -m "feat(volsync): add HelmRelease for VolSync operator"
```

---

### Task 1.6: Create VolSync Kustomization

**Files:**
- Create: `infrastructure/storage/volsync/kustomization.yaml`

**Step 1: Create kustomization**

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: volsync-system
resources:
  - namespace.yaml
  - externalsecret.yaml
  - helmrelease.yaml
```

**Step 2: Commit**

```bash
git add infrastructure/storage/volsync/kustomization.yaml
git commit -m "feat(volsync): add kustomization to bundle resources"
```

---

### Task 1.7: Create ArgoCD Application for VolSync

**Files:**
- Create: `infrastructure/controllers/argocd/apps/volsync-app.yaml`

**Step 1: Create ArgoCD Application**

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: volsync
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "1"
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  source:
    repoURL: https://github.com/mitchross/talos-argocd-proxmox.git
    targetRevision: HEAD
    path: infrastructure/storage/volsync
  destination:
    server: https://kubernetes.default.svc
    namespace: volsync-system
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

**Step 2: Commit**

```bash
git add infrastructure/controllers/argocd/apps/volsync-app.yaml
git commit -m "feat(volsync): add ArgoCD Application in sync-wave 1"
```

---

## Phase 2: Remove Longhorn Backup Components

### Task 2.1: Delete Longhorn Recurring Jobs

**Files:**
- Delete: `infrastructure/storage/longhorn/recurring-jobs.yaml`

**Step 1: Remove the file**

```bash
rm infrastructure/storage/longhorn/recurring-jobs.yaml
```

**Step 2: Commit**

```bash
git add -A infrastructure/storage/longhorn/recurring-jobs.yaml
git commit -m "refactor(longhorn): remove recurring-jobs, VolSync handles backups now"
```

---

### Task 2.2: Delete Longhorn Backup Settings

**Files:**
- Delete: `infrastructure/storage/longhorn/backup-settings.yaml`

**Step 1: Remove the file**

```bash
rm infrastructure/storage/longhorn/backup-settings.yaml
```

**Step 2: Commit**

```bash
git add -A infrastructure/storage/longhorn/backup-settings.yaml
git commit -m "refactor(longhorn): remove backup-settings, VolSync handles backups now"
```

---

### Task 2.3: Delete Longhorn Restore Job

**Files:**
- Delete: `infrastructure/storage/longhorn/restore-job.yaml`

**Step 1: Remove the file**

```bash
rm infrastructure/storage/longhorn/restore-job.yaml
```

**Step 2: Commit**

```bash
git add -A infrastructure/storage/longhorn/restore-job.yaml
git commit -m "refactor(longhorn): remove restore-job, VolSync ReplicationDestination replaces it"
```

---

### Task 2.4: Update Longhorn Kustomization

**Files:**
- Modify: `infrastructure/storage/longhorn/kustomization.yaml`

**Step 1: Remove deleted files from resources**

Update to:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: longhorn-system
resources:
  - namespace.yaml
  - httproute.yaml
  - externalsecret.yaml
  - node-failure-settings.yaml
helmCharts:
  - name: longhorn
    repo: https://charts.longhorn.io
    version: 1.10.1
    releaseName: longhorn
    namespace: longhorn-system
    valuesFile: values.yaml
    includeCRDs: true
```

**Step 2: Commit**

```bash
git add infrastructure/storage/longhorn/kustomization.yaml
git commit -m "refactor(longhorn): update kustomization after removing backup files"
```

---

### Task 2.5: Update Longhorn values.yaml

**Files:**
- Modify: `infrastructure/storage/longhorn/values.yaml`

**Step 1: Remove backup-related settings**

Remove the line `default-recurring-job-group: "default"` from defaultSettings.

Updated values.yaml:

```yaml
defaultSettings:
  defaultDataPath: "/var/lib/longhorn"
  storageMinimalAvailablePercentage: "25"
  storageOverProvisioningPercentage: "100"
  allowRecurringJobWhileVolumeDetached: "true"
  replicaAutoBalance: "best-effort"
  fastReplicaRebuildEnabled: "true"
  engineReplicaTimeout: '{"v1":"8"}'
  guaranteedInstanceManagerCPU: "8"
preUpgradeChecker:
  jobEnabled: false
persistence:
  defaultClass: true
  defaultClassReplicaCount: 2
  defaultFsType: ext4
  reclaimPolicy: Delete
ingress:
  enabled: false
```

**Step 2: Commit**

```bash
git add infrastructure/storage/longhorn/values.yaml
git commit -m "refactor(longhorn): remove default-recurring-job-group setting"
```

---

## Phase 3: Add VolSync to Applications

Each app needs:
1. A Secret for S3/Kopia credentials
2. A ReplicationSource for daily backups
3. A ReplicationDestination for restore capability

### Task 3.1: Create Shared ExternalSecret for App Namespaces

**Files:**
- Create: `infrastructure/storage/volsync/app-secret-externalsecret.yaml`

**Step 1: Create ExternalSecret that apps can reference**

Apps will use an ExternalSecret in their namespace to get S3 creds + a unique Kopia password.

```yaml
# This file documents the pattern - each app creates its own ExternalSecret
# pulling from the same 1Password items
#
# Required 1Password items:
# - minio: minio_access_key, minio_secret_key, minio_endpoint
# - volsync-kopia: password (shared encryption password for all repos)
```

**Step 2: Commit**

```bash
git add infrastructure/storage/volsync/app-secret-externalsecret.yaml
git commit -m "docs(volsync): document app ExternalSecret pattern"
```

---

### Task 3.2: Home Assistant - Add VolSync Backup

**Files:**
- Create: `my-apps/home/home-assistant/volsync-secret.yaml`
- Create: `my-apps/home/home-assistant/replicationsource.yaml`
- Create: `my-apps/home/home-assistant/replicationdestination.yaml`
- Modify: `my-apps/home/home-assistant/kustomization.yaml`

**Step 1: Create volsync-secret.yaml**

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: home-assistant-volsync-secret
  namespace: home-assistant
spec:
  refreshInterval: "1h"
  secretStoreRef:
    kind: ClusterSecretStore
    name: 1password
  target:
    name: home-assistant-volsync-secret
    creationPolicy: Owner
    template:
      engineVersion: v2
      data:
        RESTIC_REPOSITORY: "s3:http://192.168.10.133:9000/volsync-backups/home-assistant/config"
        RESTIC_PASSWORD: "{{ .kopia_password }}"
        AWS_ACCESS_KEY_ID: "{{ .access_key }}"
        AWS_SECRET_ACCESS_KEY: "{{ .secret_key }}"
  data:
    - secretKey: access_key
      remoteRef:
        key: minio
        property: minio_access_key
    - secretKey: secret_key
      remoteRef:
        key: minio
        property: minio_secret_key
    - secretKey: kopia_password
      remoteRef:
        key: volsync-kopia
        property: password
```

**Step 2: Create replicationsource.yaml**

```yaml
apiVersion: volsync.backube/v1alpha1
kind: ReplicationSource
metadata:
  name: home-assistant-config-backup
  namespace: home-assistant
spec:
  sourcePVC: home-assistant-config
  trigger:
    schedule: "0 2 * * *"
  restic:
    pruneIntervalDays: 7
    repository: home-assistant-volsync-secret
    retain:
      daily: 14
    copyMethod: Snapshot
    storageClassName: longhorn
    cacheStorageClassName: longhorn
```

**Step 3: Create replicationdestination.yaml**

```yaml
apiVersion: volsync.backube/v1alpha1
kind: ReplicationDestination
metadata:
  name: home-assistant-config-restore
  namespace: home-assistant
spec:
  trigger:
    manual: restore-once
  restic:
    repository: home-assistant-volsync-secret
    copyMethod: Direct
    storageClassName: longhorn
    accessModes:
      - ReadWriteOnce
    capacity: 10Gi
```

**Step 4: Update kustomization.yaml**

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: home-assistant

metadata:
  name: home-assistant
  annotations:
    config.kubernetes.io/local-config: "true"

resources:
- namespace.yaml
- pvc.yaml
- service.yaml
- deployment.yaml
- httproute.yaml
- volsync-secret.yaml
- replicationsource.yaml
- replicationdestination.yaml

commonLabels:
  app.kubernetes.io/managed-by: kustomize
  environment: production

generatorOptions:
  disableNameSuffixHash: true

configMapGenerator:
- name: home-assistant-config
  files:
  - configuration.yaml
  - automations.yaml
  - scripts.yaml
  - scenes.yaml
  options:
    disableNameSuffixHash: true
```

**Step 5: Commit**

```bash
git add my-apps/home/home-assistant/volsync-secret.yaml \
        my-apps/home/home-assistant/replicationsource.yaml \
        my-apps/home/home-assistant/replicationdestination.yaml \
        my-apps/home/home-assistant/kustomization.yaml
git commit -m "feat(home-assistant): add VolSync backup configuration"
```

---

### Task 3.3: Paperless-NGX - Add VolSync Backup

**Files:**
- Create: `my-apps/home/paperless-ngx/volsync-secret.yaml`
- Create: `my-apps/home/paperless-ngx/replicationsource.yaml`
- Create: `my-apps/home/paperless-ngx/replicationdestination.yaml`
- Modify: `my-apps/home/paperless-ngx/kustomization.yaml`

**Step 1: Create volsync-secret.yaml**

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: paperless-volsync-secret
  namespace: paperless-ngx
spec:
  refreshInterval: "1h"
  secretStoreRef:
    kind: ClusterSecretStore
    name: 1password
  target:
    name: paperless-volsync-secret
    creationPolicy: Owner
    template:
      engineVersion: v2
      data:
        RESTIC_REPOSITORY: "s3:http://192.168.10.133:9000/volsync-backups/paperless-ngx/data"
        RESTIC_PASSWORD: "{{ .kopia_password }}"
        AWS_ACCESS_KEY_ID: "{{ .access_key }}"
        AWS_SECRET_ACCESS_KEY: "{{ .secret_key }}"
  data:
    - secretKey: access_key
      remoteRef:
        key: minio
        property: minio_access_key
    - secretKey: secret_key
      remoteRef:
        key: minio
        property: minio_secret_key
    - secretKey: kopia_password
      remoteRef:
        key: volsync-kopia
        property: password
```

**Step 2: Create replicationsource.yaml**

```yaml
apiVersion: volsync.backube/v1alpha1
kind: ReplicationSource
metadata:
  name: paperless-data-backup
  namespace: paperless-ngx
spec:
  sourcePVC: paperless-data
  trigger:
    schedule: "0 2 * * *"
  restic:
    pruneIntervalDays: 7
    repository: paperless-volsync-secret
    retain:
      daily: 14
    copyMethod: Snapshot
    storageClassName: longhorn
    cacheStorageClassName: longhorn
```

**Step 3: Create replicationdestination.yaml**

```yaml
apiVersion: volsync.backube/v1alpha1
kind: ReplicationDestination
metadata:
  name: paperless-data-restore
  namespace: paperless-ngx
spec:
  trigger:
    manual: restore-once
  restic:
    repository: paperless-volsync-secret
    copyMethod: Direct
    storageClassName: longhorn
    accessModes:
      - ReadWriteOnce
    capacity: 20Gi
```

**Step 4: Update kustomization.yaml to include VolSync resources**

Add to resources list:
- volsync-secret.yaml
- replicationsource.yaml
- replicationdestination.yaml

**Step 5: Commit**

```bash
git add my-apps/home/paperless-ngx/volsync-secret.yaml \
        my-apps/home/paperless-ngx/replicationsource.yaml \
        my-apps/home/paperless-ngx/replicationdestination.yaml \
        my-apps/home/paperless-ngx/kustomization.yaml
git commit -m "feat(paperless-ngx): add VolSync backup configuration"
```

---

### Task 3.4-3.17: Remaining Apps

Repeat the pattern from Task 3.2/3.3 for each remaining app:

| Task | App | Namespace | PVC Name | Capacity |
|------|-----|-----------|----------|----------|
| 3.4 | frigate/mqtt | frigate | mqtt-data | 1Gi |
| 3.5 | n8n | n8n | n8n-data | 5Gi |
| 3.6 | nginx | nginx | nginx-data | 1Gi |
| 3.7 | fizzy | fizzy | fizzy-data | 5Gi |
| 3.8 | immich | immich | immich-library | 100Gi |
| 3.9 | jellyfin (config) | jellyfin | jellyfin-config | 10Gi |
| 3.10 | jellyfin (media) | jellyfin | jellyfin-media | 50Gi |
| 3.11 | karakeep/data | karakeep | karakeep-data | 10Gi |
| 3.12 | karakeep/meilisearch | karakeep | meilisearch-data | 5Gi |
| 3.13 | plex | plex | plex-config | 20Gi |
| 3.14 | homepage-dashboard | homepage | homepage-config | 1Gi |
| 3.15 | nestmtx | nestmtx | nestmtx-data | 5Gi |
| 3.16 | searxng/redis | searxng | redis-data | 1Gi |
| 3.17 | open-webui | open-webui | open-webui-data | 10Gi |
| 3.18 | khoj | khoj | khoj-data | 5Gi |
| 3.19 | container-registry | container-registry | registry-data | 50Gi |
| 3.20 | redis-instance | redis | redis-data | 5Gi |

For each app:
1. Create `volsync-secret.yaml` (ExternalSecret with templated S3 path)
2. Create `replicationsource.yaml` (daily @ 2AM, 14-day retention)
3. Create `replicationdestination.yaml` (manual trigger, matching capacity)
4. Update `kustomization.yaml` to include new resources
5. Commit with message: `feat(<app>): add VolSync backup configuration`

---

## Phase 4: Configure Database Native Backups

### Task 4.1: Add S3 Backup to Khoj CNPG Cluster

**Files:**
- Modify: `infrastructure/database/cloudnative-pg/khoj/cluster.yaml`

**Step 1: Add backup configuration**

Add to spec section:

```yaml
  backup:
    barmanObjectStore:
      destinationPath: s3://postgres-backups/cnpg/khoj
      endpointURL: http://192.168.10.133:9000
      s3Credentials:
        accessKeyId:
          name: cnpg-s3-credentials
          key: AWS_ACCESS_KEY_ID
        secretAccessKey:
          name: cnpg-s3-credentials
          key: AWS_SECRET_ACCESS_KEY
      wal:
        compression: gzip
      data:
        compression: gzip
    retentionPolicy: "14d"
```

**Step 2: Create ExternalSecret for CNPG S3 credentials**

Create `infrastructure/database/cloudnative-pg/externalsecret.yaml`:

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: cnpg-s3-credentials
  namespace: cloudnative-pg
spec:
  refreshInterval: "1h"
  secretStoreRef:
    kind: ClusterSecretStore
    name: 1password
  target:
    name: cnpg-s3-credentials
    creationPolicy: Owner
  data:
    - secretKey: AWS_ACCESS_KEY_ID
      remoteRef:
        key: minio
        property: minio_access_key
    - secretKey: AWS_SECRET_ACCESS_KEY
      remoteRef:
        key: minio
        property: minio_secret_key
```

**Step 3: Create ScheduledBackup**

Create `infrastructure/database/cloudnative-pg/khoj/scheduled-backup.yaml`:

```yaml
apiVersion: postgresql.cnpg.io/v1
kind: ScheduledBackup
metadata:
  name: khoj-daily-backup
  namespace: cloudnative-pg
spec:
  schedule: "0 3 * * *"
  backupOwnerReference: self
  cluster:
    name: khoj-database
  immediate: true
```

**Step 4: Update kustomization**

**Step 5: Commit**

```bash
git add infrastructure/database/cloudnative-pg/
git commit -m "feat(cnpg-khoj): add S3 WAL archiving and scheduled backups"
```

---

### Task 4.2: Add S3 Backup to Paperless CNPG Cluster

**Files:**
- Modify: `infrastructure/database/cloudnative-pg/paperless/cluster.yaml`
- Create: `infrastructure/database/cloudnative-pg/paperless/scheduled-backup.yaml`

Same pattern as Task 4.1, with:
- destinationPath: `s3://postgres-backups/cnpg/paperless`
- cluster name: `paperless-database`

**Commit:**

```bash
git add infrastructure/database/cloudnative-pg/paperless/
git commit -m "feat(cnpg-paperless): add S3 WAL archiving and scheduled backups"
```

---

### Task 4.3: Add S3 Backup to Immich Crunchy Cluster

**Files:**
- Modify: `infrastructure/database/crunchy-postgres/immich/cluster.yaml`

**Step 1: Add pgBackRest S3 configuration**

This requires adding the pgBackRest stanza to the Crunchy PostgresCluster spec.

**Note:** Crunchy Postgres Operator uses pgBackRest for backups. The configuration pattern differs from CNPG.

```yaml
  backups:
    pgbackrest:
      repos:
        - name: repo1
          s3:
            bucket: postgres-backups
            endpoint: http://192.168.10.133:9000
            region: us-east-1
          schedules:
            full: "0 3 * * 0"      # Weekly full on Sunday
            differential: "0 3 * * 1-6"  # Daily differential
```

**Step 2: Commit**

```bash
git add infrastructure/database/crunchy-postgres/immich/
git commit -m "feat(crunchy-immich): add pgBackRest S3 backup configuration"
```

---

## Phase 5: Create 1Password Item for Kopia Password

### Task 5.1: Document Required 1Password Item

**Files:**
- Create: `docs/secrets/volsync-secrets.md`

**Step 1: Document the required secret**

```markdown
# VolSync Secrets Setup

## Required 1Password Items

### volsync-kopia

Create a new item in 1Password vault with:

- **Item name:** `volsync-kopia`
- **Field:** `password` - A strong random password (32+ characters)

This password encrypts all Kopia/Restic backup repositories.

**Generate with:**
```bash
openssl rand -base64 32
```

### Existing Items Used

- **minio** - Already exists, provides:
  - `minio_access_key`
  - `minio_secret_key`
  - `minio_endpoint`
```

**Step 2: Commit**

```bash
git add docs/secrets/volsync-secrets.md
git commit -m "docs: add VolSync 1Password setup instructions"
```

---

## Phase 6: Update Documentation

### Task 6.1: Update Storage Architecture Doc

**Files:**
- Modify: `docs/storage-architecture.md`

**Step 1: Replace Longhorn backup section with VolSync**

Update the document to reflect:
- Longhorn is now runtime replication only
- VolSync handles all PVC backups
- CNPG/Crunchy handle database backups natively
- Restore procedure uses ReplicationDestination

**Step 2: Commit**

```bash
git add docs/storage-architecture.md
git commit -m "docs: update storage architecture for VolSync migration"
```

---

## Phase 7: Verification

### Task 7.1: Verify VolSync Deployment

**Step 1: Check VolSync pods**

```bash
kubectl get pods -n volsync-system
```

Expected: VolSync controller pod running

**Step 2: Check CRDs**

```bash
kubectl get crd | grep volsync
```

Expected: replicationsources.volsync.backube, replicationdestinations.volsync.backube

---

### Task 7.2: Verify ReplicationSource Status

**Step 1: Check all ReplicationSources**

```bash
kubectl get replicationsource -A
```

**Step 2: Check a specific one**

```bash
kubectl describe replicationsource home-assistant-config-backup -n home-assistant
```

Expected: Status shows successful sync after first scheduled run

---

### Task 7.3: Verify S3 Bucket Contents

**Step 1: List bucket contents**

```bash
# Using mc (MinIO client) or aws cli
mc ls truenas/volsync-backups/
```

Expected: Directories for each namespace/app with Kopia data

---

### Task 7.4: Test Restore Procedure

**Step 1: Trigger a ReplicationDestination**

```bash
kubectl patch replicationdestination nginx-data-restore -n nginx \
  --type merge \
  -p '{"spec":{"trigger":{"manual":"restore-test-'$(date +%s)'"}}}'
```

**Step 2: Watch the restore**

```bash
kubectl get replicationdestination nginx-data-restore -n nginx -w
```

**Step 3: Verify restore PVC is created**

```bash
kubectl get pvc -n nginx
```

---

## Summary Checklist

- [ ] Phase 1: VolSync operator installed (7 tasks)
- [ ] Phase 2: Longhorn backup components removed (5 tasks)
- [ ] Phase 3: All 17+ apps have VolSync config (17 tasks)
- [ ] Phase 4: Database native backups configured (3 tasks)
- [ ] Phase 5: 1Password item created (1 task)
- [ ] Phase 6: Documentation updated (1 task)
- [ ] Phase 7: Verification complete (4 tasks)

**Total: ~38 tasks**
