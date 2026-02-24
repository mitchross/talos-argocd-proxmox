# VPA Resource Optimization Guide

How to use VPA, Goldilocks, and Kyverno to right-size Kubernetes resource requests based on actual workload behavior.

## The Toolchain

| Tool | What It Does | Location |
|------|-------------|----------|
| **metrics-server** | Provides `metrics.k8s.io` API (CPU/memory data from kubelet) | `infrastructure/controllers/metrics-server/` |
| **VPA** (Vertical Pod Autoscaler) | Analyzes metrics, generates resource recommendations | `infrastructure/controllers/vertical-pod-autoscaler/` |
| **Kyverno Policy** (`vpa-auto-create`) | Auto-generates a VPA resource for every Deployment and StatefulSet | `infrastructure/controllers/kyverno/policies/vpa-auto-create.yaml` |
| **Goldilocks** | Web dashboard to visualize VPA recommendations per namespace | `infrastructure/controllers/goldilocks/` |

### How They Fit Together

```
kubelet /metrics/resource
    |
    v
metrics-server (provides metrics.k8s.io API)
    |
    v
VPA Recommender (reads metrics, writes recommendations to VPA status)
    ^
    |
Kyverno generate policy (auto-creates VPA for every Deployment/StatefulSet)
    |
    v
VPA resources (one per workload, updateMode: "Off")
    |
    v
Goldilocks Dashboard (reads VPA recommendations, shows per-namespace view)
    |
    v
Human reviews → updates values.yaml → Git push → ArgoCD applies
```

**Key point**: Kyverno creates VPAs for ALL workloads automatically. Goldilocks also creates VPAs for namespaces it scans, but since `on-by-default: "true"` is set, both cover all namespaces. Duplicate VPAs are harmless — they share the same name and Kyverno's `synchronize: true` keeps them in sync.

## Accessing the Dashboard

**Goldilocks Dashboard**: https://goldilocks.vanillax.me

This is routed via the internal gateway (`gateway-internal`). No port-forward needed if you're on the LAN.

Fallback (if gateway is down):
```bash
kubectl port-forward -n goldilocks svc/goldilocks-dashboard 8080:80
# Open http://localhost:8080
```

The dashboard shows every namespace with VPA-enabled workloads. For each container it displays:
- Current resource requests/limits
- VPA lower bound, target, and upper bound
- Suggested `requests` and `limits` YAML you can copy-paste

## Reading VPA Recommendations

### Via kubectl

```bash
# Quick overview: all VPA targets across the cluster
kubectl get vpa -A -o custom-columns=\
NAMESPACE:.metadata.namespace,\
NAME:.metadata.name,\
CPU:.status.recommendation.containerRecommendations[0].target.cpu,\
MEM:.status.recommendation.containerRecommendations[0].target.memory

# Detailed view for a specific namespace
kubectl get vpa -n argocd -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{range .status.recommendation.containerRecommendations[*]}{"  "}{.containerName}{": cpu="}{.target.cpu}{" mem="}{.target.memory}{"\n"}{end}{end}'

# Full detail for a specific VPA
kubectl describe vpa <name> -n <namespace>
```

### Understanding the Four Values

VPA recommendations include four values per container:

| Value | Meaning | Use For |
|-------|---------|---------|
| **lowerBound** | Minimum to avoid throttling/OOM | Red flag if current request is below this |
| **target** | Optimal request based on observed usage | Set `requests:` to this value |
| **upperBound** | Peak observed consumption | Informs `limits:` setting |
| **uncappedTarget** | Ideal ignoring any VPA min/max constraints | Same as target when no constraints are set |

**Memory values** are in bytes. Quick conversions:
- `104857600` = 100Mi
- `268435456` = 256Mi
- `536870912` = 512Mi
- `1073741824` = 1Gi
- `1610612736` = 1.5Gi

## When to Change Resources

### Decision Matrix

| Situation | Action | Priority |
|-----------|--------|----------|
| Current request < **lowerBound** | **INCREASE NOW** | Pod is being throttled or OOM-killed |
| Current request < **target** | **INCREASE** | Under-provisioned, degraded performance |
| Current request within 20% of **target** | **KEEP** | Already well-tuned |
| Current request > 1.5x **target** | **DECREASE** | Over-provisioned, wasting resources |
| Current request > 5x **target** | **DECREASE** | Heavily over-provisioned |

### Timing

- **Wait at least 7 days** before trusting VPA numbers. Initial recommendations are noisy.
- **Review weekly**, not daily. Over-correcting defeats the purpose.
- **Re-check after major changes** (new features, traffic spikes, version upgrades). VPA is backward-looking.
- **Upper bounds stabilize over ~14 days**. They'll be very wide initially.

### How to Apply Changes

1. Read the VPA recommendation (Goldilocks dashboard or kubectl)
2. Update the app's `values.yaml` with new resource requests
3. Add a comment documenting the VPA data and reasoning:

```yaml
# VPA-optimized (YYYY-MM-DD)
# VPA target: cpu Xm, memory Y
# Previous: cpu Am (reason for change)
resources:
  requests:
    cpu: Xm      # Match VPA target
    memory: Y    # Match VPA target + buffer
  limits:
    cpu: 2Xm     # 2x request for burst
    memory: 2Y   # 2x request for spikes
```

4. Git commit and push — ArgoCD applies via GitOps

### Setting Requests vs Limits

| Field | Rule of Thumb |
|-------|--------------|
| `requests.cpu` | VPA `target` (or 1.1-1.2x for buffer) |
| `requests.memory` | VPA `target` (or 1.2-1.5x — memory OOM is fatal, CPU throttling is not) |
| `limits.cpu` | 2-4x request (allows burst). Or omit entirely to let pods burst freely. |
| `limits.memory` | 2-4x request (or match VPA `upperBound` if spikes are expected) |

## Common Workload Patterns

### CPU-Bound (Helm rendering, image processing)
High CPU target, low memory target. Increase CPU generously, keep memory modest.
```
Example: argocd-repo-server
  VPA target: cpu 2975m, memory 523Mi
  Action: cpu 3000m request, memory 768Mi request
```

### Memory-Bound (Databases, caches)
Low CPU target, high memory target. Increase memory, keep CPU low.
```
Example: Redis
  VPA target: cpu 23m, memory 100Mi
  Action: cpu 50m request, memory 128Mi request
```

### Idle/Lightweight (UI servers, webhooks)
Both CPU and memory very low. Set modest requests with generous limits for occasional spikes.
```
Example: argocd-server
  VPA target: cpu 23m, memory 175Mi
  Action: cpu 50m request, memory 256Mi request
```

### GPU Workloads
VPA only tracks CPU/memory, not GPU. Recommendations will show low CPU/memory because compute happens on GPU VRAM. Set CPU/memory based on data loading needs, not inference.

## Real-World Example: ArgoCD Optimization

### Before (manual guesswork)
```
controller:     cpu: 1000m, memory: 1Gi    # UNDER-PROVISIONED (below lowerBound!)
repo-server:    cpu: 1000m, memory: 1Gi    # UNDER-PROVISIONED 3x
server:         cpu: 500m,  memory: 512Mi  # OVER-PROVISIONED 20x
applicationSet: cpu: 250m,  memory: 256Mi  # OVER-PROVISIONED 5x
redis:          cpu: 100m,  memory: 128Mi  # OVER-PROVISIONED 4x
Total: 2.85 CPU, 2.9Gi memory
```

### VPA Said
```
controller:     target: 2048m CPU, 1.25Gi memory  (lowerBound: 1021m > current 1000m!)
repo-server:    target: 2975m CPU, 523Mi memory
server:         target: 23m CPU, 175Mi memory
applicationSet: target: 49m CPU, 100Mi memory
redis:          target: 23m CPU, 100Mi memory
```

### After (VPA-optimized)
```
controller:     cpu: 2000m, memory: 1536Mi  # DOUBLED (was throttled)
repo-server:    cpu: 3000m, memory: 768Mi   # TRIPLED CPU, halved memory
server:         cpu: 50m,   memory: 256Mi   # REDUCED 10x
applicationSet: cpu: 100m,  memory: 128Mi   # REDUCED 2.5x
redis:          cpu: 50m,   memory: 128Mi   # REDUCED 2x
Total: 5.2 CPU, 2.8Gi memory
```

**Result**: +2.35 CPU where it was needed (controller/repo-server), -0.1Gi memory overall, no more CPU throttling on the controller.

See `infrastructure/controllers/argocd/values.yaml` for the actual implementation with inline VPA documentation.

## Excluded Namespaces

The Kyverno `vpa-auto-create` policy excludes:
- `kube-system` — critical system components, don't touch
- `kyverno` — policy engine, restart = cluster-wide impact
- `vertical-pod-autoscaler` — VPA managing itself creates feedback loops

## K8s 1.35: In-Place Pod Resize (Future)

This cluster runs K8s v1.35.1 where In-Place Pod Resize is GA. VPA supports `updateMode: "InPlaceOrRecreate"` which resizes pods **without restarting them** when possible.

Currently we use `updateMode: "Off"` (manual review). When confident in VPA accuracy after 2-4 weeks of observation, you can switch individual workloads to `InPlaceOrRecreate`:

```yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
spec:
  updatePolicy:
    updateMode: "InPlaceOrRecreate"  # Live resize when possible
```

**Start with non-critical workloads** (dev tools, media apps) before enabling on infrastructure.

## Troubleshooting

### No recommendations showing
- VPA needs ~5-10 minutes for initial data, 24+ hours for accuracy
- Check metrics-server: `kubectl top nodes` (should return data)
- Check VPA recommender: `kubectl logs -n vertical-pod-autoscaler -l app.kubernetes.io/component=recommender`

### Goldilocks dashboard is empty
- Check if Goldilocks controller is running: `kubectl get pods -n goldilocks`
- Goldilocks is set to `on-by-default: "true"` — all namespaces should appear
- VPA resources must exist (Kyverno creates them on Deployment/StatefulSet CREATE/UPDATE)

### VPA recommendations seem too high/low
- Not enough data — wait 7-14 days
- Workload changed recently — VPA is backward-looking
- Check `upperBound` for peak usage context
- Batch/cron workloads have spiky usage — use `upperBound` for limits

### Pods OOMKilled after applying VPA
- VPA target reflects steady-state, not initialization spikes
- Set `limits.memory` well above `requests.memory` (2-4x)
- Check startup memory with `kubectl top pod` during pod init

## Quick Reference

```bash
# Goldilocks dashboard (LAN)
https://goldilocks.vanillax.me

# All VPA recommendations (cluster-wide)
kubectl get vpa -A -o custom-columns=\
NS:.metadata.namespace,\
NAME:.metadata.name,\
CPU:.status.recommendation.containerRecommendations[0].target.cpu,\
MEM:.status.recommendation.containerRecommendations[0].target.memory

# Current resource usage vs requests
kubectl top pods -n <namespace>

# Compare current requests vs VPA target
kubectl get deploy <name> -n <ns> -o jsonpath='{.spec.template.spec.containers[0].resources}'
kubectl get vpa <name> -n <ns> -o jsonpath='{.status.recommendation.containerRecommendations[0].target}'
```

## Related Docs

- [Monitoring README](../monitoring/README.md) — metrics-server vs Prometheus pipelines
- [VPA component README](../infrastructure/controllers/vertical-pod-autoscaler/README.md)
- [Kyverno VPA policy](../infrastructure/controllers/kyverno/policies/vpa-auto-create.yaml)
- [Goldilocks config](../infrastructure/controllers/goldilocks/)

---

**Last Updated**: 2026-02-24
**Cluster**: talos-prod-cluster (K8s v1.35.1, Talos v1.12.4)
