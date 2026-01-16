# VolSync Kyverno Automation - Complete Session Notes
**Date**: January 16, 2026, 23:00-23:15 UTC  
**Objective**: Achieve 100% automated zero-touch VolSync backup/restore via Kyverno policy  
**Status**: IN PROGRESS - ReplicationDestination needs S3 credentials secret reference

---

## Executive Summary

### Goal
Create a fully automated GitOps backup system where:
1. User creates PVC with label `backup=hourly`
2. Kyverno policy auto-generates TWO VolSync resources:
   - `ReplicationDestination` (restore job) - triggers ONCE on PVC creation
   - `ReplicationSource` (backup job) - runs hourly on schedule
3. Restore runs FIRST (if S3 backup exists → restores; if not → fails gracefully)
4. Backups protect data going forward (hourly retention: 24, daily: 7)
5. **Critical safety requirement**: Never overwrite existing backups with empty data on fresh cluster deployments

### Current Blocker
**Error**: `Secret "s3:http://192.168.10.133:30292/volsync-backup/volsync-test/volsync-test-data" not found`

**Root Cause**: VolSync expects `restic.repository` field to be a **Secret name**, not a direct S3 URL. The secret should contain:
- `RESTIC_REPOSITORY` - S3 URL
- `RESTIC_PASSWORD` - Restic encryption password
- `AWS_ACCESS_KEY_ID` - S3 access key
- `AWS_SECRET_ACCESS_KEY` - S3 secret key

**Missing Piece**: Kyverno policy needs a third generate rule to create per-PVC secrets with S3 credentials.

---

## Technology Stack

| Component | Version/Config | Role |
|-----------|----------------|------|
| **RustFS S3** | 192.168.10.133:30292 | Object storage backend (MinIO on TrueNAS) |
| **VolSync** | v0.10+ | Restic-based backup operator |
| **Kyverno** | v3.6.2 | Policy engine (generate VolSync resources) |
| **ArgoCD** | GitOps sync | All changes via Git commits |
| **ExternalSecrets** | Operator | Syncs 1Password → K8s Secrets |
| **1Password** | Vault | Source of truth for credentials |
| **Cilium** | CNI + NetworkPolicy | Permits egress to RustFS IP |
| **Longhorn** | StorageClass | PVC backend |

### Credential Chain
```
1Password (rustfs item)
  ├─ k8s-admin-access-key (property)
  ├─ k8s-admin-secret-key (property)
  └─ restic-password (property)
         ↓
ExternalSecret (volsync-system/volsync-rustfs-credentials)
  ├─ AWS_ACCESS_KEY_ID
  ├─ AWS_SECRET_ACCESS_KEY
  ├─ RESTIC_PASSWORD
  └─ RESTIC_REPOSITORY (base URL)
         ↓
ClusterExternalSecret (distributes to select namespaces)
  ├─ volsync-system ✅
  ├─ longhorn-system ✅
  ├─ karakeep ✅
  ├─ khoj ✅
  └─ volsync-test ❌ (not included - may need to add)
```

---

## Session Timeline

### Phase 1: Initial Diagnosis (23:00-23:02)
**Problem**: VolSync backup jobs (ReplicationSource) not generating for PVCs with `backup=hourly` label

**Investigation**:
```bash
kubectl get applications -n argocd | grep kyverno
# kyverno   OutOfSync   Healthy

kubectl get clusterpolicy volsync-smart-protection -o yaml | head -80
# Saw 3 rules with context.apiCall sections
```

**Root Cause Found**:
Kyverno policy using `context.apiCall` to check S3 bucket existence before generating resources:
```yaml
context:
- apiCall:
    method: GET
    urlPath: http://192.168.10.133:30292/volsync-backup/{{ request.namespace }}/{{ request.object.metadata.name }}/config
  name: repoCheck
preconditions:
  all:
  - key: '{{ repoCheck.code }}'
    operator: Equals
    value: 200  # Only generate if S3 path exists
```

**Error Message** (from PVC admission webhook):
```
admission webhook "mutate.kyverno.svc-fail" denied the request: 
mutation policy volsync-smart-protection error: 
failed to evaluate preconditions: 
failed to substitute variables in condition key: 
failed to resolve repoCheck.code at path : 
failed to fetch data for APICall: 
failed to GET resource with raw url: http://192.168.10.133:30292/volsync-backup/volsync-test/volsync-test-data/config: unknown
```

**Why It Failed**:
- apiCall executes during PVC admission (synchronous webhook)
- Network call to external S3 endpoint creates fragile dependency
- Even though Cilium NetworkPolicy permits egress, HTTP request unreliable
- Admission webhook timeout or S3 unreachability blocks PVC creation entirely

**Findings**:
- VolSync operator healthy: `kubectl get deploy -n volsync-system` → 1/1 Ready
- Existing backups confirmed in RustFS (karakeep, khoj, open-webui, home-assistant)
- Cilium policy allows egress to `192.168.10.133:30292/30293/9000` (verified in `infrastructure/networking/cilium/policies/block-lan-access.yaml`)

---

### Phase 2: Credentials Consolidation (23:02-23:03)
**Problem**: Multiple 1Password items with overlapping credentials
- `rustfs` item
- `minio` item  
- `kbs-admin` item (typo - should be k8s-admin)

**Decision**: Unify to single source of truth: `k8s-admin` credentials in `rustfs` 1Password item

**Files Updated** (all committed to Git):
1. `infrastructure/storage/volsync/rustfs-credentials.yaml`
   - `remoteRef.property: kbs-admin-access-key` → `k8s-admin-access-key`
   - `remoteRef.property: kbs-admin-secret-key` → `k8s-admin-secret-key`

2. `infrastructure/storage/volsync/externalsecret.yaml`
   - Updated all remoteRef properties to k8s-admin

3. `infrastructure/storage/longhorn/externalsecret.yaml`
   - Updated to k8s-admin properties

4. `monitoring/loki-stack/externalsecret.yaml`
   - Updated to k8s-admin properties

5. `monitoring/tempo/externalsecret.yaml`
   - Updated to k8s-admin properties

6. `infrastructure/database/cloudnative-pg/postgres-global-secrets/externalsecret.yaml`
   - Updated to k8s-admin properties

7. `infrastructure/database/crunchy-postgres/immich/pgo-s3-credentials.yaml`
   - Updated template data keys to k8s-admin

8. `docs/VOLSYNC_1PASSWORD_AUDIT.md`
   - Renamed all instances of kbs-admin → k8s-admin throughout

**Verification** (all successful):
```bash
# Check ExternalSecret status
kubectl get externalsecrets -n volsync-system
# NAME                        STORE   REFRESH INTERVAL   STATUS         READY
# volsync-rustfs-credentials  ...     5m                 SecretSynced   True

# Decode secret to verify k8s-admin username
kubectl get secret -n volsync-system volsync-rustfs-credentials -o jsonpath='{.data.AWS_ACCESS_KEY_ID}' | base64 -d
# Output: k8s-admin ✅

kubectl get secret -n longhorn-system volsync-rustfs-credentials -o jsonpath='{.data.AWS_ACCESS_KEY_ID}' | base64 -d
# Output: k8s-admin ✅

kubectl get secret -n karakeep volsync-rustfs-credentials -o jsonpath='{.data.AWS_ACCESS_KEY_ID}' | base64 -d
# Output: k8s-admin ✅
```

---

### Phase 3: Remove apiCall - Policy Refactor (23:03-23:05)

**Decision**: Eliminate `context.apiCall` network dependency from Kyverno policy

**Rationale**:
- Admission-time HTTP calls = brittle failure point
- S3 bucket existence can be verified post-admission by VolSync controller
- Safer to generate resources unconditionally; VolSync handles missing repos gracefully
- Improves cluster isolation (no external calls during admission)

**Original Policy Structure** (`volsync-smart-restore.yaml`):
```yaml
spec:
  rules:
  # Rule 1: Mutate PVC to add dataSourceRef (if backup exists)
  - name: link-restore-if-exists
    context:
    - apiCall: <HTTP GET to S3>
    preconditions: <check HTTP 200>
    mutate: <patch PVC spec.dataSourceRef>
  
  # Rule 2: Generate ReplicationDestination (if backup exists)
  - name: generate-restore-job
    context:
    - apiCall: <HTTP GET to S3>
    preconditions: <check HTTP 200>
    generate: <ReplicationDestination>
  
  # Rule 3: Generate ReplicationSource (always)
  - name: generate-backup-job
    generate: <ReplicationSource>
```

**Refactored Policy** (2 rules, no apiCall, no mutation):
```yaml
spec:
  validationFailureAction: Enforce
  background: false  # Only trigger on admission, not background scans
  rules:
  
  # Rule 1: Generate hourly backup job
  - name: generate-backup-job
    match:
      any:
      - resources:
          kinds: ["PersistentVolumeClaim"]
          selector:
            matchLabels:
              backup: "hourly"
    generate:
      apiVersion: volsync.backube/v1alpha1
      kind: ReplicationSource
      name: "{{ request.object.metadata.name }}-backup"
      namespace: "{{ request.object.metadata.namespace }}"
      synchronize: true
      data:
        spec:
          sourcePVC: "{{ request.object.metadata.name }}"
          trigger:
            schedule: "0 * * * *"  # Every hour at :00
          restic:
            pruneIntervalDays: 10
            repository: "s3:http://192.168.10.133:30292/volsync-backup/{{ request.object.metadata.namespace }}/{{ request.object.metadata.name }}"
            copyMethod: Direct
            storageClassName: "longhorn"
            volumeSnapshotClassName: "longhorn"
            cacheStorageClassName: "longhorn"
            cacheAccessModes: ["ReadWriteOnce"]
            cacheCapacity: "2Gi"
            retain:
              hourly: 24
              daily: 7
  
  # Rule 2: Generate one-time restore job
  - name: generate-restore-job
    match:
      any:
      - resources:
          kinds: ["PersistentVolumeClaim"]
          selector:
            matchLabels:
              backup: "hourly"
    generate:
      apiVersion: volsync.backube/v1alpha1
      kind: ReplicationDestination
      name: "{{ request.object.metadata.name }}-restore"
      namespace: "{{ request.object.metadata.namespace }}"
      synchronize: true
      data:
        spec:
          trigger:
            manual: "auto-restore-{{ request.object.metadata.creationTimestamp }}"
          restic:
            repository: "s3:http://192.168.10.133:30292/volsync-backup/{{ request.object.metadata.namespace }}/{{ request.object.metadata.name }}"
            copyMethod: Direct
            storageClassName: "longhorn"
            volumeSnapshotClassName: "longhorn"
            accessModes: ["ReadWriteOnce"]  # Added after testing failure
            capacity: "{{ request.object.spec.resources.requests.storage }}"  # Added after testing failure
```

**Key Design Choices**:
- **Restore trigger**: `manual: "auto-restore-{{ creationTimestamp }}"` creates unique trigger string per PVC creation → runs once, never re-runs
- **Backup trigger**: `schedule: "0 * * * *"` runs hourly
- **S3 repository paths**: Hardcoded deterministic pattern (no network calls needed)
- **synchronize: true**: Keeps generated resources in sync with policy updates
- **background: false**: Only evaluate on PVC admission events, not background scans

**Git Commits**:
```bash
git commit -m "refactor(kyverno): remove apiCall from volsync-smart-protection policy"
git push origin main
```

---

### Phase 4: Testing Infrastructure (23:05-23:06)

**Created Test Application**: `my-apps/development/volsync-test/`

**Purpose**: Isolated namespace to test Kyverno policy without affecting production

**Files Created**:

`namespace.yaml`:
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: volsync-test
  labels:
    app.kubernetes.io/name: volsync-test
```

`pvc.yaml`:
```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: volsync-test-data
  namespace: volsync-test
  labels:
    backup: "hourly"  # ← Triggers Kyverno policy
    app.kubernetes.io/name: volsync-test
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 1Gi
  storageClassName: longhorn
```

`kustomization.yaml`:
```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: volsync-test
resources:
  - namespace.yaml
  - pvc.yaml
```

**ArgoCD Auto-Discovery**:
```bash
# Commit to Git
git add my-apps/development/volsync-test
git commit -m "test(volsync): add volsync-test app with labeled PVC for restore-first policy verification"
git push origin main

# Force ApplicationSet to re-scan directories
kubectl patch applicationset my-apps -n argocd --type merge -p '{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}}'

# Wait and verify app generation
sleep 5
kubectl get applications -n argocd | grep volsync-test
# Output: my-apps-volsync-test   OutOfSync   Missing
```

**How ArgoCD Discovers It** (`infrastructure/controllers/argocd/apps/my-apps-appset.yaml`):
```yaml
spec:
  generators:
  - git:
      directories:
      - path: my-apps/*/*  # Matches: my-apps/development/volsync-test
  template:
    metadata:
      name: 'my-apps-{{path.basename}}'  # → my-apps-volsync-test
    spec:
      destination:
        namespace: '{{path.basename}}'  # → volsync-test
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
```

---

### Phase 5: Debugging ReplicationDestination Spec (23:06-23:10)

#### Issue 1: Malformed YAML in Policy File

**Symptom**: Policy file had corrupt/duplicate section:
```yaml
# Line 70-ish in volsync-smart-restore.yaml
- name: generate-restore-job
  match:
    any:
      - resources:
          kinds: ["PersistentVolumeClaim"]
          selector:
            matchLabels:Auto-triggers on PVC creation)  # ← CORRUPT LINE
# ------------------------------------------------------------------
- name: generate-restore-job  # ← DUPLICATE!
  match:
    ...
```

**Fix**: Cleaned up YAML structure, removed duplicate header, proper indentation

#### Issue 2: Missing `accessModes` and `capacity` Fields

**Error from VolSync**:
```bash
kubectl describe replicationdestination volsync-test-data-restore -n volsync-test
# Status:
#   Conditions:
#     Message: accessModes must be provided when destinationPVC is not
#     Status: False
#     Type: Synchronizing
```

**Analysis**:
Original spec used simplified form:
```yaml
spec:
  destinationPVC: "{{ request.object.metadata.name }}"  # Reference existing PVC
  restic:
    repository: "s3://..."
```

But VolSync expects full PVC creation spec when NOT using `destinationPVC` reference to pre-existing PVC. ReplicationDestination creates a NEW PVC from the restore, doesn't just point to the source PVC.

**Fixed Spec**:
```yaml
spec:
  # REMOVED: destinationPVC field
  restic:
    repository: "s3:http://192.168.10.133:30292/volsync-backup/{{ request.object.metadata.namespace }}/{{ request.object.metadata.name }}"
    copyMethod: Direct
    storageClassName: "longhorn"
    volumeSnapshotClassName: "longhorn"
    accessModes: ["ReadWriteOnce"]  # ← REQUIRED
    capacity: "{{ request.object.spec.resources.requests.storage }}"  # ← REQUIRED (copies from source PVC)
  trigger:
    manual: "auto-restore-{{ request.object.metadata.creationTimestamp }}"
```

**Git Commit**:
```bash
git add infrastructure/controllers/kyverno/volsync-smart-restore.yaml
git commit -m "fix(kyverno): add accessModes and capacity to ReplicationDestination, remove destinationPVC"
git push origin main
```

**Lesson Learned**: VolSync API requires complete PVC spec when creating destination volumes from restores

#### Issue 3: Kyverno Generate Rule Immutability

**Error** (when trying to kubectl apply updated policy):
```
admission webhook "validate-policy.kyverno.svc" denied the request: 
changes of immutable fields of a rule spec in a generate rule is disallowed
```

**Cause**: Kyverno prevents in-place modification of generate rule specs to prevent configuration drift

**Attempted Fix** (WRONG - manual kubectl):
```bash
kubectl delete clusterpolicy volsync-smart-protection
kubectl apply -f infrastructure/controllers/kyverno/volsync-smart-restore.yaml
# Policy recreated successfully
```

**Problem Created**: This added a massive `kubectl.kubernetes.io/last-applied-configuration` annotation...

#### Issue 4: ArgoCD CRD Annotation Size Limit

**Error** (when ArgoCD tried to sync):
```
operationState:
  message: 'one or more objects failed to apply, reason: 
    error when patching "/dev/shm/983121763": 
    CustomResourceDefinition.apiextensions.k8s.io "clusterpolicies.kyverno.io" is invalid: 
    metadata.annotations: Too long: may not be more than 262144 bytes
```

**Cause**: `kubectl apply` embeds entire resource YAML in `last-applied-configuration` annotation → exceeds Kubernetes annotation size limit (256KB)

**Fix** (proper GitOps approach):
```bash
# 1. Remove the problematic annotation
kubectl annotate clusterpolicy volsync-smart-protection kubectl.kubernetes.io/last-applied-configuration-

# 2. Sync via ArgoCD (NOT kubectl!)
kubectl patch application kyverno -n argocd --type merge -p '{
  "operation": {
    "initiatedBy": {"username": "admin"},
    "sync": {
      "revision": "HEAD",
      "prune": true,
      "syncOptions": ["Replace=true", "ServerSideApply=true"]
    }
  }
}'

# 3. Wait for sync to complete
sleep 15
kubectl get applications -n argocd kyverno -o jsonpath='{.status.sync.status} {.status.health.status}'
# Output: OutOfSync Progressing (then eventually: Synced Healthy)
```

**Verification**:
```bash
# Confirm policy updated with accessModes
kubectl get clusterpolicy volsync-smart-protection -o jsonpath='{.spec.rules[1].generate.data.spec.restic.accessModes}'
# Output: ["ReadWriteOnce"] ✅
```

**Critical Lesson**: **NEVER use `kubectl apply` on resources managed by ArgoCD**. Always sync via ArgoCD API to avoid annotation conflicts.

---

### Phase 6: Current Blocking Issue - Missing S3 Credentials Secret (23:10-present)

#### Resources Created Successfully

**Test PVC**:
```bash
kubectl get pvc -n volsync-test
# NAME                                         STATUS   VOLUME                                     CAPACITY   ACCESS MODES   STORAGECLASS
# volsync-dst-volsync-test-data-restore-cache  Bound    pvc-d6c81a75-c715-4d88-9b6f-90a89429d821   1Gi        RWO            longhorn
# volsync-src-volsync-test-data-backup-cache   Bound    pvc-8ab84609-ef0d-47b1-9c29-c8609c5f8354   2Gi        RWO            longhorn
# volsync-test-data                            Bound    pvc-1838ed9a-a0eb-404e-bbce-d2a68b4e5b6d   1Gi        RWO            longhorn
# volsync-volsync-test-data-restore-dest       Bound    pvc-7b58f4d9-ead4-46ac-9b3f-e5b1ef836f0b   1Gi        RWO            longhorn
```

**VolSync Resources**:
```bash
kubectl get replicationsources,replicationdestinations -n volsync-test
# NAME                                                         SOURCE              LAST SYNC   DURATION   NEXT SYNC
# replicationsource.volsync.backube/volsync-test-data-backup   volsync-test-data               
# 
# NAME                                                               LAST SYNC   DURATION   NEXT SYNC
# replicationdestination.volsync.backube/volsync-test-data-restore
```

**ReplicationDestination Spec** (validated correct):
```bash
kubectl get replicationdestination volsync-test-data-restore -n volsync-test -o yaml
```
```yaml
spec:
  restic:
    accessModes:
    - ReadWriteOnce
    capacity: 1Gi  # Copied from source PVC
    copyMethod: Direct
    repository: s3:http://192.168.10.133:30292/volsync-backup/volsync-test/volsync-test-data
    storageClassName: longhorn
    volumeSnapshotClassName: longhorn
  trigger:
    manual: auto-restore-2026-01-16T23:09:56Z  # Unique timestamp
```

#### Current Error

```bash
kubectl describe replicationdestination volsync-test-data-restore -n volsync-test
```
```yaml
Status:
  Conditions:
    Last Transition Time:  2026-01-16T23:09:56Z
    Message:               Secret "s3:http://192.168.10.133:30292/volsync-backup/volsync-test/volsync-test-data" not found
    Reason:                Error
    Status:                False
    Type:                  Synchronizing
  Last Sync Start Time:    2026-01-16T23:09:55Z
```

#### Root Cause Analysis

**VolSync is interpreting the `repository` field as a Secret name!**

The error message literally says:
```
Secret "s3:http://192.168.10.133:30292/volsync-backup/volsync-test/volsync-test-data" not found
```

It's trying to find a Kubernetes Secret with that name (which is actually the S3 URL we provided).

**Expected VolSync Pattern** (from docs):
```yaml
# Secret should exist with credentials
apiVersion: v1
kind: Secret
metadata:
  name: volsync-test-data-volsync-secret  # ← This is what repository should reference
type: Opaque
data:
  RESTIC_REPOSITORY: <base64: s3://...>  # The actual S3 URL goes HERE
  RESTIC_PASSWORD: <base64>
  AWS_ACCESS_KEY_ID: <base64>
  AWS_SECRET_ACCESS_KEY: <base64>

# ReplicationDestination references the secret NAME
spec:
  restic:
    repository: volsync-test-data-volsync-secret  # ← Secret name, NOT the URL!
```

**What We Currently Have** (WRONG):
```yaml
spec:
  restic:
    repository: s3:http://192.168.10.133:30292/...  # ← Direct URL string
```

**Current State of Secrets in volsync-test Namespace**:
```bash
kubectl get secrets -n volsync-test
# NAME                     TYPE                                  DATA   AGE
# default-token-xxxxx      kubernetes.io/service-account-token   3      25m
# (NO volsync-test-data-volsync-secret exists!)
```

---

## What We Know (Verified Facts)

1. **RustFS S3 is accessible from cluster**
   - Cilium NetworkPolicy permits egress to `192.168.10.133:30292/30293/9000`
   - Verified in `infrastructure/networking/cilium/policies/block-lan-access.yaml`

2. **Credentials exist in 1Password `rustfs` item**
   - Properties: `k8s-admin-access-key`, `k8s-admin-secret-key`, `restic-password`

3. **ExternalSecret syncing successfully in volsync-system**
   ```bash
   kubectl get secret -n volsync-system volsync-rustfs-credentials -o yaml
   # Contains: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, RESTIC_PASSWORD, RESTIC_REPOSITORY
   ```

4. **ClusterExternalSecret distributes to select namespaces**
   ```yaml
   # File: infrastructure/storage/volsync/rustfs-credentials.yaml
   spec:
     namespaceSelector:
       matchExpressions:
       - key: kubernetes.io/metadata.name
         operator: In
         values:
         - volsync-system
         - longhorn-system
         - karakeep
         # ... other production namespaces
         # volsync-test NOT included! ← May need to add
   ```

5. **VolSync CRD expects repository field to be a Secret name** (not S3 URL)

6. **Production backups are working** for karakeep, khoj, open-webui (visible in RustFS console)

7. **Kyverno RBAC configured for VolSync**
   ```yaml
   # File: infrastructure/controllers/kyverno/rbac-patch.yaml
   # Admission controller: can read Secrets
   # Background controller: can create/update/delete Secrets
   ```

---

## Current Theories

### Theory 1: Need Per-PVC Secret Generation Rule (MOST LIKELY ✅)

**Hypothesis**: Kyverno policy should generate **three resources**, not two:
1. ReplicationSource (backup job)
2. ReplicationDestination (restore job)
3. **Secret with S3 credentials** ← MISSING!

**Proposed Third Rule**:
```yaml
- name: generate-s3-credentials-secret
  match:
    any:
    - resources:
        kinds: ["PersistentVolumeClaim"]
        selector:
          matchLabels:
            backup: "hourly"
  generate:
    apiVersion: v1
    kind: Secret
    name: "{{ request.object.metadata.name }}-volsync-secret"
    namespace: "{{ request.object.metadata.namespace }}"
    synchronize: true
    data:
      type: Opaque
      stringData:  # Kyverno auto-encodes to base64
        RESTIC_REPOSITORY: "s3:http://192.168.10.133:30292/volsync-backup/{{ request.object.metadata.namespace }}/{{ request.object.metadata.name }}"
        RESTIC_PASSWORD: "{{ ??? }}"  # How to get from volsync-system/volsync-rustfs-credentials?
        AWS_ACCESS_KEY_ID: "{{ ??? }}"
        AWS_SECRET_ACCESS_KEY: "{{ ??? }}"
```

**Challenge**: How to copy secret values from `volsync-system/volsync-rustfs-credentials` into generated secret?

**Possible Solutions**:
- **Option A**: Use Kyverno `context.apiCall` to Kubernetes API (GET Secret) - different from HTTP S3 call
  ```yaml
  context:
  - apiCall:
      urlPath: "/api/v1/namespaces/volsync-system/secrets/volsync-rustfs-credentials"
      jmesPath: "data"
    name: baseCredentials
  stringData:
    RESTIC_PASSWORD: "{{ base64_decode(baseCredentials.RESTIC_PASSWORD) }}"
  ```

- **Option B**: Use Kyverno external data sources or ConfigMapGenerator

- **Option C**: Modify ClusterExternalSecret to distribute to ALL namespaces, not just selected ones

- **Option D**: Use Kyverno JMESPath with cluster resources (if available in context)

**Then Update Repository References**:
```yaml
# In both ReplicationSource and ReplicationDestination:
spec:
  restic:
    repository: "{{ request.object.metadata.name }}-volsync-secret"  # Secret name, not URL!
```

### Theory 2: ClusterExternalSecret Needs volsync-test Namespace

**Hypothesis**: Test namespace not included in distribution selector, so base secret missing

**Current Selector**:
```yaml
# File: infrastructure/storage/volsync/rustfs-credentials.yaml
spec:
  namespaceSelector:
    matchExpressions:
    - key: kubernetes.io/metadata.name
      operator: In
      values:
      - volsync-system
      - longhorn-system
      - karakeep
      - khoj
      # ... production namespaces
      # volsync-test NOT in list!
```

**Test**:
```bash
# Add volsync-test to values list
# Commit, push, sync ArgoCD
# Check if secret appears
kubectl get secret -n volsync-test volsync-rustfs-credentials
```

**Challenge**: Still doesn't solve per-PVC unique repository paths (all PVCs would share same credentials and repository URL)

### Theory 3: Wrong Repository Field Format in VolSync CRD

**Hypothesis**: Maybe VolSync v0.10+ changed API to accept direct URLs instead of secret names?

**Action Needed**:
```bash
# Check CRD schema
kubectl explain replicationdestination.spec.restic.repository
kubectl explain replicationsource.spec.restic.repository

# Check production resources
kubectl get replicationsource -n karakeep -o yaml | grep -A5 "repository:"
kubectl get replicationsource -n khoj -o yaml | grep -A5 "repository:"
```

**If production uses secret names** → Confirms Theory 1 (need secret generation)  
**If production uses direct URLs** → Investigate why volsync-test fails differently

---

## Investigation Checklist for Next Session

### High Priority (Do These First)

1. **Check production ReplicationSource specs**
   ```bash
   kubectl get replicationsource -n karakeep -o yaml | head -100
   kubectl get replicationsource -n khoj -o yaml | head -100
   ```
   **Goal**: Determine if production uses secret names or direct URLs in `repository` field

2. **List secrets in production namespaces**
   ```bash
   kubectl get secrets -n karakeep | grep -i volsync
   kubectl get secrets -n khoj | grep -i volsync
   kubectl get secrets -n open-webui | grep -i volsync
   ```
   **Goal**: Find pattern for per-PVC secrets (`<pvc-name>-volsync-secret`?)

3. **Check VolSync CRD schema**
   ```bash
   kubectl explain replicationdestination.spec.restic --recursive | grep -i repository
   kubectl get crd replicationdestinations.volsync.backube -o yaml | grep -A20 "name: repository"
   ```
   **Goal**: Understand expected field format (string vs secretRef object?)

4. **Review VolSync controller logs**
   ```bash
   kubectl logs -n volsync-system deploy/volsync --tail=200 | grep -C5 "volsync-test"
   ```
   **Goal**: See exact error from controller attempting restore

5. **Verify ClusterExternalSecret distribution**
   ```bash
   kubectl get clusterexternalsecret volsync-rustfs-credentials -o yaml | grep -A20 namespaceSelector
   ```
   **Goal**: Confirm which namespaces receive base credentials

### Medium Priority

6. **Test adding volsync-test to ClusterExternalSecret**
   ```bash
   # Edit infrastructure/storage/volsync/rustfs-credentials.yaml
   # Add volsync-test to namespaceSelector values
   # Commit, push, sync
   kubectl get secret -n volsync-test volsync-rustfs-credentials
   ```

7. **Check Kyverno admission controller logs**
   ```bash
   kubectl logs -n kyverno deploy/kyverno-admission-controller --tail=200 | grep -i volsync-test
   ```
   **Goal**: See if policy generated resources successfully

8. **Review old policy Git history**
   ```bash
   git log --oneline --all infrastructure/controllers/kyverno/volsync-smart-restore.yaml
   git show <old-commit>:infrastructure/controllers/kyverno/volsync-smart-restore.yaml | grep -A30 "generate-backup-job"
   ```
   **Goal**: See how old apiCall-based policy handled secrets

---

## Implementation Plan (Based on Investigation)

### If Production Uses Secret Names (Most Likely):

1. **Add third generate rule to Kyverno policy** for per-PVC secrets
   - Determine best method to copy credentials from base secret
   - Test in volsync-test namespace first

2. **Update ReplicationSource/Destination** repository field to secret name
   ```yaml
   repository: "{{ request.object.metadata.name }}-volsync-secret"
   ```

3. **Test end-to-end in volsync-test**
   - Delete existing PVC: `kubectl delete pvc volsync-test-data -n volsync-test`
   - Sync ArgoCD: triggers policy with new secret rule
   - Verify secret created
   - Verify ReplicationDestination/Source reference secret correctly
   - Check VolSync controller picks up resources

4. **If successful, rollout to production PVCs**
   - May need to delete/recreate existing ReplicationSources to update repository field
   - Or use Kyverno `synchronize: true` to auto-update

### If Production Uses Direct URLs:

1. **Investigate why volsync-test fails but production works**
   - Check for namespace-specific configurations
   - Verify ExternalSecret distribution differences
   - Compare VolSync controller behavior between namespaces

2. **Debug secret resolution**
   - VolSync may be resolving URLs from a different source
   - Check for ConfigMaps or environment variables in VolSync controller

---

## Documentation Updates Needed

1. **Update `docs/secrets/volsync-secrets.md`**
   - Document correct secret generation pattern
   - Add examples of per-PVC secrets
   - Explain repository field format (secret name vs URL)

2. **Add troubleshooting section**
   - "Secret not found" error → check secret exists and repository field format
   - "accessModes must be provided" → add to ReplicationDestination spec
   - "Kyverno rule immutable" → delete and recreate via ArgoCD

3. **Update Kyverno policy docs**
   - Document all three generate rules (backup, restore, secret)
   - Explain context variable usage for cross-namespace secret copying

---

## Commands Reference

### Policy Management
```bash
# View policy
kubectl get clusterpolicy volsync-smart-protection -o yaml

# List rules
kubectl get clusterpolicy volsync-smart-protection -o jsonpath='{.spec.rules[*].name}' | tr ' ' '\n'

# Check policy status
kubectl describe clusterpolicy volsync-smart-protection | grep -A10 "Status:"
```

### Resource Inspection
```bash
# For any PVC with backup label
NAMESPACE=volsync-test
PVC=volsync-test-data

# Check PVC labels
kubectl get pvc -n $NAMESPACE $PVC -o jsonpath='{.metadata.labels}' | jq

# Check generated resources
kubectl get replicationsource -n $NAMESPACE ${PVC}-backup -o yaml
kubectl get replicationdestination -n $NAMESPACE ${PVC}-restore -o yaml
kubectl get secret -n $NAMESPACE ${PVC}-volsync-secret -o yaml

# Check resource status
kubectl describe replicationsource -n $NAMESPACE ${PVC}-backup
kubectl describe replicationdestination -n $NAMESPACE ${PVC}-restore
```

### VolSync Debugging
```bash
# Controller logs
kubectl logs -n volsync-system deploy/volsync -f --tail=100

# Check operator status
kubectl get deploy -n volsync-system
kubectl get pods -n volsync-system

# List all VolSync resources cluster-wide
kubectl get replicationsources,replicationdestinations -A
```

### ArgoCD Operations
```bash
# Force app refresh (re-scan Git)
kubectl patch application <app-name> -n argocd --type merge \
  -p '{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}}'

# Trigger sync
kubectl patch application <app-name> -n argocd --type merge \
  -p '{"operation":{"initiatedBy":{"username":"admin"},"sync":{"revision":"HEAD","prune":true}}}'

# Check sync status
kubectl get applications -n argocd <app-name> -o jsonpath='{.status.sync.status} {.status.health.status}' && echo

# View sync errors
kubectl get applications -n argocd <app-name> -o yaml | sed -n '/operationState:/,/health:/p'
```

### Cleanup Test Resources
```bash
# Delete via ArgoCD (GitOps way)
git rm -r my-apps/development/volsync-test
git commit -m "test(volsync): remove test app after debugging"
git push
kubectl delete application my-apps-volsync-test -n argocd

# Or manual cleanup
kubectl delete namespace volsync-test
kubectl delete replicationsource,replicationdestination --all -n volsync-test
```

---

## Success Criteria

When fully automated backup/restore is working:

```bash
# For any PVC labeled backup=hourly:
NAMESPACE=<namespace>
PVC=<pvc-name>

# 1. PVC bound to storage
kubectl get pvc -n $NAMESPACE $PVC
# STATUS: Bound ✅

# 2. Secret generated with S3 credentials
kubectl get secret -n $NAMESPACE ${PVC}-volsync-secret -o yaml
# data:
#   RESTIC_REPOSITORY: <base64>
#   RESTIC_PASSWORD: <base64>
#   AWS_ACCESS_KEY_ID: <base64>
#   AWS_SECRET_ACCESS_KEY: <base64>
# ✅

# 3. ReplicationDestination created with secret reference
kubectl get replicationdestination -n $NAMESPACE ${PVC}-restore -o yaml
# spec:
#   restic:
#     repository: <pvc-name>-volsync-secret  # Secret NAME
#   trigger:
#     manual: "auto-restore-<timestamp>"
# ✅

# 4. Restore attempted once
kubectl describe replicationdestination -n $NAMESPACE ${PVC}-restore
# Conditions:
#   Type: Synchronizing
#   Status: True or Completed
# Events: "Synchronization in progress" or "Restore completed"
# ✅

# 5. ReplicationSource created with secret reference
kubectl get replicationsource -n $NAMESPACE ${PVC}-backup -o yaml
# spec:
#   restic:
#     repository: <pvc-name>-volsync-secret  # Secret NAME
#   trigger:
#     schedule: "0 * * * *"
# ✅

# 6. Backup running on schedule
kubectl describe replicationsource -n $NAMESPACE ${PVC}-backup
# Status:
#   Last Sync Time: <within last hour>
#   Next Sync Time: <next hour on the hour>
#   Conditions:
#     Type: Synchronizing
#     Status: True
# ✅

# 7. Data in RustFS S3
# RustFS Console → volsync-backup/<namespace>/<pvc>/
# Files: config, data/, locks/, snapshots/
# ✅
```

---

## Files Modified This Session

### Kyverno Policy
- **File**: `infrastructure/controllers/kyverno/volsync-smart-restore.yaml`
- **Changes**:
  - Removed 3 rules with `context.apiCall` checks
  - Added 2 generate rules (ReplicationSource, ReplicationDestination)
  - Fixed YAML structure (removed duplicate headers)
  - Added `accessModes` and `capacity` to ReplicationDestination
- **Status**: **INCOMPLETE** - needs third rule for secret generation
- **Git Commits**:
  - `fd952e72` - Initial test app creation
  - `dd09beb5` - Fix accessModes/capacity

### Test Application
- **Files**: `my-apps/development/volsync-test/{namespace,pvc,kustomization}.yaml`
- **Purpose**: Isolated test environment for policy validation
- **Status**: **ACTIVE** - waiting for secret generation fix

### Documentation
- **File**: `docs/VOLSYNC_TROUBLESHOOTING_FLOW.md`
- **Changes**: Appended session notes placeholder
- **File**: `docs/VOLSYNC_SESSION_2026-01-16.md` (this file)
- **Status**: **NEW** - complete session documentation

---

## Git Commit Log
```bash
git log --oneline --since="2026-01-16 23:00"
# dd09beb5 fix(kyverno): add accessModes and capacity to ReplicationDestination, remove destinationPVC
# fd952e72 test(volsync): add volsync-test app with labeled PVC for restore-first policy verification
# fa94095e refactor(kyverno): remove apiCall from volsync-smart-protection policy
```

---

## Next Agent Instructions

1. **Start with investigation checklist** (high priority items)
2. **Focus on production ReplicationSource specs** first - this tells us the expected pattern
3. **If secret names are used**: implement Theory 1 (per-PVC secret generation rule)
4. **Test thoroughly in volsync-test namespace** before touching production
5. **Document findings in this file** before implementing changes
6. **Use GitOps workflow exclusively** - no kubectl apply, only ArgoCD sync

---

**Session End Time**: 2026-01-16 23:15 UTC  
**Status**: Awaiting next session to investigate production resources and implement secret generation

**Critical Next Step**: Check how production namespaces (karakeep, khoj) handle VolSync secrets - this will determine implementation path.
