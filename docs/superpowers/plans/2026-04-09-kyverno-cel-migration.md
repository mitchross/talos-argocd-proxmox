# Kyverno CEL Migration + Webhook Deadlock Prevention

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate all 4 legacy ClusterPolicies to CEL-based policy types (ValidatingPolicy, MutatingPolicy, GeneratingPolicy) and add infrastructure namespace exclusions to the Kyverno webhook to prevent the boot deadlock that caused a full cluster outage on 2026-04-08.

**Architecture:** Legacy `ClusterPolicy` (kyverno.io/v1) bundles validate+mutate+generate into one resource. CEL migration splits each into specialized types (`policies.kyverno.io/v1`): ValidatingPolicy, MutatingPolicy, GeneratingPolicy. The `ClusterCleanupPolicy` (v2) stays as-is since it's already a separate type with no CEL equivalent. Webhook namespace exclusions are added via Helm values so infrastructure namespaces (longhorn-system, argocd, volsync-system, etc.) can boot without waiting for Kyverno.

**Tech Stack:** Kyverno 1.17.1 (Helm chart 3.7.1), CEL expressions, ArgoCD GitOps

**RCA Context:** On 2026-04-08, a kube-prometheus-stack Helm upgrade caused Kyverno's admission controller to crash-loop ("failed to wait for cache sync" on v1beta1 informers). The `failurePolicy: Fail` webhook blocked all Deployment/StatefulSet/DaemonSet operations in non-excluded namespaces, preventing Longhorn, ArgoCD, and all operators from starting. The cluster was completely down for hours. Removing legacy ClusterPolicy resources eliminates the v1beta1 informer load, and adding namespace exclusions ensures infrastructure can boot even if Kyverno is temporarily unhealthy.

---

## Critical Constraints

1. **Fail-closed PVC gate MUST be preserved** — PVC creation with backup labels must be denied if PVC Plumber is unreachable. This prevents data loss during DR.
2. **NFS injection into VolSync mover jobs MUST work** — Without it, backups fail silently.
3. **Generated resources (ExternalSecret, ReplicationSource, ReplicationDestination) MUST have identical specs** — Any field drift breaks backup/restore.
4. **VPA auto-generation logic MUST match** — Infrastructure = "Off" mode, apps = "Initial" mode.
5. **Canonical form for ArgoCD sync** — All defaulted fields must be explicit to prevent OutOfSync.
6. **`synchronize: false` on all generate rules** — Prevents API server overload from drift watchers.
7. **`background: false` equivalent** — Prevents continuous background scanning.
8. **ClusterCleanupPolicy stays as-is** — It's already v2, no CEL equivalent exists.
9. **Don't break existing generated resources** — Existing ReplicationSources, VPAs, etc. should not be deleted or recreated.

## Policy Migration Map

| Legacy Policy | New Type(s) | Notes |
|---|---|---|
| `volsync-pvc-backup-restore` (ClusterPolicy) | `volsync-pvc-validate` (ValidatingPolicy) + `volsync-pvc-mutate` (MutatingPolicy) + `volsync-pvc-generate` (GeneratingPolicy) | Split into 3 specialized types |
| `volsync-nfs-inject` (ClusterPolicy) | `volsync-nfs-inject` (MutatingPolicy) | Direct conversion |
| `vpa-auto-generate` (ClusterPolicy) | `vpa-auto-generate` (GeneratingPolicy) | Direct conversion |
| `vpa-min-allowed` (ClusterPolicy) | `vpa-min-allowed` (MutatingPolicy) | Direct conversion |
| `volsync-orphan-cleanup` (ClusterCleanupPolicy v2) | **No change** | Already separate type |

## File Structure

### New files to create:
- `infrastructure/controllers/kyverno/policies/volsync-pvc-validate.yaml` — ValidatingPolicy (fail-closed gate)
- `infrastructure/controllers/kyverno/policies/volsync-pvc-mutate.yaml` — MutatingPolicy (dataSourceRef injection)
- `infrastructure/controllers/kyverno/policies/volsync-pvc-generate.yaml` — GeneratingPolicy (ExternalSecret + ReplicationSource + ReplicationDestination)
- `infrastructure/controllers/kyverno/policies/volsync-nfs-inject-cel.yaml` — MutatingPolicy (NFS volume injection)
- `infrastructure/controllers/kyverno-vpa-policies/vpa-auto-generate-cel.yaml` — GeneratingPolicy (VPA creation)
- `infrastructure/controllers/kyverno-vpa-policies/vpa-min-allowed-cel.yaml` — MutatingPolicy (minAllowed injection)
- `scripts/emergency-webhook-cleanup.sh` — Emergency recovery script

### Files to modify:
- `infrastructure/controllers/kyverno/values.yaml` — Add webhook namespace exclusions
- `infrastructure/controllers/kyverno/kustomization.yaml` — Swap old policies for new
- `infrastructure/controllers/kyverno-vpa-policies/kustomization.yaml` — Swap old policies for new

### Files to delete (after migration verified):
- `infrastructure/controllers/kyverno/policies/volsync-pvc-backup-restore.yaml`
- `infrastructure/controllers/kyverno/policies/volsync-nfs-inject.yaml`
- `infrastructure/controllers/kyverno-vpa-policies/vpa-auto-generate.yaml`
- `infrastructure/controllers/kyverno-vpa-policies/vpa-min-allowed.yaml`

---

## Task 1: Add Webhook Namespace Exclusions (Deadlock Prevention)

**Files:**
- Modify: `infrastructure/controllers/kyverno/values.yaml`
- Create: `scripts/emergency-webhook-cleanup.sh`

This is the highest-priority fix — it prevents the deadlock even before CEL migration.

- [ ] **Step 1: Add infrastructure namespaces to webhook exclusion**

In `infrastructure/controllers/kyverno/values.yaml`, update the `config` section. Add a new top-level `config` key with webhook namespace exclusions:

```yaml
# Add at the TOP of values.yaml, before admissionController:
config:
  webhooks:
    namespaceSelector:
      matchExpressions:
      - key: kubernetes.io/metadata.name
        operator: NotIn
        values:
          - kube-system
          # Infrastructure namespaces that must boot before Kyverno is healthy
          - longhorn-system
          - argocd
          - volsync-system
          - cilium       # if cilium has its own namespace
          - snapshot-controller
          - cert-manager
          - external-secrets
          - 1passwordconnect
  excludeKyvernoNamespace: true
```

**Why these namespaces:** These are Waves 0-2 in the sync wave architecture. They must start before Kyverno (Wave 3). The fail-closed PVC gate only needs to protect Wave 4-6 app namespaces.

- [ ] **Step 2: Create emergency webhook cleanup script**

Create `scripts/emergency-webhook-cleanup.sh`:

```bash
#!/usr/bin/env bash
# Emergency: Remove all Kyverno webhooks to unblock cluster recovery
# Run this when the cluster is in a webhook deadlock (pods can't be created)
# Kyverno will recreate its webhooks once it's healthy again.
set -euo pipefail

echo "WARNING: This will delete ALL Kyverno webhook configurations."
echo "Kyverno will recreate them once it starts successfully."
echo ""
read -p "Continue? (yes/no): " confirm
[[ "$confirm" == "yes" ]] || exit 1

echo "Deleting Kyverno validating webhooks..."
kubectl delete validatingwebhookconfigurations -l app.kubernetes.io/instance=kyverno --ignore-not-found

echo "Deleting Kyverno mutating webhooks..."
kubectl delete mutatingwebhookconfigurations -l app.kubernetes.io/instance=kyverno --ignore-not-found

echo "Done. Monitor Kyverno pods: kubectl get pods -n kyverno -w"
echo "Webhooks will be recreated when Kyverno admission controller is healthy."
```

- [ ] **Step 3: Commit**

```bash
chmod +x scripts/emergency-webhook-cleanup.sh
git add infrastructure/controllers/kyverno/values.yaml scripts/emergency-webhook-cleanup.sh
git commit -m "fix: add infrastructure namespace exclusions to Kyverno webhook

Prevents webhook deadlock on cluster recovery. Infrastructure namespaces
(Waves 0-2) are excluded so Longhorn, ArgoCD, and other operators can
boot without waiting for Kyverno. Fail-closed PVC gate still protects
app namespaces (Waves 4-6).

Also adds emergency-webhook-cleanup.sh for manual recovery."
```

---

## Task 2: Migrate volsync-pvc-backup-restore — ValidatingPolicy (Fail-Closed Gate)

**Files:**
- Create: `infrastructure/controllers/kyverno/policies/volsync-pvc-validate.yaml`

- [ ] **Step 1: Write the ValidatingPolicy**

This replaces Rule 0 (require-pvc-plumber-available) from the legacy ClusterPolicy. Uses `http.Get()` to call PVC Plumber health endpoint.

```yaml
---
apiVersion: policies.kyverno.io/v1
kind: ValidatingPolicy
metadata:
  name: volsync-pvc-validate
  annotations:
    argocd.argoproj.io/sync-wave: "4"
    policies.kyverno.io/title: VolSync PVC Backup Gate (Fail-Closed)
    policies.kyverno.io/description: >-
      Denies PVC creation with backup labels if PVC Plumber is unreachable.
      Prevents data loss during disaster recovery by ensuring the backup
      existence checker is healthy before allowing backup-labeled PVCs.
spec:
  validationActions: [Deny]
  matchConstraints:
    resourceRules:
      - apiGroups: ['']
        apiVersions: ['v1']
        operations: ['CREATE']
        resources: ['persistentvolumeclaims']
    excludeResourceRules:
      - resourceNames: []
        namespaces: ['kube-system', 'volsync-system', 'kyverno']
  matchConditions:
    - name: has-backup-label
      expression: >-
        has(object.metadata.labels) &&
        has(object.metadata.labels.backup) &&
        object.metadata.labels.backup in ['hourly', 'daily']
  variables:
    - name: plumberHealth
      expression: >-
        http.Get("http://pvc-plumber.volsync-system.svc.cluster.local/readyz")
  validations:
    - expression: >-
        variables.plumberHealth != null
      message: >-
        PVC Plumber is not available. Backup-labeled PVCs cannot be created
        until PVC Plumber is healthy in volsync-system namespace. This ensures
        backup restoration works correctly during disaster recovery.
```

- [ ] **Step 2: Test locally with kyverno CLI**

```bash
# Dry-run test: verify the policy YAML is valid
kubectl apply --dry-run=server -f infrastructure/controllers/kyverno/policies/volsync-pvc-validate.yaml
```

Expected: No errors (the CRD exists since Kyverno 1.17 is installed).

- [ ] **Step 3: Commit**

```bash
git add infrastructure/controllers/kyverno/policies/volsync-pvc-validate.yaml
git commit -m "feat: add ValidatingPolicy for PVC Plumber fail-closed gate (CEL)"
```

---

## Task 3: Migrate volsync-pvc-backup-restore — MutatingPolicy (dataSourceRef Injection)

**Files:**
- Create: `infrastructure/controllers/kyverno/policies/volsync-pvc-mutate.yaml`

- [ ] **Step 1: Write the MutatingPolicy**

This replaces Rule 1 (add-datasource-if-backup-exists). Uses `http.Get()` to call PVC Plumber `/exists` endpoint and conditionally adds `dataSourceRef`.

```yaml
---
apiVersion: policies.kyverno.io/v1
kind: MutatingPolicy
metadata:
  name: volsync-pvc-mutate
  annotations:
    argocd.argoproj.io/sync-wave: "4"
    policies.kyverno.io/title: VolSync PVC Auto-Restore (dataSourceRef Injection)
    policies.kyverno.io/description: >-
      On PVC creation with backup labels, checks PVC Plumber for existing backups.
      If a backup exists, adds dataSourceRef pointing to the ReplicationDestination
      for automatic restore via VolSync.
spec:
  matchConstraints:
    resourceRules:
      - apiGroups: ['']
        apiVersions: ['v1']
        operations: ['CREATE']
        resources: ['persistentvolumeclaims']
    excludeResourceRules:
      - resourceNames: []
        namespaces: ['kube-system', 'volsync-system', 'kyverno']
  matchConditions:
    - name: has-backup-label
      expression: >-
        has(object.metadata.labels) &&
        has(object.metadata.labels.backup) &&
        object.metadata.labels.backup in ['hourly', 'daily']
    - name: no-existing-datasource
      expression: >-
        !has(object.spec.dataSourceRef)
  variables:
    - name: pvcName
      expression: "object.metadata.name"
    - name: pvcNamespace
      expression: "object.metadata.namespace"
    - name: backupCheck
      expression: >-
        http.Get("http://pvc-plumber.volsync-system.svc.cluster.local/exists/" + variables.pvcNamespace + "/" + variables.pvcName)
  mutations:
    - patchType: JSONPatch
      jsonPatch:
        expression: >-
          (variables.backupCheck != null && has(variables.backupCheck.exists) && variables.backupCheck.exists == true) ?
          [JSONPatch{op: "add", path: "/spec/dataSourceRef", value: Object.spec.DataSourceRef{
            apiGroup: dyn("volsync.backube"),
            kind: dyn("ReplicationDestination"),
            name: dyn(variables.pvcName + "-backup")
          }}] : []
```

**Note:** The JSONPatch conditional expression returns an empty array `[]` if no backup exists, meaning no mutation happens. If backup exists, it adds the `dataSourceRef`.

- [ ] **Step 2: Test locally**

```bash
kubectl apply --dry-run=server -f infrastructure/controllers/kyverno/policies/volsync-pvc-mutate.yaml
```

- [ ] **Step 3: Commit**

```bash
git add infrastructure/controllers/kyverno/policies/volsync-pvc-mutate.yaml
git commit -m "feat: add MutatingPolicy for PVC auto-restore dataSourceRef injection (CEL)"
```

---

## Task 4: Migrate volsync-pvc-backup-restore — GeneratingPolicy (Backup Resources)

**Files:**
- Create: `infrastructure/controllers/kyverno/policies/volsync-pvc-generate.yaml`

- [ ] **Step 1: Write the GeneratingPolicy**

This replaces Rules 2-4 (generate-kopia-secret, generate-replication-source, generate-replication-destination). Uses `generator.Apply()` with dynamic CEL expressions.

```yaml
---
apiVersion: policies.kyverno.io/v1
kind: GeneratingPolicy
metadata:
  name: volsync-pvc-generate
  annotations:
    argocd.argoproj.io/sync-wave: "4"
    policies.kyverno.io/title: VolSync PVC Backup Resource Generation (CEL)
    policies.kyverno.io/description: >-
      Generates ExternalSecret (Kopia credentials), ReplicationSource (backup schedule),
      and ReplicationDestination (restore capability) for PVCs with backup labels.
spec:
  evaluation:
    synchronize:
      enabled: false
  matchConstraints:
    resourceRules:
      - apiGroups: ['']
        apiVersions: ['v1']
        operations: ['CREATE', 'UPDATE']
        resources: ['persistentvolumeclaims']
    excludeResourceRules:
      - resourceNames: []
        namespaces: ['kube-system', 'volsync-system', 'kyverno']
  matchConditions:
    - name: has-backup-label
      expression: >-
        has(object.metadata.labels) &&
        has(object.metadata.labels.backup) &&
        object.metadata.labels.backup in ['hourly', 'daily']
  variables:
    - name: pvcName
      expression: "object.metadata.name"
    - name: pvcNamespace
      expression: "object.metadata.namespace"
    - name: backupLabel
      expression: "object.metadata.labels.backup"
    - name: schedule
      expression: >-
        variables.backupLabel == 'hourly' ? '0 * * * *' : '0 2 * * *'
    - name: accessMode
      expression: >-
        has(object.spec.accessModes) && size(object.spec.accessModes) > 0 ?
        object.spec.accessModes[0] : 'ReadWriteOnce'
    - name: storageSize
      expression: "object.spec.resources.requests['storage']"
    - name: isBound
      expression: >-
        has(object.status) && has(object.status.phase) && object.status.phase == 'Bound'
    - name: externalSecret
      expression: >-
        [
          {
            "apiVersion": dyn("external-secrets.io/v1"),
            "kind": dyn("ExternalSecret"),
            "metadata": dyn({
              "name": "volsync-" + variables.pvcName,
              "namespace": variables.pvcNamespace,
              "labels": {
                "app.kubernetes.io/managed-by": "kyverno",
                "volsync.backup/pvc": variables.pvcName
              }
            }),
            "spec": dyn({
              "refreshInterval": "1h",
              "secretStoreRef": {
                "kind": "ClusterSecretStore",
                "name": "1password"
              },
              "target": {
                "name": "volsync-" + variables.pvcName,
                "creationPolicy": "Owner",
                "template": {
                  "engineVersion": "v2",
                  "mergePolicy": "Merge",
                  "metadata": {
                    "labels": {
                      "app.kubernetes.io/managed-by": "kyverno",
                      "volsync.backup/pvc": variables.pvcName
                    }
                  },
                  "data": {
                    "KOPIA_REPOSITORY": "filesystem:///repository",
                    "KOPIA_FS_PATH": "/repository"
                  }
                }
              },
              "data": [
                {
                  "secretKey": "KOPIA_PASSWORD",
                  "remoteRef": {
                    "key": "rustfs",
                    "property": "kopia_password"
                  }
                }
              ]
            })
          }
        ]
    - name: replicationDest
      expression: >-
        [
          {
            "apiVersion": dyn("volsync.backube/v1alpha1"),
            "kind": dyn("ReplicationDestination"),
            "metadata": dyn({
              "name": variables.pvcName + "-backup",
              "namespace": variables.pvcNamespace,
              "labels": {
                "app.kubernetes.io/managed-by": "kyverno",
                "volsync.backup/pvc": variables.pvcName
              }
            }),
            "spec": dyn({
              "trigger": {"manual": "restore-once"},
              "kopia": {
                "repository": "volsync-" + variables.pvcName,
                "copyMethod": "Snapshot",
                "storageClassName": "longhorn",
                "volumeSnapshotClassName": "longhorn-snapclass",
                "accessModes": [variables.accessMode],
                "capacity": variables.storageSize,
                "cacheCapacity": "2Gi",
                "moverSecurityContext": {
                  "runAsUser": 568,
                  "runAsGroup": 568,
                  "fsGroup": 568
                }
              }
            })
          }
        ]
    - name: replicationSource
      expression: >-
        variables.isBound ?
        [
          {
            "apiVersion": dyn("volsync.backube/v1alpha1"),
            "kind": dyn("ReplicationSource"),
            "metadata": dyn({
              "name": variables.pvcName + "-backup",
              "namespace": variables.pvcNamespace,
              "labels": {
                "app.kubernetes.io/managed-by": "kyverno",
                "volsync.backup/pvc": variables.pvcName
              }
            }),
            "spec": dyn({
              "sourcePVC": variables.pvcName,
              "trigger": {"schedule": variables.schedule},
              "kopia": {
                "repository": "volsync-" + variables.pvcName,
                "compression": "zstd-fastest",
                "parallelism": 2,
                "retain": {
                  "hourly": 24,
                  "daily": 7,
                  "weekly": 4,
                  "monthly": 2
                },
                "copyMethod": "Snapshot",
                "storageClassName": "longhorn",
                "volumeSnapshotClassName": "longhorn-snapclass",
                "cacheCapacity": "2Gi",
                "moverSecurityContext": {
                  "runAsUser": 568,
                  "runAsGroup": 568,
                  "fsGroup": 568
                }
              }
            })
          }
        ] : []
  generate:
    - expression: >-
        generator.Apply(variables.pvcNamespace, variables.externalSecret)
    - expression: >-
        generator.Apply(variables.pvcNamespace, variables.replicationDest)
    - expression: >-
        size(variables.replicationSource) > 0 ?
        generator.Apply(variables.pvcNamespace, variables.replicationSource) : true
```

**Key differences from legacy:**
- ReplicationSource only generated when PVC is Bound (via `isBound` check)
- The 2-hour age precondition is harder to express in CEL (no `time_since` equivalent) — may need to be dropped or handled differently
- `synchronize: false` via `evaluation.synchronize.enabled: false`

- [ ] **Step 2: Test locally**

```bash
kubectl apply --dry-run=server -f infrastructure/controllers/kyverno/policies/volsync-pvc-generate.yaml
```

- [ ] **Step 3: Commit**

```bash
git add infrastructure/controllers/kyverno/policies/volsync-pvc-generate.yaml
git commit -m "feat: add GeneratingPolicy for VolSync backup resources (CEL)"
```

---

## Task 5: Migrate volsync-nfs-inject — MutatingPolicy

**Files:**
- Create: `infrastructure/controllers/kyverno/policies/volsync-nfs-inject-cel.yaml`

- [ ] **Step 1: Write the MutatingPolicy**

```yaml
---
apiVersion: policies.kyverno.io/v1
kind: MutatingPolicy
metadata:
  name: volsync-nfs-inject
  annotations:
    argocd.argoproj.io/sync-wave: "4"
    policies.kyverno.io/title: VolSync NFS Mount Injection (CEL)
    policies.kyverno.io/description: >-
      Injects NFS volume mount into VolSync mover jobs so Kopia can
      access the shared repository on TrueNAS.
spec:
  matchConstraints:
    resourceRules:
      - apiGroups: ['batch']
        apiVersions: ['v1']
        operations: ['CREATE']
        resources: ['jobs']
  matchConditions:
    - name: is-volsync-job
      expression: >-
        has(object.metadata.labels) &&
        has(object.metadata.labels['app.kubernetes.io/created-by']) &&
        object.metadata.labels['app.kubernetes.io/created-by'] == 'volsync'
  mutations:
    - patchType: ApplyConfiguration
      applyConfiguration:
        expression: >-
          Object{
            spec: Object.spec{
              template: Object.spec.template{
                spec: Object.spec.template.spec{
                  volumes: [
                    Object.spec.template.spec.volumes{
                      name: "repository",
                      nfs: Object.spec.template.spec.volumes.nfs{
                        server: "192.168.10.133",
                        path: "/mnt/BigTank/k8s/volsync-kopia-nfs"
                      }
                    }
                  ]
                }
              }
            }
          }
    - patchType: JSONPatch
      jsonPatch:
        expression: >-
          object.spec.template.spec.containers.map(c, c.name).enumerate().map(e,
            JSONPatch{
              op: "add",
              path: "/spec/template/spec/containers/" + string(e.index) + "/volumeMounts/-",
              value: {
                "name": "repository",
                "mountPath": "/repository"
              }
            }
          )
```

- [ ] **Step 2: Test locally**

```bash
kubectl apply --dry-run=server -f infrastructure/controllers/kyverno/policies/volsync-nfs-inject-cel.yaml
```

- [ ] **Step 3: Commit**

```bash
git add infrastructure/controllers/kyverno/policies/volsync-nfs-inject-cel.yaml
git commit -m "feat: add MutatingPolicy for VolSync NFS injection (CEL)"
```

---

## Task 6: Migrate vpa-auto-generate — GeneratingPolicy

**Files:**
- Create: `infrastructure/controllers/kyverno-vpa-policies/vpa-auto-generate-cel.yaml`

- [ ] **Step 1: Write the GeneratingPolicy**

```yaml
---
apiVersion: policies.kyverno.io/v1
kind: GeneratingPolicy
metadata:
  name: vpa-auto-generate
  annotations:
    argocd.argoproj.io/sync-wave: "4"
    policies.kyverno.io/title: Auto-Generate VPA for All Workloads (CEL)
    policies.kyverno.io/description: >-
      Automatically creates a VerticalPodAutoscaler for every Deployment,
      StatefulSet, and DaemonSet. Infrastructure namespaces get updateMode "Off"
      (recommend-only). User app namespaces get "Initial" for automatic tuning.
spec:
  evaluation:
    synchronize:
      enabled: false
  matchConstraints:
    resourceRules:
      - apiGroups: ['apps']
        apiVersions: ['v1']
        operations: ['CREATE']
        resources: ['deployments', 'statefulsets', 'daemonsets']
    excludeResourceRules:
      - resourceNames: []
        namespaces: ['kube-system', 'kyverno', 'volsync-system']
  variables:
    - name: workloadName
      expression: "object.metadata.name"
    - name: workloadNamespace
      expression: "object.metadata.namespace"
    - name: workloadKind
      expression: "object.kind"
    - name: workloadUid
      expression: "string(object.metadata.uid)"
    - name: infraNamespaces
      expression: >-
        ['argocd', '1passwordconnect', 'external-secrets',
         'longhorn-system', 'snapshot-controller',
         'cert-manager', 'external-dns', 'gpu-device-plugin', 'gpu-operator',
         'metrics-server', 'node-feature-discovery', 'reloader', 'vertical-pod-autoscaler',
         'cloudflared', 'gateway', 'csi-driver-nfs', 'csi-driver-smb', 'kopia-ui', 'local-storage',
         'cloudnative-pg', 'postgres-operator', 'redis', 'redis-instance',
         'prometheus-stack', 'loki-stack', 'monitoring', 'k8sgpt', 'pod-cleanup']
    - name: isInfra
      expression: "variables.workloadNamespace in variables.infraNamespaces"
    - name: updateMode
      expression: "variables.isInfra ? 'Off' : 'Initial'"
    - name: modeLabel
      expression: "variables.isInfra ? 'off' : 'auto'"
    - name: vpaResource
      expression: >-
        [
          {
            "apiVersion": dyn("autoscaling.k8s.io/v1"),
            "kind": dyn("VerticalPodAutoscaler"),
            "metadata": dyn({
              "name": variables.workloadName,
              "namespace": variables.workloadNamespace,
              "labels": {
                "app.kubernetes.io/managed-by": "kyverno",
                "vpa.kubernetes.io/mode": variables.modeLabel
              },
              "ownerReferences": [
                {
                  "apiVersion": "apps/v1",
                  "kind": variables.workloadKind,
                  "name": variables.workloadName,
                  "uid": variables.workloadUid
                }
              ]
            }),
            "spec": dyn({
              "targetRef": {
                "apiVersion": "apps/v1",
                "kind": variables.workloadKind,
                "name": variables.workloadName
              },
              "updatePolicy": {
                "updateMode": variables.updateMode
              }
            })
          }
        ]
  generate:
    - expression: >-
        generator.Apply(variables.workloadNamespace, variables.vpaResource)
```

- [ ] **Step 2: Test locally**

```bash
kubectl apply --dry-run=server -f infrastructure/controllers/kyverno-vpa-policies/vpa-auto-generate-cel.yaml
```

- [ ] **Step 3: Commit**

```bash
git add infrastructure/controllers/kyverno-vpa-policies/vpa-auto-generate-cel.yaml
git commit -m "feat: add GeneratingPolicy for VPA auto-generation (CEL)"
```

---

## Task 7: Migrate vpa-min-allowed — MutatingPolicy

**Files:**
- Create: `infrastructure/controllers/kyverno-vpa-policies/vpa-min-allowed-cel.yaml`

- [ ] **Step 1: Write the MutatingPolicy**

```yaml
---
apiVersion: policies.kyverno.io/v1
kind: MutatingPolicy
metadata:
  name: vpa-min-allowed
  annotations:
    argocd.argoproj.io/sync-wave: "4"
    policies.kyverno.io/title: Inject VPA minAllowed from Workload Annotations (CEL)
    policies.kyverno.io/description: >-
      Reads vpa.kubernetes.io/min-memory annotation from the VPA's target
      workload and injects it as minAllowed into the VPA's resourcePolicy.
spec:
  matchConstraints:
    resourceRules:
      - apiGroups: ['autoscaling.k8s.io']
        apiVersions: ['v1']
        operations: ['CREATE', 'UPDATE']
        resources: ['verticalpodautoscalers']
  matchConditions:
    - name: managed-by-kyverno
      expression: >-
        has(object.metadata.labels) &&
        has(object.metadata.labels['app.kubernetes.io/managed-by']) &&
        object.metadata.labels['app.kubernetes.io/managed-by'] == 'kyverno'
  variables:
    - name: targetKind
      expression: "object.spec.targetRef.kind"
    - name: targetName
      expression: "object.spec.targetRef.name"
    - name: targetNamespace
      expression: "object.metadata.namespace"
    - name: pluralKind
      expression: >-
        variables.targetKind == 'Deployment' ? 'deployments' :
        variables.targetKind == 'StatefulSet' ? 'statefulsets' : 'daemonsets'
    - name: workload
      expression: >-
        resource.Get("apps/v1", variables.pluralKind, variables.targetNamespace, variables.targetName)
    - name: hasMinMemory
      expression: >-
        variables.workload != null &&
        has(variables.workload.metadata.annotations) &&
        has(variables.workload.metadata.annotations['vpa.kubernetes.io/min-memory'])
    - name: minMemory
      expression: >-
        variables.hasMinMemory ?
        variables.workload.metadata.annotations['vpa.kubernetes.io/min-memory'] : ''
  mutations:
    - patchType: ApplyConfiguration
      applyConfiguration:
        expression: >-
          variables.hasMinMemory ?
          Object{
            spec: Object.spec{
              resourcePolicy: Object.spec.resourcePolicy{
                containerPolicies: [
                  Object.spec.resourcePolicy.containerPolicies{
                    containerName: "*",
                    minAllowed: Object.spec.resourcePolicy.containerPolicies.minAllowed{
                      memory: variables.minMemory
                    }
                  }
                ]
              }
            }
          } : Object{}
```

- [ ] **Step 2: Test locally**

```bash
kubectl apply --dry-run=server -f infrastructure/controllers/kyverno-vpa-policies/vpa-min-allowed-cel.yaml
```

- [ ] **Step 3: Commit**

```bash
git add infrastructure/controllers/kyverno-vpa-policies/vpa-min-allowed-cel.yaml
git commit -m "feat: add MutatingPolicy for VPA minAllowed injection (CEL)"
```

---

## Task 8: Swap Kustomization References and Remove Legacy Policies

**Files:**
- Modify: `infrastructure/controllers/kyverno/kustomization.yaml`
- Modify: `infrastructure/controllers/kyverno-vpa-policies/kustomization.yaml`
- Delete: legacy policy files

- [ ] **Step 1: Update kyverno kustomization.yaml**

Replace the policy references:

```yaml
resources:
- namespace.yaml
- rbac-patch.yaml
- policies/volsync-pvc-validate.yaml
- policies/volsync-pvc-mutate.yaml
- policies/volsync-pvc-generate.yaml
- policies/volsync-nfs-inject-cel.yaml
- policies/volsync-orphan-cleanup.yaml
# Legacy policies removed:
# - policies/volsync-pvc-backup-restore.yaml
# - policies/volsync-nfs-inject.yaml
```

- [ ] **Step 2: Update kyverno-vpa-policies kustomization.yaml**

Read the current file first, then replace policy references.

- [ ] **Step 3: Delete legacy policy files**

```bash
git rm infrastructure/controllers/kyverno/policies/volsync-pvc-backup-restore.yaml
git rm infrastructure/controllers/kyverno/policies/volsync-nfs-inject.yaml
git rm infrastructure/controllers/kyverno-vpa-policies/vpa-auto-generate.yaml
git rm infrastructure/controllers/kyverno-vpa-policies/vpa-min-allowed.yaml
```

- [ ] **Step 4: Commit**

```bash
git add -A infrastructure/controllers/kyverno/ infrastructure/controllers/kyverno-vpa-policies/
git commit -m "chore: swap to CEL policies and remove legacy ClusterPolicies

Removes all kyverno.io/v1 ClusterPolicy resources in favor of
policies.kyverno.io/v1 ValidatingPolicy, MutatingPolicy, and
GeneratingPolicy. This eliminates v1beta1 informer load that caused
cache sync failures and cluster deadlock on 2026-04-08."
```

---

## Task 9: Verification Test Plan

After deploying, verify each policy works correctly. **Do NOT skip these tests.**

- [ ] **Test 1: Webhook namespace exclusion**

```bash
# Verify the webhook namespaceSelector includes infrastructure namespaces
kubectl get validatingwebhookconfigurations -l app.kubernetes.io/instance=kyverno -o json | \
  jq '.items[].webhooks[].namespaceSelector'

# Expected: NotIn list includes longhorn-system, argocd, volsync-system, etc.
```

- [ ] **Test 2: Fail-closed PVC gate**

```bash
# Scale down PVC Plumber to simulate it being unavailable
kubectl scale deployment pvc-plumber -n volsync-system --replicas=0
sleep 10

# Try to create a backup-labeled PVC — should be DENIED
cat <<EOF | kubectl apply -f - 2>&1
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: test-failclosed
  namespace: default
  labels:
    backup: "hourly"
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: longhorn
  resources:
    requests:
      storage: 1Gi
EOF
# Expected: Error — denied by volsync-pvc-validate

# Scale PVC Plumber back up
kubectl scale deployment pvc-plumber -n volsync-system --replicas=2

# Clean up
kubectl delete pvc test-failclosed -n default --ignore-not-found
```

- [ ] **Test 3: NFS injection into VolSync jobs**

```bash
# Trigger a backup and check that NFS mount is injected
kubectl get jobs -A -l app.kubernetes.io/created-by=volsync -o json | \
  jq '.items[0].spec.template.spec.volumes[] | select(.name=="repository")'

# Expected: NFS volume with server 192.168.10.133
```

- [ ] **Test 4: VPA generation**

```bash
# Check that VPAs exist for workloads
kubectl get vpa -A --no-headers | wc -l

# Check infrastructure namespace gets "Off" mode
kubectl get vpa -n argocd -o jsonpath='{.items[0].spec.updatePolicy.updateMode}'
# Expected: Off

# Check app namespace gets "Initial" mode
kubectl get vpa -n frigate -o jsonpath='{.items[0].spec.updatePolicy.updateMode}'
# Expected: Initial
```

- [ ] **Test 5: Verify no legacy ClusterPolicies remain**

```bash
kubectl get clusterpolicy --no-headers
# Expected: Only volsync-orphan-cleanup (ClusterCleanupPolicy) and possibly none
# All 4 ClusterPolicies should be gone
```

- [ ] **Test 6: Simulate deadlock recovery**

```bash
# Delete all Kyverno webhooks
./scripts/emergency-webhook-cleanup.sh

# Verify Longhorn pods can still be created in longhorn-system
kubectl rollout restart daemonset/longhorn-manager -n longhorn-system

# Wait for Kyverno to recreate webhooks
sleep 60
kubectl get validatingwebhookconfigurations -l app.kubernetes.io/instance=kyverno

# Verify webhook namespace exclusions are present
kubectl get validatingwebhookconfigurations -l app.kubernetes.io/instance=kyverno -o json | \
  jq '.items[].webhooks[].namespaceSelector.matchExpressions[].values' | sort -u
```

---

## Risk Mitigation

1. **Rollback plan:** If CEL policies don't work, restore the legacy files from git history and redeploy. The ClusterCleanupPolicy doesn't change so orphan cleanup continues working.
2. **Existing generated resources are NOT affected** — Deleting the old ClusterPolicy doesn't delete resources it previously generated (since `synchronize: false`).
3. **Deploy during low-traffic window** — The policy swap will briefly leave a gap where no policies are active. Deploy when no PVCs are being created.
4. **Test on a single PVC first** — After deployment, create a test PVC with `backup: daily` in a test namespace and verify the full flow (ExternalSecret, ReplicationSource, ReplicationDestination all generated).
