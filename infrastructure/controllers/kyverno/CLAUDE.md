# Kyverno Backup & Restore System

> **Required reading before modifying backup policies or troubleshooting backup issues:**
> - `docs/backup-restore.md` — Full architecture, why Kopia+NFS (not S3), cross-PVC deduplication
> - `docs/pvc-plumber-full-flow.md` — Complete flow from bare metal bootstrap to automatic DR

## The Magic Label Pattern

Add a label to a PVC and Kyverno automatically configures backup and restore:

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

## Backup Schedules

| Label | Schedule | Retention |
|-------|----------|-----------|
| `backup: "hourly"` | Hourly at `<minute> * * * *` (length-spread) | 24 hourly, 7 daily, 4 weekly, 2 monthly |
| `backup: "daily"` | Daily at `<minute> 2 * * *` (length-spread) | 24 hourly, 7 daily, 4 weekly, 2 monthly |

The `<minute>` field is `length(namespace-name) modulo 60` — a **temporary
deterministic spread**, not a real hash. PVC names share length ranges so this
clusters; it's still better than every PVC firing at `:00`. Replace with a
sha256-derived minute (or move scheduling into a future controller) when
inventory grows past ~50 backup-labeled PVCs. Existing ReplicationSources keep
whatever minute Kyverno generated at admission time (`synchronize: false`); the
new minute only takes effect when a PVC is recreated.

## How It Works

**Backup Architecture**:
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

## Backend Configuration

- **Storage Backend**: Kopia filesystem repository on NFS
- **NFS Server**: `192.168.10.133` (TrueNAS)
- **NFS Path**: `/mnt/BigTank/k8s/volsync-kopia-nfs`
- **Compression**: zstd-fastest
- **Snapshot Method**: Longhorn VolumeSnapshots (copy-on-write)
- **Mover Security**: Runs as user/group 568

## Kyverno Policies

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
   - Deletes orphaned ReplicationSource, ReplicationDestination, ExternalSecret when backup label is removed or PVC deleted
   - Prevents stale backup/restore jobs

## PVC Plumber Service

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

## Manual Backup Operations

```bash
# Trigger all backups immediately
./scripts/trigger-immediate-backups.sh

# Check backup status
kubectl get replicationsource -A

# Check restore resources
kubectl get replicationdestination -A

# View VolSync mover job logs
kubectl logs -n <namespace> -l app.kubernetes.io/created-by=volsync

# Manually trigger restore
kubectl patch replicationdestination app-data-restore -n app-name \
  --type merge -p '{"spec":{"trigger":{"manual":"restore-now"}}}'
```

## Adding Backup to Existing Apps

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

## PVC Disaster Recovery

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

# 2. Apply → PVC Plumber checks → Kyverno adds dataSourceRef → VolSync restores
```

## Important Notes

**DO**:
- Add `backup: "hourly"` or `backup: "daily"` labels to critical PVCs
- Use `storageClassName: longhorn` (required for volumesnapshots)
- Keep PVC names consistent for restore to work
- Test restores periodically

**Removing backups**: Remove the `backup` label. The `volsync-orphan-cleanup` ClusterCleanupPolicy runs every 15 minutes and automatically deletes orphaned resources.

**DON'T**:
- Add backup labels to system namespace PVCs (auto-excluded)
- Change PVC name if you want automatic restore
- Delete ReplicationSource/ReplicationDestination manually (Kyverno will recreate if label present)
- Use backup labels on non-Longhorn PVCs (snapshot support required)
- Add backup labels to CNPG database PVCs (they use Barman to S3, not Kyverno/VolSync)

## Critical: Kyverno Policy Performance Rules

**All generate policies MUST use `background: false`**. Background scanning causes Kyverno to re-evaluate every matching resource on a ~30s loop, generating UpdateRequests that hammer the API server. With 70+ workloads, this creates 800+ API calls per cycle and cascading crash loops across the entire cluster.

**Never use `mutateExistingOnPolicyUpdate: true` on generate policies**. This re-evaluates ALL matching resources cluster-wide whenever the policy YAML changes — even a comment edit triggers it. Combined with background scanning, this caused a 23-hour API server overload incident (2026-03-25).

**The safe pattern for all Kyverno generate policies (canonical form):**
```yaml
spec:
  mutateExistingOnPolicyUpdate: false  # REQUIRED — prevents cluster-wide re-evaluation on policy change
  background: false                     # REQUIRED — prevents continuous background scanning
  emitWarning: false                    # Kyverno default — include to match canonical form for ArgoCD sync
  validationFailureAction: Audit        # OK for pure generate-only policies; use Enforce for admission safety gates
  rules:
    - name: my-generate-rule
      skipBackgroundRequests: true       # Kyverno default — include to match canonical form for ArgoCD sync
      generate:
        synchronize: false              # REQUIRED — prevents drift watchers that generate UpdateRequests on every controller status update
```

**Why `synchronize: false`**: With `synchronize: true`, Kyverno watches every generated resource (ExternalSecrets, ReplicationSources, etc.) and creates UpdateRequests whenever their controllers update status. With ~114 watched resources, this generates hundreds of thousands of API calls. Resources are still created on admission (PVC creation via ArgoCD sync) — they just aren't re-synced on drift.

**Why canonical form**: Kyverno's admission webhook adds `emitWarning`, `validationFailureAction`, and `skipBackgroundRequests` as defaults. If these aren't in git, ArgoCD detects the diff and shows OutOfSync. Writing the defaults explicitly keeps ArgoCD happy.

**Exception: PVC backup/restore admission policy.** `volsync-pvc-backup-restore` must use Enforce semantics because it protects against silent empty PVC initialization during rebuilds. For backup-labeled PVC CREATE operations, unknown pvc-plumber/Kopia truth should block admission and let ArgoCD retry.

**If you need to re-process existing resources after a policy change**, do a one-time ArgoCD sync or manually trigger resource re-admission — don't enable `mutateExistingOnPolicyUpdate`.

## Critical: Webhook Deadlock Prevention

**Incident: 2026-04-08 — Full cluster outage caused by Kyverno webhook deadlock.**

### What happened

1. Renovate auto-merged a kube-prometheus-stack v82→v83 Helm chart upgrade
2. ArgoCD synced it, restarting many Prometheus pods simultaneously
3. The restart flood overwhelmed Kyverno's admission controller — its internal cache sync failed
4. Kyverno crashed with `"failed to wait for cache sync"` on v1beta1 informers
5. Kyverno's webhook was still registered with `failurePolicy: Fail`
6. **Every Deployment/StatefulSet/DaemonSet creation outside kube-system was rejected**
7. Longhorn (longhorn-system) couldn't restart → no storage → ArgoCD couldn't mount PVCs → ArgoCD died
8. Full cluster deadlock — even rebooting all nodes didn't fix it because webhook configs survive in etcd
9. Only manual deletion of webhook configurations broke the deadlock

### The fix

Infrastructure namespaces are excluded from Kyverno's webhook `namespaceSelector` in `values.yaml`:

```yaml
config:
  webhooks:
    namespaceSelector:
      matchExpressions:
      - key: kubernetes.io/metadata.name
        operator: NotIn
        values:
          - kube-system
          - longhorn-system        # Wave 1 storage
          - argocd                 # Wave 0 GitOps
          - volsync-system         # Wave 1 backup controller
          - snapshot-controller    # Wave 1 snapshots
          - cert-manager           # Wave 4 but critical
          - external-secrets       # Wave 0 secrets
          - 1passwordconnect       # Wave 0 secrets
```

**Why this works:** The fail-closed PVC gate only needs to protect app namespaces (Waves 4-6). Infrastructure namespaces (Waves 0-2) must boot before Kyverno (Wave 3), so they should never be gated by Kyverno's webhook.

### Emergency recovery

If Kyverno causes a webhook deadlock again:

```bash
./scripts/emergency-webhook-cleanup.sh
```

This deletes all Kyverno webhook configurations. Kyverno recreates them once it's healthy. The script is safe to run — it only removes webhook registrations, not policies or generated resources.

### Prevention rules

- **Never remove infrastructure namespaces from the webhook exclusion list**
- **Pin Renovate to minor/patch for critical charts** (kube-prometheus-stack, longhorn, kyverno, cilium) — major version bumps should be manually reviewed
- **Monitor Kyverno admission controller restarts** — more than 2 restarts in 10 minutes indicates a potential deadlock forming
- **If Kyverno shows `"failed to wait for cache sync"` in logs** — run the emergency cleanup script immediately, don't wait

## Debugging Backup/Restore

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

# Force backup to run now
kubectl patch replicationsource app-data-backup -n app-name \
  --type merge -p '{"spec":{"trigger":{"schedule":"*/5 * * * *"}}}'

# Check ReplicationSource status
kubectl get replicationsource app-data-backup -n app-name -o yaml | grep -A 10 status

# Verify Kyverno generated resources
kubectl get replicationsource,replicationdestination,externalsecret \
  -n app-name -l app.kubernetes.io/managed-by=kyverno
```

## Debugging Kyverno

```bash
kubectl get pods -n kyverno
kubectl logs -n kyverno -l app.kubernetes.io/component=admission-controller
kubectl get policyreport -A
kubectl describe policyreport -n app-name
kubectl get clusterpolicy volsync-pvc-backup-restore -o yaml

# Test if NFS injection is working
kubectl get jobs -n app-name -l app.kubernetes.io/created-by=volsync -o yaml | grep -A 5 nfs
```
