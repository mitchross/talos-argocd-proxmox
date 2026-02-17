# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a production-grade GitOps Kubernetes cluster running on **Talos OS** with **self-managing ArgoCD**. The key differentiator is that ArgoCD manages its own configuration and automatically discovers applications through directory structure - no manual Application manifests needed.

**Tech Stack**: Talos OS + ArgoCD + Cilium (Gateway API) + Longhorn + 1Password + GPU support

## Core Architecture Pattern: GitOps Self-Management

```
Manual Bootstrap → ArgoCD → Root App → ApplicationSets → Auto-discovered Apps
```

1. **Bootstrap once**: Apply ArgoCD manifests manually via `scripts/bootstrap-argocd.sh`
2. **Root app triggers**: Points ArgoCD to scan `infrastructure/controllers/argocd/apps/`
3. **ApplicationSets discover**: Three ApplicationSets scan for directories and auto-create Applications
4. **Everything else is automatic**: Add directory + `kustomization.yaml` = deployed app

**Critical Understanding**: Directory = Application
```
my-apps/ai/ollama/          → ArgoCD Application "ollama"
infrastructure/storage/longhorn/ → ArgoCD Application "longhorn"
monitoring/prometheus-stack/    → ArgoCD Application "prometheus-stack"
```

## Essential Commands

### Bootstrap New Cluster

```bash
# Full bootstrap sequence (after Talos cluster is provisioned)
./scripts/bootstrap-argocd.sh

# Monitor application sync progress
kubectl get applications -n argocd -w

# View sync wave order
kubectl get applications -n argocd -o custom-columns=NAME:.metadata.name,WAVE:.metadata.annotations.argocd\\.argoproj\\.io/sync-wave,STATUS:.status.sync.status
```

### ArgoCD Operations

```bash
# Check application sync status
kubectl get applications -n argocd

# Force refresh of root application (re-discovers apps)
kubectl delete application root -n argocd
kubectl apply -f infrastructure/controllers/argocd/root.yaml

# Check ApplicationSet discovery
kubectl get applicationsets -n argocd
kubectl describe applicationset infrastructure -n argocd

# Emergency reset (removes all applications)
kubectl get applications -n argocd -o name | xargs -I{} kubectl patch {} -n argocd --type json -p '[{"op": "remove","path": "/metadata/finalizers"}]'
kubectl delete applications --all -n argocd
./scripts/bootstrap-argocd.sh
```

### Talos Operations

```bash
# Node health check
talosctl health --nodes <node-ip>

# View system logs
talosctl logs -n <node-ip> -k

# Apply configuration changes
talosctl apply-config --nodes <node-ip> --file <config.yaml>

# Upgrade Talos version
talosctl upgrade --nodes <node-ip> --image <installer-image>
```

### Testing & Verification

```bash
# Verify Cilium networking
cilium status
cilium connectivity test

# Check External Secrets are syncing
kubectl get externalsecret -A

# Verify Longhorn storage
kubectl get pods -n longhorn-system
kubectl get pvc -A

# Check GPU nodes
kubectl get nodes -l feature.node.kubernetes.io/pci-0300_10de.present=true

# Test Gateway API routing
kubectl get gateway -A
kubectl get httproute -A

# Verify backup system (Kyverno + VolSync)
kubectl get clusterpolicy volsync-pvc-backup-restore
kubectl get replicationsource -A
kubectl get replicationdestination -A
kubectl get pods -n volsync-system

# Check PVC Plumber (backup checker)
kubectl get pods -n volsync-system -l app.kubernetes.io/name=pvc-plumber
```

## Sync Wave Architecture

Applications deploy in strict order to prevent race conditions:

| Wave | Component | Purpose |
|------|-----------|---------|
| **0** | Foundation | Cilium (CNI), ArgoCD, 1Password Connect, External Secrets, AppProjects |
| **1** | Storage | Longhorn, VolumeSnapshot Controller, VolSync |
| **2** | PVC Plumber | Backup existence checker (FAIL-CLOSED gate: PVC creation denied if Plumber is down) |
| **3** | Kyverno | Policy engine (standalone App, must register webhooks before app PVCs are created) |
| **4** | Infrastructure AppSet | Deploys from explicit path list: cert-manager, external-dns, GPU operators, gateway, databases, etc. |
| **5** | Monitoring AppSet | Discovers `monitoring/*` applications |
| **6** | My-Apps AppSet | Discovers `my-apps/*/*` applications |

**Why this matters**:
- Longhorn won't deploy until Cilium + External Secrets are healthy
- PVC Plumber (Wave 2) must run before Kyverno (Wave 3) because Kyverno policies call PVC Plumber API
- Kyverno (Wave 3) is a **standalone Application** (not in the Infrastructure AppSet) to guarantee its webhooks are registered before any app PVCs are created. ApplicationSets are considered "healthy" immediately upon creation, so putting Kyverno in an AppSet would race with app deployment.
- **FAIL-CLOSED**: If PVC Plumber is down, Kyverno denies creation of backup-labeled PVCs. Apps retry via ArgoCD backoff until Plumber is healthy. This prevents data loss during disaster recovery.
- cert-manager, GPU operators etc. deploy via Infrastructure AppSet (Wave 4) before user apps (Wave 6)
- This prevents "chicken-and-egg" dependency issues and SSD thrashing

**Important**: The Infrastructure AppSet uses an explicit list of paths (not glob discovery). To add a new infrastructure component, you must add its path to `infrastructure/controllers/argocd/apps/infrastructure-appset.yaml`.

## Directory Structure

```
infrastructure/          # Core cluster components (Wave 4)
├── controllers/        # Operators and system controllers
├── database/          # Database operators and instances
├── networking/        # Cilium, Gateway API, DNS
└── storage/           # Longhorn, NFS, SMB, Local storage

monitoring/             # Observability stack (Wave 5)
├── prometheus-stack/  # Prometheus, Grafana, Alertmanager
├── loki-stack/        # Log aggregation
└── tempo/             # Distributed tracing

my-apps/                # User applications (Wave 6)
├── ai/                # GPU workloads (ollama, comfyui)
├── development/       # Dev tools (gitea, kafka, temporal)
├── home/              # Home automation (home-assistant, frigate)
├── media/             # Media services (immich, jellyfin, plex)
└── common/            # Shared Kustomize components

scripts/                # Automation tools
omni/                   # Omni (Sidero) deployment configs
docs/                   # Documentation
```

## Adding New Applications

### Minimal Application (No storage/secrets)

```bash
# 1. Create directory structure
mkdir -p my-apps/category/app-name

# 2. Create required files
cat > my-apps/category/app-name/namespace.yaml <<EOF
apiVersion: v1
kind: Namespace
metadata:
  name: app-name
EOF

cat > my-apps/category/app-name/kustomization.yaml <<EOF
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: app-name

resources:
- namespace.yaml
- deployment.yaml
- service.yaml
EOF

# 3. Git commit - ArgoCD discovers automatically
git add my-apps/category/app-name
git commit -m "Add app-name application"
git push
```

### Application with Web Access

Services MUST have named ports for HTTPRoute to work:

```yaml
# service.yaml
spec:
  ports:
    - name: http        # CRITICAL - HTTPRoute fails silently without this
      port: 8080
      targetPort: 8080

# httproute.yaml
apiVersion: gateway.networking.k8s.io/v1beta1
kind: HTTPRoute
metadata:
  name: app-route
  namespace: app-name
spec:
  parentRefs:
  - kind: Gateway
    name: gateway-external
    namespace: gateway
  hostnames:
  - app.vanillax.me
  rules:
  - backendRefs:
    - name: app-service
      port: 8080
```

### Application with GPU Requirements

Reference `my-apps/ai/comfyui/` for complete pattern:

```yaml
spec:
  template:
    spec:
      # Select GPU nodes
      nodeSelector:
        feature.node.kubernetes.io/pci-0300_10de.present: "true"

      # NVIDIA runtime for CUDA
      runtimeClassName: nvidia

      # Priority to prevent eviction
      priorityClassName: gpu-workload-preemptible

      # Allow scheduling on GPU nodes
      tolerations:
      - key: nvidia.com/gpu
        operator: Exists
        effect: NoSchedule

      containers:
      - name: app
        resources:
          requests:
            nvidia.com/gpu: "1"
          limits:
            nvidia.com/gpu: "1"
```

### Application with Secrets (1Password)

```yaml
# externalsecret.yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: app-secrets
  namespace: app-name
spec:
  refreshInterval: "1h"
  secretStoreRef:
    kind: ClusterSecretStore
    name: 1password
  target:
    name: app-secrets
    creationPolicy: Owner
  data:
  - secretKey: API_KEY
    remoteRef:
      key: app-name           # 1Password item name
      property: api_key       # Field in 1Password item

# Then reference in deployment:
envFrom:
- secretRef:
    name: app-secrets
```

### Application with Persistent Storage + Backups

```yaml
# pvc.yaml - Add backup label for automatic Kyverno backup/restore
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: app-data
  namespace: app-name
  labels:
    app: app-name
    backup: "daily"  # Kyverno will auto-generate backup resources
spec:
  accessModes:
  - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
  storageClassName: longhorn  # Required for volumesnapshot support
  # dataSourceRef automatically added by Kyverno if backup exists

# After applying, verify Kyverno generated resources:
# kubectl get replicationsource,replicationdestination,externalsecret -n app-name
```

**When to use backup labels**:
- User-generated content (photos, documents, uploads)
- Non-CNPG database volumes (Redis, SQLite, etc.)
- Configuration that's hard to recreate
- AI model caches (large downloads)

**When NOT to use backup labels**:
- Temporary/cache data
- Data synced from external sources
- System namespaces (auto-excluded anyway)
- PVCs that will be frequently deleted/recreated
- **CNPG database PVCs** — these use Barman to S3, not Kyverno/VolSync (see below)

### Application with Database (CNPG CloudNativePG)

Databases use **CloudNativePG** with Barman backups to RustFS S3 — a **separate backup path** from the PVC/VolSync system. PVC backups use NFS + Kopia (shared repository with cross-PVC deduplication). Database backups use S3 + Barman (SQL-aware `pg_basebackup` + WAL archiving for point-in-time recovery). Each tool uses its native backup mechanism — see [backup-restore.md](docs/backup-restore.md#why-two-backup-systems-nfs-for-pvcs-s3-for-databases) for the full rationale.

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
      serverName: <app>-database      # IMPORTANT: bump on DR recovery (see DR docs)
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
- **No automatic restore** — recovery requires manual intervention (see [Database DR docs](docs/cnpg-disaster-recovery.md))
- **Cannot go through ArgoCD** for recovery — CNPG webhook + SSA = `initdb` always wins
- `serverName` must be bumped after each recovery (e.g. `-v2`, `-v3`) to avoid WAL archive conflicts

## Configuration Patterns

### Helm + Kustomize Pattern

Use Helm for base, Kustomize for customization:

```yaml
# kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: app-name

helmCharts:
- name: chart-name
  repo: https://charts.example.com
  version: 1.2.3
  releaseName: app-name
  valuesFile: values.yaml
  includeCRDs: true

resources:
- namespace.yaml
- externalsecret.yaml

# Custom values in values.yaml
```

### Component Reuse

Apply common settings across deployments:

```yaml
# kustomization.yaml
components:
- ../../common/deployment-defaults  # Applies revisionHistoryLimit: 2 to all Deployments
```

### Gateway API Routing

This cluster uses Gateway API (not Ingress):

```yaml
# Gateway defined once in infrastructure/networking/gateway/
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: gateway-external
spec:
  gatewayClassName: cilium
  listeners:
  - name: https
    port: 443
    protocol: HTTPS

# Applications reference the Gateway via HTTPRoute
apiVersion: gateway.networking.k8s.io/v1beta1
kind: HTTPRoute
metadata:
  name: app-route
spec:
  parentRefs:
  - kind: Gateway
    name: gateway-external
    namespace: gateway
```

## Secret Management Flow

```
1Password Vault (homelab-prod)
    ↓
1Password Connect API (infrastructure/controllers/1passwordconnect/)
    ↓
ClusterSecretStore (infrastructure/controllers/external-secrets/)
    ↓
ExternalSecret CRD (in application directory)
    ↓
Kubernetes Secret (auto-created and synced)
    ↓
Application Pod (mounts secret)
```

**Never commit secrets to Git**. Always use ExternalSecret resources pointing to 1Password.

## Storage Configuration

### Longhorn (Default StorageClass)

```yaml
# PVC example
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: app-data
  namespace: app-name
spec:
  accessModes:
  - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
  storageClassName: longhorn  # Default, can be omitted
```

### Alternative Storage Classes

- `longhorn` - Distributed block storage (default)
- `nfs-csi` - NFS mounts
- `smb-csi` - Windows shares
- `local-path` - Node-local fast storage
- `openebs-hostpath` - OpenEBS local storage

## Automated Backup & Restore with Kyverno

### The Magic Label Pattern

This cluster uses **Kyverno policies** to automatically configure backup and restore for PVCs. Just add a label:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: app-data
  namespace: app-name
  labels:
    backup: "hourly"  # or "daily"
spec:
  accessModes:
  - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
  storageClassName: longhorn
  # dataSourceRef automatically added by Kyverno if backup exists
```

**What happens automatically**:

1. **Kyverno generates ExternalSecret** - Pulls Kopia repository password from 1Password
2. **Kyverno generates ReplicationSource** - Backup schedule (hourly or daily at 2am)
3. **Kyverno generates ReplicationDestination** - Restore capability
4. **Kyverno injects NFS mount** - Mounts TrueNAS NFS share (`192.168.10.133:/mnt/BigTank/k8s/volsync-kopia-nfs`)
5. **PVC Plumber checks for backups** - On PVC creation, automatically adds `dataSourceRef` to restore from last backup

### Backup Schedules

| Label | Schedule | Retention |
|-------|----------|-----------|
| `backup: "hourly"` | Every hour (`0 * * * *`) | 24 hourly, 7 daily, 4 weekly, 2 monthly |
| `backup: "daily"` | Daily at 2am (`0 2 * * *`) | 24 hourly, 7 daily, 4 weekly, 2 monthly |

### How It Works

**Architecture**:
```
PVC with backup label
    ↓ (Kyverno watches)
ExternalSecret generated (Kopia password from 1Password)
    ↓
ReplicationSource generated (backup schedule)
    ↓ (triggers VolSync)
VolSync mover job (Kyverno injects NFS mount)
    ↓ (runs Kopia)
Backup to TrueNAS NFS share (filesystem:///repository)
```

**Restore Flow**:
```
New PVC created with backup label
    ↓ (Kyverno policy triggers)
PVC Plumber API call (checks if backup exists)
    ↓ (if backup found)
Kyverno adds dataSourceRef to PVC
    ↓ (points to)
ReplicationDestination (already generated)
    ↓ (VolSync restores)
PVC populated from last backup
```

### Backend Configuration

- **Storage Backend**: Kopia filesystem repository on NFS
- **NFS Server**: `192.168.10.133` (TrueNAS)
- **NFS Path**: `/mnt/BigTank/k8s/volsync-kopia-nfs`
- **Compression**: zstd-fastest
- **Snapshot Method**: Longhorn VolumeSnapshots (copy-on-write)
- **Mover Security**: Runs as user/group 568

### Kyverno Policies

**Location**: `infrastructure/controllers/kyverno/policies/`

1. **volsync-pvc-backup-restore.yaml** - Main backup/restore automation
   - **FAIL-CLOSED**: Validate rule denies PVC creation if PVC Plumber is unreachable
   - Adds `dataSourceRef` if backup exists (via PVC Plumber)
   - Generates ExternalSecret, ReplicationSource, ReplicationDestination
   - Excludes system namespaces (kube-system, volsync-system, kyverno)

2. **volsync-nfs-inject.yaml** - NFS mount injection
   - Automatically injects NFS volume into VolSync mover jobs
   - No manual NFS configuration needed per app

3. **volsync-orphan-cleanup.yaml** - Orphan resource cleanup (ClusterCleanupPolicy)
   - Runs every 15 minutes
   - Deletes orphaned ReplicationSource, ReplicationDestination, ExternalSecret when backup label is removed from PVC or PVC is deleted
   - Prevents stale backup/restore jobs from running after disabling backups

### PVC Plumber Service

**Purpose**: Checks Kopia repository for existing backups before PVC creation

**Endpoint**: `http://pvc-plumber.volsync-system.svc.cluster.local/exists/{namespace}/{pvc-name}`

**Response**:
```json
{
  "exists": true,
  "namespace": "app-name",
  "pvc": "app-data",
  "snapshots": 24
}
```

**Kyverno uses this to**:
- First validate PVC Plumber is healthy (`/readyz`) — if not, PVC creation is **denied** (fail-closed)
- Then call PVC Plumber API (`/exists`) during PVC CREATE operation
- If backup exists, add `dataSourceRef` to auto-restore
- Prevents data loss when recreating PVCs or during disaster recovery

### Manual Backup Operations

```bash
# Trigger all backups immediately (doesn't wait for schedule)
./scripts/trigger-immediate-backups.sh

# Check backup status
kubectl get replicationsource -A

# Check restore resources
kubectl get replicationdestination -A

# View VolSync mover job logs
kubectl logs -n <namespace> -l app.kubernetes.io/created-by=volsync

# Manually trigger restore (change trigger value)
kubectl patch replicationdestination app-data-restore -n app-name \
  --type merge -p '{"spec":{"trigger":{"manual":"restore-now"}}}'
```

### Adding Backup to Existing Apps

```yaml
# Just add the label to your PVC
metadata:
  labels:
    backup: "daily"

# Kyverno will generate:
# - ExternalSecret: volsync-app-data
# - ReplicationSource: app-data-backup
# - ReplicationDestination: app-data-restore

# Verify resources were created
kubectl get externalsecret,replicationsource,replicationdestination -n app-name
```

### Disaster Recovery

**Scenario**: Node failure, PVC deleted, need to restore

```yaml
# 1. Recreate PVC with same name and backup label
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: app-data
  namespace: app-name
  labels:
    backup: "daily"
spec:
  accessModes:
  - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
  # Kyverno will automatically add:
  # dataSourceRef:
  #   apiGroup: volsync.backube
  #   kind: ReplicationDestination
  #   name: app-data-restore

# 2. Apply the PVC
kubectl apply -f pvc.yaml

# 3. PVC Plumber checks for backup, Kyverno adds dataSourceRef
# 4. VolSync automatically restores from last backup
# 5. PVC is populated and ready to use
```

### Important Notes

**DO**:
- Add `backup: "hourly"` or `backup: "daily"` labels to critical PVCs
- Use `storageClassName: longhorn` (required for volumesnapshots)
- Keep PVC names consistent for restore to work
- Test restores periodically

**Removing backups**: Just remove the `backup` label from the PVC. The `volsync-orphan-cleanup` ClusterCleanupPolicy runs every 15 minutes and automatically deletes orphaned ReplicationSource, ReplicationDestination, and ExternalSecret resources when the PVC no longer has a backup label.

**DON'T**:
- Add backup labels to system namespace PVCs (auto-excluded)
- Change PVC name if you want automatic restore
- Delete ReplicationSource/ReplicationDestination manually (Kyverno will recreate them if label still present)
- Use backup labels on non-Longhorn PVCs (snapshot support required)

### Database Disaster Recovery (CNPG)

CNPG databases use Barman backups to S3 but **do NOT auto-restore**. After a cluster nuke:

**Recovery procedure** (must bypass ArgoCD — SSA + CNPG webhook makes `initdb` always win):

```bash
# 1. Edit cluster.yaml: comment out initdb, uncomment recovery section
# 2. Update externalClusters.serverName to match CURRENT backup.serverName
# 3. Bump backup.serverName to next version (e.g. -v2 → -v3)
# 4. Render and apply directly (bypass ArgoCD):
kubectl kustomize infrastructure/database/cloudnative-pg/immich/ \
  | awk '/^apiVersion: postgresql.cnpg.io\/v1/{p=1} p{print} /^---/{if(p) exit}' \
  > /tmp/recovery.yaml

# 5. Delete existing empty cluster and immediately create recovery version:
kubectl delete cluster immich-database -n cloudnative-pg --wait=false; \
  kubectl create -f /tmp/recovery.yaml

# 6. Wait for recovery:
kubectl get clusters -n cloudnative-pg -w

# 7. Verify data:
kubectl exec -n cloudnative-pg immich-database-1 -- \
  psql -U postgres -d immich -c "SELECT count(*) FROM \"user\";"

# 8. Revert cluster.yaml to initdb (keep new serverName in backup section)
# 9. Commit and push — ArgoCD syncs, CNPG ignores bootstrap on existing clusters
```

**Current serverName versions** (track these — must match for recovery):
| Database | Current backup serverName |
|----------|--------------------------|
| immich | `immich-database-v2` |
| khoj | `khoj-database` (original) |
| paperless | `paperless-database` (original) |

See [docs/cnpg-disaster-recovery.md](docs/cnpg-disaster-recovery.md) for full details.

## Debugging & Troubleshooting

### ArgoCD Issues

```bash
# Application stuck in sync
kubectl get application app-name -n argocd -o yaml

# Check ApplicationSet generation
kubectl describe applicationset infrastructure -n argocd

# View ArgoCD controller logs
kubectl logs -n argocd -l app.kubernetes.io/name=argocd-application-controller

# Force manual sync
kubectl patch application app-name -n argocd --type merge -p '{"operation":{"initiatedBy":{"username":"admin"},"sync":{"revision":"HEAD"}}}'
```

### Networking Issues

```bash
# Verify Cilium health
cilium status
kubectl get pods -n kube-system -l k8s-app=cilium

# Check Gateway API resources
kubectl get gateway -A
kubectl get httproute -A
kubectl describe httproute app-route -n app-name

# Test DNS resolution
kubectl run -it --rm debug --image=busybox --restart=Never -- nslookup app-service.app-name.svc.cluster.local
```

### Storage Issues

```bash
# Check PVC binding
kubectl get pvc -A
kubectl describe pvc app-data -n app-name

# Longhorn system status
kubectl get pods -n longhorn-system
kubectl get volumes -n longhorn-system
```

### Backup/Restore Issues (Kyverno + VolSync)

```bash
# Check if Kyverno generated backup resources
kubectl get replicationsource,replicationdestination -n app-name

# View Kyverno policy status
kubectl get clusterpolicy
kubectl describe clusterpolicy volsync-pvc-backup-restore

# Check if ExternalSecret was generated
kubectl get externalsecret -n app-name | grep volsync

# View VolSync backup job logs
kubectl get jobs -n app-name -l app.kubernetes.io/created-by=volsync
kubectl logs -n app-name job/volsync-src-<pvc-name> -c kopia

# Check PVC Plumber health
kubectl get pods -n volsync-system -l app.kubernetes.io/name=pvc-plumber
kubectl logs -n volsync-system -l app.kubernetes.io/name=pvc-plumber

# Test PVC Plumber API manually
kubectl run -it --rm curl --image=curlimages/curl --restart=Never -- \
  curl http://pvc-plumber.volsync-system.svc.cluster.local/exists/app-name/app-data

# Check if backup exists on NFS
kubectl exec -it -n volsync-system deploy/pvc-plumber -- ls -la /repository

# Force backup to run now (patch schedule)
kubectl patch replicationsource app-data-backup -n app-name \
  --type merge -p '{"spec":{"trigger":{"schedule":"*/5 * * * *"}}}'

# Check ReplicationSource status
kubectl get replicationsource app-data-backup -n app-name -o yaml | grep -A 10 status

# Verify Kyverno generated resources
kubectl get replicationsource,replicationdestination,externalsecret \
  -n app-name -l app.kubernetes.io/managed-by=kyverno
```

### Kyverno Policy Issues

```bash
# Check Kyverno admission controller status
kubectl get pods -n kyverno

# View Kyverno logs
kubectl logs -n kyverno -l app.kubernetes.io/component=admission-controller

# Check policy reports
kubectl get policyreport -A
kubectl describe policyreport -n app-name

# Verify policy is active
kubectl get clusterpolicy volsync-pvc-backup-restore -o yaml

# Test if NFS injection is working
kubectl get jobs -n app-name -l app.kubernetes.io/created-by=volsync -o yaml | grep -A 5 nfs
```

### Secret Sync Issues

```bash
# Check ExternalSecret status
kubectl get externalsecret -A
kubectl describe externalsecret app-secrets -n app-name

# Verify 1Password Connect is running
kubectl get pods -n 1passwordconnect
kubectl logs -n 1passwordconnect -l app.kubernetes.io/name=connect

# Check ClusterSecretStore
kubectl get clustersecretstore
kubectl describe clustersecretstore 1password
```

### GPU Issues

```bash
# Verify GPU nodes are labeled
kubectl get nodes -o json | jq '.items[].metadata.labels' | grep gpu

# Check NVIDIA GPU Operator
kubectl get pods -n gpu-operator

# Test GPU from pod
kubectl exec -it gpu-pod -n app-name -- nvidia-smi
```

## Critical Rules

### DO:
- Use directory structure for application discovery (no manual Application resources)
- Name Service ports for HTTPRoute compatibility (`name: http`)
- Use Gateway API (not Ingress Controllers)
- Follow GitOps workflow for all changes
- Store secrets in 1Password, reference via ExternalSecret
- Add `backup: "hourly"` or `backup: "daily"` labels to critical PVCs
- Use `storageClassName: longhorn` for PVCs that need backups (volumesnapshot support required)
- Test changes in personal fork before main branch
- Use sync waves when adding infrastructure components
- Apply common components for shared config
- Verify Kyverno generated backup resources after creating PVCs with backup labels

### DON'T:
- Create manual ArgoCD `Application` resources (use directory discovery)
- Use `kubectl edit` on Talos nodes (changes are ephemeral)
- Create Services without named ports when using HTTPRoute
- Mix Ingress and Gateway API (this cluster uses Gateway API only)
- Commit secrets to Git
- Bypass GitOps workflow for configuration changes
- Deploy without considering sync wave order
- Assume Ingress patterns work (use HTTPRoute instead)
- Add backup labels to PVCs in system namespaces (kube-system, volsync-system, kyverno)
- Manually create ReplicationSource/ReplicationDestination (Kyverno auto-generates)
- Delete backup resources managed by Kyverno (they'll be recreated)

## Reference Examples

| Pattern | Reference Location |
|---------|-------------------|
| **Minimal app** | `my-apps/development/nginx/` |
| **GPU workload** | `my-apps/ai/comfyui/` |
| **Complex app with storage** | `my-apps/media/immich/` |
| **PVC with automatic backup** | `my-apps/ai/khoj/pvc.yaml` (see backup label) |
| **Kyverno backup policies** | `infrastructure/controllers/kyverno/policies/volsync-pvc-backup-restore.yaml` |
| **Kyverno orphan cleanup** | `infrastructure/controllers/kyverno/policies/volsync-orphan-cleanup.yaml` |
| **PVC Plumber (restore checker)** | `infrastructure/controllers/pvc-plumber/` |
| **Full backup/restore flow diagram** | `docs/pvc-plumber-full-flow.md` |
| **VolSync configuration** | `infrastructure/storage/volsync/` |
| **Helm + Kustomize** | `infrastructure/controllers/1passwordconnect/` |
| **Database with CNPG** | `infrastructure/database/cloudnative-pg/immich/` |
| **CNPG disaster recovery** | `docs/cnpg-disaster-recovery.md` |
| **Gateway API routing** | `infrastructure/networking/gateway/` |
| **Custom monitoring** | `monitoring/prometheus-stack/custom-alerts.yaml` |
| **Secret management** | Any app with `externalsecret.yaml` |

## Additional Documentation

- **[README.md](README.md)** - Bootstrap guide, architecture overview, and Omni/Proxmox setup
- **[.github/copilot-instructions.md](.github/copilot-instructions.md)** - Detailed development patterns
- **[.github/instructions/](.github/instructions/)** - Domain-specific instructions (ArgoCD, GPU, Talos, standards)
- **[docs/pvc-plumber-full-flow.md](docs/pvc-plumber-full-flow.md)** - Complete PVC backup/restore flow from bare metal to automatic disaster recovery
- **[docs/backup-restore.md](docs/backup-restore.md)** - Detailed backup/restore workflow with architecture diagrams
- **[docs/network-topology.md](docs/network-topology.md)** - Network architecture details
- **[docs/network-policy.md](docs/network-policy.md)** - Cilium network policies
- **[docs/argocd.md](docs/argocd.md)** - ArgoCD-specific documentation
- **[docs/cnpg-disaster-recovery.md](docs/cnpg-disaster-recovery.md)** - CNPG database backup/restore and disaster recovery procedures
