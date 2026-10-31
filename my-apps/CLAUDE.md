# Application Guidelines

## Adding New Applications

Long-running Deployments and StatefulSets also get a co-located `vpa.yaml`.
List it in `kustomization.yaml`; use `InPlaceOrRecreate`, `minReplicas: 1`, and
`RequestsOnly`. CPU-utilization HPA targets use a memory-only VPA. Intentional
exceptions must be added with a reason to `scripts/vpa-exemptions.yaml`.

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

# 3. Open a PR - ArgoCD discovers the app after merge
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
#     name: gateway-internal-technitium
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

### Which StorageClass? (decide BEFORE writing the PVC)

Follow `.claude/commands/place-storage.md` for class, size and backup mode; measured numbers are in `docs/domains/storage/storage-tiers.md`.
Never put databases on network-attached block storage: the NVMe/TCP flash-pool experiment was not adopted, so database flash stays **local to the node**.

### Application with Persistent Storage + Backups

Follow `.claude/commands/add-backup.md` (kopiur stub, shared component, namespace label, PVC `dataSourceRef`, mover uid). Reference app: `my-apps/ai/open-webui/`.

- Restore-before-bind: on recreate the PVC stays `Pending` while the populator hydrates it. A new PVC with no snapshot binds **empty** and backs up forward (`onMissingSnapshot: Continue`), so confirm `kubectl -n <ns> get snapshot` shows one before relying on restore.
- Multi-PVC apps: one stub + `dataSourceRef` per PVC, mover uid per PVC (`my-apps/knowledge/_archive/project-nomad/`); backed-up and `backup-exempt` PVCs mix freely (`my-apps/home-automation/frigate/`).

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
