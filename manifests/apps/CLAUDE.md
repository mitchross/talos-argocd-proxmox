# Application Guidelines

## Adding New Applications

### Minimal Application (No storage/secrets)

```bash
# 1. Create directory structure
mkdir -p manifests/apps/category/app-name/deploy-targets/talos/.argocd

# 2. Create required files
cat > manifests/apps/category/app-name/deploy-targets/talos/namespace.yaml <<EOF
apiVersion: v1
kind: Namespace
metadata:
  name: app-name
EOF

cat > manifests/apps/category/app-name/deploy-targets/talos/kustomization.yaml <<EOF
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: app-name

resources:
- namespace.yaml
- deployment.yaml
- service.yaml
EOF

# 3. Add deploy-target metadata
cat > manifests/apps/category/app-name/deploy-targets/talos/.argocd/config.json <<EOF
{
  "applicationName": "talos-apps-category-app-name",
  "cluster": "talos",
  "project": "talos-apps",
  "namespace": "app-name",
  "part": "apps",
  "syncWave": "6",
  "sourcePath": "manifests/apps/category/app-name/deploy-targets/talos"
}
EOF

# 4. Git commit - ArgoCD discovers automatically
git add manifests/apps/category/app-name
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

# httproute.yaml - EXTERNAL (public via Cloudflare tunnel)
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: app-route
  namespace: app-name
  labels:
    external-dns: "true"                                    # REQUIRED - external-dns won't create DNS without this
  annotations:
    external-dns.alpha.kubernetes.io/target: vanillax.me    # REQUIRED - CNAMEs to Cloudflare tunnel
spec:
  parentRefs:
  - kind: Gateway
    name: gateway-external
    namespace: gateway
    sectionName: https          # REQUIRED - must bind to HTTPS listener, not just the gateway
  hostnames:
  - app.vanillax.me
  rules:
  - backendRefs:
    - name: app-service
      port: 8080

# httproute.yaml - INTERNAL (local network only, no Cloudflare)
# apiVersion: gateway.networking.k8s.io/v1
# kind: HTTPRoute
# metadata:
#   name: app-route
#   namespace: app-name
# spec:
#   parentRefs:
#   - kind: Gateway
#     name: gateway-internal
#     namespace: gateway
#   hostnames:
#   - app.vanillax.me
#   rules:
#   - backendRefs:
#     - name: app-service
#       port: 8080
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

### Deployment Strategy for Apps with PVCs

**CRITICAL**: Any Deployment that mounts a `ReadWriteOnce` PVC **must** use `strategy: type: Recreate`. The default `RollingUpdate` creates a deadlock — the new pod can't attach the RWO volume while the old pod still holds it, so the rollout hangs forever in `ContainerCreating`.

```yaml
# deployment.yaml
spec:
  strategy:
    type: Recreate    # REQUIRED for RWO PVCs - RollingUpdate causes Multi-Attach deadlock
  replicas: 1
```

### Jobs with ArgoCD Hooks (Migration/Setup Jobs)

**CRITICAL**: Kubernetes Jobs are immutable after creation. When Renovate bumps an image tag, ArgoCD can't apply the updated spec and sync fails with "field is immutable". All Jobs must have ArgoCD hook annotations.

**For standalone Job YAML files** (you control the manifest):
```yaml
# job.yaml
metadata:
  annotations:
    argocd.argoproj.io/hook: Sync
    argocd.argoproj.io/hook-delete-policy: BeforeHookCreation
    argocd.argoproj.io/sync-wave: "1"   # optional, controls ordering
```

**For Jobs rendered by Helm charts** (upstream chart, can't edit directly):
```yaml
# kustomization.yaml - add patches section
patches:
- target:
    kind: Job
  patch: |
    - op: add
      path: /metadata/annotations/argocd.argoproj.io~1hook
      value: Sync
    - op: add
      path: /metadata/annotations/argocd.argoproj.io~1hook-delete-policy
      value: BeforeHookCreation
```

`BeforeHookCreation` deletes the old Job before creating the new one, sidestepping immutability. Failed Jobs stay for debugging until the next sync.

**Do NOT use `Replace=true,Force=true`** — causes duplicate Job execution ([#24005](https://github.com/argoproj/argo-cd/issues/24005)).

### Application with Persistent Storage + Backups

Backups are declared **explicitly per PVC**: each backed-up PVC inlines its own
`ReplicationSource` and `ReplicationDestination`, and its `dataSourceRef`
points at that RD so PVC re-creation triggers the VolSync volume populator and
restores from the shared Kopia repo. There is no Kyverno generator, no
operator, no Helm chart — the YAML is the truth.

The shared repo Secret `volsync-kopia-repository` is produced in every
namespace labeled `volsync.backube/privileged-movers: "true"` by
`ClusterExternalSecret/volsync-kopia-repository` (see
`manifests/infra/volsync-backup-cluster/`). Add that label on the
namespace.

A `wait-for-rustfs` init container is auto-injected on every mover Job by
`MutatingAdmissionPolicy/volsync-mover-backend-availability`. Backups fail
fast (and Job-backoff-retry) if RustFS is unreachable.

Reference: `manifests/apps/media/jellyfin/pvc.yaml` (single-PVC), `manifests/apps/home/paperless-ngx/pvc.yaml`
(multi-PVC). Pattern:

```yaml
# namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: app-name
  labels:
    volsync.backube/privileged-movers: "true"   # REQUIRED — ClusterES selector

---
# pvc.yaml — PVC + RS + RD inlined as one doc per PVC
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: app-data
  namespace: app-name
  labels:
    app: app-name
    restore-policy: "strict"
  annotations:
    # ServerSideDiff dry-runs SSA; the apiserver rejects any change to
    # the immutable dataSourceRef on a Bound PVC and wedges sync. The
    # global Argo `ignoreDifferences` then masks the dataSource drift
    # normally. See docs/domains/argocd/argocd.md "Server-Side Diff & Apply Strategy".
    argocd.argoproj.io/compare-options: ServerSideDiff=false
spec:
  storageClassName: longhorn   # Required — needs volumesnapshot support
  accessModes:
  - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
  # Static dataSourceRef — VolSync's volume populator reads the latest
  # snapshot from the shared kopia repo on PVC re-creation (DR / namespace
  # recreate). No-op while the PVC is already Bound.
  dataSourceRef:
    apiGroup: volsync.backube
    kind: ReplicationDestination
    name: app-data-dst
---
apiVersion: volsync.backube/v1alpha1
kind: ReplicationSource
metadata:
  name: app-data
  namespace: app-name
spec:
  sourcePVC: app-data
  trigger:
    schedule: "33 2 * * *"   # pick a unique minute — avoid thundering herd
  kopia:
    repository: volsync-kopia-repository
    username: app-data            # convention: PVC name
    hostname: app-name            # convention: namespace
    compression: zstd-fastest
    parallelism: 2
    retain: { hourly: 24, daily: 7, weekly: 4, monthly: 2 }
    copyMethod: Snapshot
    storageClassName: longhorn
    volumeSnapshotClassName: longhorn-snapclass
    cacheCapacity: 2Gi
    moverSecurityContext: { runAsUser: 568, runAsGroup: 568, fsGroup: 568 }
---
apiVersion: volsync.backube/v1alpha1
kind: ReplicationDestination
metadata:
  name: app-data-dst
  namespace: app-name
spec:
  trigger:
    manual: restore-once          # static; only fires when value changes
  kopia:
    repository: volsync-kopia-repository
    username: app-data
    hostname: app-name
    sourceIdentity:
      sourceName: app-data
      sourceNamespace: app-name
      sourcePVCName: app-data
    copyMethod: Snapshot
    storageClassName: longhorn
    volumeSnapshotClassName: longhorn-snapclass
    cacheCapacity: 2Gi
    accessModes: [ReadWriteOnce]
    capacity: 10Gi               # MUST equal PVC requests.storage
    moverSecurityContext: { runAsUser: 568, runAsGroup: 568, fsGroup: 568 }
```

Verify after applying:
```
kubectl get replicationsource,replicationdestination,pvc -n app-name
kubectl get secret -n app-name volsync-kopia-repository   # produced by ClusterES
bash hack/volsync-status.sh   # cluster-wide RS/RD status
```

**When to back up a PVC**:
- User-generated content (photos, documents, uploads)
- Non-CNPG database volumes (Redis, SQLite, etc.)
- Configuration that's hard to recreate
- AI model caches (large downloads)

**When NOT to back up a PVC** — mark `backup-exempt: "true"` + annotation
`storage.vanillax.dev/backup-exempt-reason: "<reason>"` (the **fully-qualified**
key — bare `backup-exempt-reason` is silently ignored by CI guard):
- Temporary/cache data
- Data synced from external sources
- System namespaces (auto-excluded anyway)
- PVCs that will be frequently deleted/recreated
- **CNPG database PVCs** — these use Barman to S3, not VolSync

**Multi-PVC apps**: declare each PVC's triplet (PVC + RS + RD) explicitly in
its own document. There is no per-app abstraction. See
`manifests/apps/development/posthog/data-layer/{kafka,postgres,redis}.yaml` and
`manifests/apps/home/project-nomad/*/pvc.yaml` for examples.

**Helm-rendered PVCs**: the PVC manifest is owned by the chart; inject the
`ServerSideDiff=false` annotation and the `dataSourceRef` via Kustomize
`patches:` (see `manifests/apps/development/gitea/kustomization.yaml`), and put the
sibling RS/RD as `extraDeploy:` entries in the chart's values file (see
`manifests/apps/development/gitea/values.yaml`).

## Configuration Patterns

### Helm + Kustomize Pattern

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
```

### Component Reuse

```yaml
# kustomization.yaml
components:
- ../../common/deployment-defaults  # Applies revisionHistoryLimit: 2 to all Deployments
```

## Reference Examples

| Pattern | Location |
|---------|----------|
| **Minimal app** | `manifests/apps/development/nginx/` |
| **GPU workload** | `manifests/apps/ai/comfyui/` |
| **Complex app with storage** | `manifests/apps/media/immich/` |
| **PVC with automatic backup** | `manifests/apps/home/project-zomboid/pvc.yaml` (see `zomboid-data`) |
| **Helm + Kustomize** | `manifests/infra/1passwordconnect/` |
| **Secret management** | Any app with `externalsecret.yaml` |
| **Job with ArgoCD hooks** | `manifests/apps/development/posthog/core/jobs.yaml` |
| **Helm Job patch** | `manifests/apps/development/temporal/kustomization.yaml` |
