---
applies_to:
  - "infrastructure/controllers/argocd/**"
  - "**/applicationset*"
  - "**/application*"
---

# ArgoCD GitOps Instructions

## Self-Managing ArgoCD Architecture

This cluster uses a "self-managing" ArgoCD pattern where ArgoCD manages its own configuration through Git.

### Bootstrap Flow
1. **Manual Bootstrap**: Apply ArgoCD Helm chart via Kustomize
2. **Root Application**: Points ArgoCD to its own configuration directory
3. **ApplicationSets**: Auto-discover applications by directory scanning
4. **Application Generation**: Create ArgoCD Applications for each discovered directory

### Root Application Pattern
The `infrastructure/controllers/argocd/root.yaml` is the entry point:
```yaml
spec:
  source:
    path: infrastructure/controllers/argocd/apps  # Points to ArgoCD config
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

## ApplicationSet Strategy

### Three-Tier Application Discovery
1. **Infrastructure** (`infrastructure-appset.yaml`):
   - Paths: `infrastructure/controllers/*`, `infrastructure/storage/*`, etc.
   - Sync wave: "1" (after ArgoCD, before apps)
   - Creates core cluster services

2. **Monitoring** (`monitoring-appset.yaml`):
   - Paths: `monitoring/*`
   - Sync wave: "0" (early deployment)
   - Creates observability stack

3. **Applications** (`my-apps-appset.yaml`):
   - Paths: `my-apps/*/*` (nested directories)
   - Sync wave: "2" (after infrastructure)
   - Creates user applications

### Directory-Based Discovery
ApplicationSets use `git.directories` generator:
```yaml
generators:
  - git:
      directories:
        - path: my-apps/*/*  # Scans for any nested directory
```

**Key Rule**: Every discovered directory MUST contain `kustomization.yaml`

## Application Template Patterns

### Namespace Strategy
```yaml
template:
  spec:
    destination:
      namespace: '{{path.basename}}'  # Directory name = namespace
    syncPolicy:
      syncOptions:
        - CreateNamespace=true  # Auto-create namespaces
```

### Sync Options
Standard sync options for all applications:
- `CreateNamespace=true`: Auto-create target namespaces
- `ServerSideApply=true`: Use server-side apply for better conflict resolution
- `RespectIgnoreDifferences=true`: Honor ignoreDifferences configurations
- `ApplyOutOfSyncOnly=true`: Only apply resources that are out of sync

### Retry Strategy
```yaml
retry:
  limit: 5
  backoff:
    duration: 5s
    factor: 2
    maxDuration: 3m
```

## Sync Waves and Dependencies

### Wave Ordering
- Wave "0": Monitoring stack (Prometheus, Grafana)
- Wave "1": Infrastructure (Cilium, Longhorn, cert-manager)
- Wave "2": Applications (user workloads)

### CRD Handling
For infrastructure components that install CRDs:
```yaml
ignoreDifferences:
  - group: apiextensions.k8s.io
    kind: CustomResourceDefinition
    jsonPointers:
      - /spec/preserveUnknownFields
```

## Project Structure for GitOps

### ArgoCD Project Separation
- `infrastructure`: For cluster-level services
- `monitoring`: For observability components  
- `my-apps`: For user applications

### Required Files per Application
```
app-directory/
├── kustomization.yaml    # REQUIRED - defines resources
├── namespace.yaml        # REQUIRED - creates namespace
├── deployment.yaml       # Application workload
├── service.yaml         # Service definition
└── values.yaml          # If using Helm
```

## Helm Integration with ArgoCD

### Kustomize + Helm Pattern
Use Kustomize's `helmCharts` field in `kustomization.yaml`:
```yaml
helmCharts:
  - name: chart-name
    repo: https://charts.example.com
    version: 1.0.0
    releaseName: release-name
    valuesFile: values.yaml
    includeCRDs: true
```

### Patching Helm Resources
After Helm rendering, use Kustomize patches:
```yaml
# kustomization.yaml
patchesStrategicMerge:
  - patches/deployment-patch.yaml

# patches/deployment-patch.yaml  
apiVersion: apps/v1
kind: Deployment
metadata:
  name: app-name
spec:
  template:
    spec:
      nodeSelector:
        feature.node.kubernetes.io/pci-0300_10de.present: "true"
```

## Bootstrap and Troubleshooting

### Critical Bootstrap Sequence
```bash
# 1. Deploy ArgoCD with Helm via Kustomize
kustomize build infrastructure/controllers/argocd --enable-helm | kubectl apply -f -

# 2. Wait for CRDs (critical - race condition without this)
kubectl wait --for condition=established --timeout=60s crd/applications.argoproj.io

# 3. Wait for ArgoCD server
kubectl wait --for=condition=Available deployment/argocd-server -n argocd --timeout=300s

# 4. Apply root application
kubectl apply -f infrastructure/controllers/argocd/root.yaml
```

### Emergency Recovery
```bash
# Remove finalizers from stuck applications
kubectl get applications -n argocd -o name | xargs -I{} kubectl patch {} -n argocd --type json -p '[{"op": "remove","path": "/metadata/finalizers"}]'

# Delete all applications
kubectl delete applications --all -n argocd

# Remove finalizers from ApplicationSets
kubectl get applicationsets -n argocd -o name | xargs -I{} kubectl patch {} -n argocd --type json -p '[{"op": "remove","path": "/metadata/finalizers"}]'
```

### Debugging ApplicationSets
```bash
# Check ApplicationSet status
kubectl get applicationsets -n argocd
kubectl describe applicationset infrastructure -n argocd

# View generated applications
kubectl get applications -n argocd

# Check specific application
kubectl describe application <app-name> -n argocd
```

## Best Practices

### Application Discovery
- ✅ Use directory structure to organize applications
- ✅ Every directory must have `kustomization.yaml`
- ✅ Use meaningful directory names (they become application names)
- ❌ Don't create manual Application resources

### Sync Policies
- ✅ Use automated sync with prune and selfHeal
- ✅ Set appropriate sync waves for dependencies
- ✅ Use server-side apply for complex resources
- ❌ Don't disable automated sync without good reason

### Resource Management
- ✅ Use ignoreDifferences for known noisy fields
- ✅ Set resource limits and requests
- ✅ Use proper labels and annotations
- ❌ Don't bypass ArgoCD for manual kubectl apply

## Integration Points

### With Talos OS
- ArgoCD manages cluster configuration post-bootstrap
- No direct Talos resource management (use talosctl)
- Cluster-level services only (not node configuration)

### With External Secrets
- ArgoCD applications can reference ExternalSecrets
- Secrets are created automatically by External Secrets Operator
- No need to manage Kubernetes Secrets directly

### With Gateway API
- Applications expose services via HTTPRoute
- Gateway configuration managed by ArgoCD
- Service naming critical for HTTPRoute discovery