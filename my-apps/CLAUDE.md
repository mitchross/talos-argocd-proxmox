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

Backups are **kopiur** (home-operations' Kopia-native operator). It replaced
pvc-plumber + VolSync (retired 2026-06-27). You declare per-PVC backup intent
with a small Kustomize stub + the shared `kopiur-backup` component; kopiur owns
the `SnapshotPolicy` / `SnapshotSchedule` / `Restore` reconcile and the
`Snapshot` Jobs; kopia moves bytes to the dedicated RustFS bucket
(`s3://kopiur`). Full workflow: `.claude/commands/add-backup.md`.
**Reference app: `my-apps/ai/open-webui/`** (component + `kopiur/storage.yaml`).

**Four pieces per backed-up app:**

**1. Namespace** — one label (drives the ESO credential fan-out AND
ClusterRepository tenancy). Add the privileged-movers annotation ONLY if the
PVC's data is root-owned (its mover then runs as uid 0):
```yaml
# namespace.yaml
metadata:
  name: app-name
  labels:
    kopiur.home-operations.com/repo: cluster-kopia      # REQUIRED — creds + repo tenancy
  # annotations:                                         # ONLY for root-owned data
  #   kopiur.home-operations.com/privileged-movers: "true"
```

**2. Kustomization** — pull in the component + the per-PVC stub:
```yaml
resources:
  - kopiur/app-data.yaml
components:
  - ../../common/kopiur-backup   # injects repository, copyMethod, populator, schedule defaults
```

**3. Per-PVC stub** (`kopiur/app-data.yaml`) — only the VARYING bits. The
**mover MUST run as the DATA OWNER uid:gid**: under baseline Pod Security the
mover runs `capabilities: drop:[ALL]` and kopiur's `privilegedMode` adds none,
so a root mover **cannot** read non-root / mode-600/700 data. Find the owner:
`kubectl -n <ns> exec <pod> -- stat -c '%u:%g' <data-mountpath>`.
(Full plain-English + technical why: `docs/domains/storage/kopiur-mover-permissions.md`.)
```yaml
---
apiVersion: kopiur.home-operations.com/v1alpha1
kind: SnapshotPolicy
metadata: { name: app-data, namespace: app-name }
spec:
  sources: [{ pvc: { name: app-data } }]
  identity: { username: app-data, hostname: app-name }
  retention: { keepDaily: 14, keepWeekly: 6, keepMonthly: 3 }   # hourly tier: keepHourly:24,keepDaily:7,keepWeekly:4
  mover:                          # <-- run as the DATA owner (example uid 1000)
    securityContext: { runAsUser: 1000, runAsGroup: 1000, runAsNonRoot: true }
    podSecurityContext: { fsGroup: 1000, supplementalGroups: [1000] }
---
apiVersion: kopiur.home-operations.com/v1alpha1
kind: SnapshotSchedule
metadata: { name: app-data-daily, namespace: app-name }
spec: { policyRef: { name: app-data }, schedule: { cron: "MM 3 * * *" } }   # distinct minute vs ALL schedules incl. hourly "MM * * * *" tiers (hourly :MM collides with daily 03:MM)
---
apiVersion: kopiur.home-operations.com/v1alpha1
kind: Restore
metadata: { name: app-data-restore, namespace: app-name }
spec:
  source: { fromPolicy: { name: app-data, offset: 0 } }
  mover:                          # same data-owner uid (no consumer pod during a cold restore)
    securityContext: { runAsUser: 1000, runAsGroup: 1000, runAsNonRoot: true }
    podSecurityContext: { fsGroup: 1000, supplementalGroups: [1000] }
```
For **root-owned** data use `securityContext: { runAsUser: 0, runAsNonRoot: false }`
(no podSecurityContext needed) AND add the namespace privileged-movers annotation.
The component injects `repository: cluster-kopia`, `copyMethod: Snapshot`,
`volumeSnapshotClassName: longhorn-snapclass`, `target.populator: {}`,
`policy.onMissingSnapshot: Continue`, `concurrencyPolicy: Forbid`,
`runOnCreate: false` — do NOT duplicate those in the stub.

**4. The PVC** — point `dataSourceRef` at the Restore (restore-before-bind) and
keep the immutable-dataSourceRef masking annotations:
```yaml
metadata:
  annotations:
    # immutable dataSourceRef on a Bound PVC — mask the SSA dry-run diff;
    # the AppSet ignoreDifferences handles the live compare.
    argocd.argoproj.io/compare-options: ServerSideDiff=false
    argocd.argoproj.io/sync-options: ServerSideApply=false
spec:
  storageClassName: longhorn      # needs CSI VolumeSnapshot
  dataSourceRef:
    apiGroup: kopiur.home-operations.com
    kind: Restore
    name: app-data-restore
```

**Restore-before-bind semantics:** on recreate the PVC sits `Pending` while the
`Restore` populator hydrates it from the latest snapshot, then binds WITH data.
A brand-new PVC with no snapshot yet binds **empty** and backs up forward
(`onMissingSnapshot: Continue` = deploy-or-restore) — so ensure a `Snapshot`
exists (`kubectl -n <ns> get snapshot`) before relying on restore. If the **repo
is unreachable**, the restore errors and the PVC stays `Pending` — it never binds
empty (source-verified; kopiur propagates the backend error before the
onMissingSnapshot decision, preserving the old `wait-for-rustfs` MAP's guarantee).

Verify after applying:
```
kubectl -n app-name get snapshotpolicy,snapshotschedule,restore
kubectl -n app-name get secret kopiur-rustfs     # fanned in by the ClusterExternalSecret
kubectl -n app-name get snapshot                 # Completed with non-zero files after first run
```

**When NOT to back up a PVC** — label `backup-exempt: "true"` + annotation
`storage.vanillax.dev/backup-exempt-reason: "<reason>"` (the **fully-qualified**
key — bare `backup-exempt-reason` is silently ignored by the CI guard):
temporary/cache data, externally-synced data, frequently-recreated PVCs,
**CNPG database PVCs** (Barman to S3, never kopiur), PostHog/Redis (disposable).

**Multi-PVC apps**: each PVC gets its own stub + `dataSourceRef`; the mover uid
is per-PVC (e.g. `my-apps/home/project-nomad/` runs `1000` / `999:568` / `568`
in one namespace). Mix backed-up and `backup-exempt` freely — e.g.
`my-apps/home/project-zomboid/` backs up `zomboid-data`, exempts `zomboid-server-files`.

**Helm-rendered PVCs**: the chart owns the PVC manifest — inject the
`dataSourceRef` + masking annotations via a Kustomize `patches:` block targeting
the chart PVC; the per-PVC stub + the component go in the app kustomization (see
`my-apps/development/gitea/`). Do NOT add backup objects as `extraDeploy:` chart values.

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
| **Minimal app** | template in `my-apps/CLAUDE.md` § "Minimal Application" (no live example is truly minimal) |
| **Backup with root-uid mover** | `my-apps/development/nginx/` (root-owned data: `runAsUser: 0` stub + `privileged-movers` namespace annotation) |
| **GPU workload** | `my-apps/ai/comfyui/` |
| **Complex app with storage** | `my-apps/media/immich/` |
| **PVC with automatic backup** | `my-apps/home/project-zomboid/pvc.yaml` (see `zomboid-data`) |
| **Restore canary (DR drill)** | `my-apps/system/restore-canary/` + `docs/disaster-recovery.md` |
| **Helm + Kustomize** | `infrastructure/controllers/1passwordconnect/` |
| **Secret management** | Any app with `externalsecret.yaml` |
| **Job with ArgoCD hooks** | `my-apps/development/posthog/core/jobs.yaml` |
| **Helm Job patch** | `my-apps/development/temporal/kustomization.yaml` |
