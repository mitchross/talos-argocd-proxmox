# Deployment Defaults Component

This Kustomize component automatically sets `revisionHistoryLimit: 2` on all Deployments and StatefulSets to prevent accumulation of old replica sets.

## Why This Matters

By default, Kubernetes keeps **10 old replica sets** for each Deployment/StatefulSet. Over time with frequent updates, this causes:
- Hundreds of unused replica sets cluttering your cluster
- Increased etcd storage usage
- Slower `kubectl get replicasets` commands
- Harder debugging (finding the right replica set in a sea of old ones)

Setting `revisionHistoryLimit: 2` keeps only 2 old replica sets, which is sufficient for emergency rollbacks while preventing clutter.

## Usage

### Option 1: Add to Existing Applications (Recommended)

In any application's `kustomization.yaml`, add the component:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

# Add this line at the top
components:
  - ../../common/deployment-defaults

resources:
  - deployment.yaml
  - service.yaml
  # ... rest of your resources
```

### Option 2: Use as Base for New Applications

When creating new apps, structure them to use this component by default:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: my-app

components:
  - ../../common/deployment-defaults  # Automatically applies revision history limits

resources:
  - namespace.yaml
  - deployment.yaml
  - service.yaml
```

### Option 3: Override for Specific Apps

If you need a different limit (e.g., for critical apps that need more rollback history):

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

components:
  - ../../common/deployment-defaults  # Sets to 2 by default

patchesJson6902:
  - target:
      kind: Deployment
      name: critical-app
    patch: |-
      - op: replace
        path: /spec/revisionHistoryLimit
        value: 5  # Override to keep more history
```

## How It Works

This uses Kustomize's **component** feature (think of it like a mixin):
1. Component defines JSON patches targeting ALL Deployments/StatefulSets
2. When included in a `kustomization.yaml`, it applies the patches
3. Works with both existing manifests and Helm charts
4. ArgoCD automatically picks it up during sync

## Cleanup Existing Replica Sets

After enabling this component, existing accumulated replica sets won't be deleted automatically. Run this one-time cleanup:

```bash
# Delete all replica sets with 0 replicas (safe - these are unused)
kubectl get replicasets --all-namespaces -o json | \
  jq -r '.items[] | select(.spec.replicas==0) | "\(.metadata.namespace) \(.metadata.name)"' | \
  xargs -n2 sh -c 'kubectl delete replicaset -n $0 $1'
```

Or use the provided script: `scripts/cleanup-old-replicasets.sh`

## Best Practices

✅ **Do**: Use this component for all standard applications
✅ **Do**: Override with higher limits (3-5) for critical production services
✅ **Do**: Run periodic cleanup scripts for accumulated replica sets
❌ **Don't**: Set to 0 (disables rollback capability entirely)
❌ **Don't**: Set above 10 (defeats the purpose of cleanup)

## Related Configuration

This component only affects Kubernetes replica set retention. For ArgoCD's own application history:

```yaml
# In ArgoCD Application/ApplicationSet
spec:
  revisionHistoryLimit: 5  # Controls ArgoCD's Git revision history
```

This is separate and controls how many ArgoCD application revisions to keep in etcd.

## Troubleshooting

**Problem**: Component not applying to Helm charts

**Solution**: Ensure the component is listed before the Helm chart inflation:

```yaml
components:
  - ../../common/deployment-defaults

helmCharts:
  - name: my-chart
    repo: https://...
```

**Problem**: Seeing `op: add` error about existing path

**Solution**: Some deployments might already have `revisionHistoryLimit` set. The component will fail gracefully and leave existing values unchanged.

## Migration Path

To roll this out globally:

1. **Test**: Apply to 1-2 non-critical apps first
2. **Cleanup**: Run replica set cleanup script
3. **Rollout**: Add component to all apps in phases (by category)
4. **Monitor**: Check that deployments still rollback correctly
5. **Maintain**: Include in all new app templates
