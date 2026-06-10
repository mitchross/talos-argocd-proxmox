# Application Guidelines

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

Backups are declared **per PVC via labels**; the **pvc-plumber v4 operator**
(permissive mode, no admission webhook) owns the `ReplicationSource` /
`ReplicationDestination` wiring. You declare intent on the namespace + PVC;
the operator creates and repairs RS/RD; VolSync/Kopia move bytes. **Never
create, edit, or delete RS/RD by hand for managed PVCs** — reconcile through
the labels. Full workflow: `.claude/commands/add-backup.md`.

The shared repo Secret `volsync-kopia-repository` is produced in every
namespace labeled `volsync.backube/privileged-movers: "true"` by
`ClusterExternalSecret/volsync-kopia-repository` (see
`infrastructure/storage/volsync-backup-cluster/`).

A `wait-for-rustfs` init container is auto-injected on every mover Job by
`MutatingAdmissionPolicy/volsync-mover-backend-availability`. Backups fail
fast (and Job-backoff-retry) if RustFS is unreachable.

Reference: `my-apps/development/nginx/` (plain PVC),
`my-apps/system/restore-canary/` (tier=manual + drill),
`my-apps/development/gitea/kustomization.yaml` (Helm-rendered PVC). Pattern:

```yaml
# namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: app-name
  labels:
    volsync.backube/privileged-movers: "true"   # REQUIRED — ClusterES secret fanout
    pvc-plumber.io/managed-namespace: "true"    # REQUIRED — operator write gate

---
# pvc.yaml — labels + dataSourceRef only; the operator renders RS/RD
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: app-data
  namespace: app-name
  labels:
    app.kubernetes.io/name: app-name
    pvc-plumber.io/enabled: "true"          # opt-in fuse (1 of 2)
    pvc-plumber.io/manage-volsync: "true"   # write fuse (2 of 2)
    pvc-plumber.io/tier: "daily"            # hourly|daily|weekly|manual|disabled
    restore-policy: "strict"
  annotations:
    # ServerSideDiff dry-runs SSA; the apiserver rejects any change to
    # the immutable dataSourceRef on a Bound PVC and wedges sync. The
    # global Argo `ignoreDifferences` then masks the dataSource drift
    # normally. See docs/domains/argocd/argocd.md "Server-Side Diff & Apply Strategy".
    argocd.argoproj.io/compare-options: ServerSideDiff=false
    argocd.argoproj.io/sync-options: ServerSideApply=false
spec:
  storageClassName: longhorn   # Required — needs volumesnapshot support
  accessModes:
  - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
  # Static dataSourceRef → <pvc-name>-dst. On PVC re-creation (DR /
  # namespace recreate) the VolSync volume populator restores from the
  # operator-managed RD's latestImage. No-op while the PVC is Bound.
  dataSourceRef:
    apiGroup: volsync.backube
    kind: ReplicationDestination
    name: app-data-dst
```

The operator renders the RS (schedule minute derived from a hash of
`namespace/pvc` — no thundering herd) and the RD
(`trigger.manual: restore-once`), both labeled
`app.kubernetes.io/managed-by: pvc-plumber`. `tier=manual` renders
`trigger.manual: backup-on-demand` — trigger a backup by changing that
string.

> **Day-one caveat**: a brand-new PVC shipping `dataSourceRef` sits
> `Pending` until the RD's first sync, then binds **EMPTY** — the Kopia
> mover no-ops successfully on an identity with no snapshots, so the
> populator happily consumes an empty `latestImage` (verified live
> 2026-06-10). A `dataSourceRef` alone is no guarantee of restored content.
> Preferred bootstrap: pre-create the PVC without `dataSourceRef`, seed the
> first backup, let the first delete→recreate install it. See
> `docs/restore-canary.md` "First-deploy bootstrap".

Verify after applying:
```
kubectl get replicationsource,replicationdestination,pvc -n app-name
kubectl get secret -n app-name volsync-kopia-repository   # produced by ClusterES
kubectl get --raw "/api/v1/namespaces/pvc-plumber/services/pvc-plumber-metrics:audit-http/proxy/audit" \
  | python3 -m json.tool | less   # entry should be action=already-matches
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

**Multi-PVC apps**: each PVC carries its own fuse labels + `dataSourceRef`;
there is no per-app abstraction. Mix freely — e.g.
`my-apps/home/project-zomboid/pvc.yaml` backs up `zomboid-data` and leaves
`zomboid-server-files` unlabeled.

**Helm-rendered PVCs**: the PVC manifest is owned by the chart; inject the
fuse labels, the `ServerSideDiff=false` annotation, and the `dataSourceRef`
via Kustomize `patches:` (see `my-apps/development/gitea/kustomization.yaml`).
Do NOT add RS/RD as `extraDeploy:` chart values — the operator owns RS/RD
(gitea's inline pair was removed in the 2026-05-31 DRY handoff).

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
| **Minimal app** | `my-apps/development/nginx/` |
| **GPU workload** | `my-apps/ai/comfyui/` |
| **Complex app with storage** | `my-apps/media/immich/` |
| **PVC with automatic backup** | `my-apps/home/project-zomboid/pvc.yaml` (see `zomboid-data`) |
| **Restore canary (DR drill)** | `my-apps/system/restore-canary/` + `docs/restore-canary.md` |
| **Helm + Kustomize** | `infrastructure/controllers/1passwordconnect/` |
| **Secret management** | Any app with `externalsecret.yaml` |
| **Job with ArgoCD hooks** | `my-apps/development/posthog/core/jobs.yaml` |
| **Helm Job patch** | `my-apps/development/temporal/kustomization.yaml` |
