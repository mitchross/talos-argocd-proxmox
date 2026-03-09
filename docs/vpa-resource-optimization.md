# VPA Resource Optimization Guide

How to use VPA to right-size Kubernetes resource requests based on actual workload behavior.

## TL;DR — Just Tell Me What To Do

**Everything is automatic.** A Kyverno ClusterPolicy auto-creates VPA resources for every workload in the cluster. Infrastructure/monitoring namespaces get `updateMode: "Off"` (recommend only). User app namespaces get `updateMode: "InPlaceOrRecreate"` (auto-tuning with in-place pod resize).

### Step 1: Check recommendations

```bash
# Human-readable VPA report
./scripts/vpa-report.sh

# Filter to one namespace
./scripts/vpa-report.sh argocd

# Or raw kubectl one-liner
kubectl get vpa -A -o custom-columns=\
NS:.metadata.namespace,\
NAME:.metadata.name,\
CPU:.status.recommendation.containerRecommendations[0].target.cpu,\
MEM:.status.recommendation.containerRecommendations[0].target.memory
```

### Step 2: Open Grafana VPA dashboard

Go to **https://grafana.vanillax.me** and search for "VPA". The dashboard shows time-series graphs of VPA recommendations with historical trends.

### Step 3: Look for problems

Look for:
- **Current request way below "Target"** = pod is starved, increase it
- **Current request way above "Target"** = wasting resources, decrease it
- **Current request below "Lower Bound"** = pod is actively throttled, fix ASAP

### Step 4: Apply changes (infrastructure only)

Infrastructure namespaces use `updateMode: "Off"` — edit the app's `values.yaml` in Git, update the `resources:` block, push, ArgoCD applies it. Add a comment explaining why:

```yaml
# VPA-optimized (2026-02-28) — target was 2000m, previous 500m
resources:
  requests:
    cpu: 2000m
    memory: 1Gi
```

User app namespaces use `updateMode: "InPlaceOrRecreate"` — VPA automatically adjusts resources via in-place pod resize (K8s 1.35 GA). No manual intervention needed.

### Step 5: Wait and re-check

VPA recommendations update continuously. Check back in a week to see if the new values are good. Don't change things daily.

---

## Architecture

```
kubelet /metrics/resource
    │
    ▼
metrics-server (provides metrics.k8s.io API)
    │
    ▼
VPA Recommender (reads metrics, writes recommendations to VPA .status)
    ▲
    │
Kyverno ClusterPolicy (vpa-auto-generate)
    │  • watches Deployments, StatefulSets, DaemonSets
    │  • auto-creates VPA per workload
    │  • infra/monitoring namespaces → updateMode: "Off"
    │  • user app namespaces → updateMode: "InPlaceOrRecreate"
    │  • GPU workloads → updateMode: "Off"
    ▼
VPA resources (one per workload)
    │
    ├─ Infra namespaces: recommend-only (manual review)
    └─ App namespaces: auto-resize (InPlaceOrRecreate)
    │
    ▼
Human reviews infra → updates values.yaml → Git push → ArgoCD applies
VPA Updater auto-resizes app pods → no human intervention needed
```

**Kyverno is the sole VPA creator.** The `vpa-auto-generate` ClusterPolicy watches all workloads and generates VPA resources automatically. No manual VPA manifests needed.

---

## Components

| Component | Chart | Namespace | Location |
|-----------|-------|-----------|----------|
| **metrics-server** | `metrics-server/metrics-server` | `kube-system` | `infrastructure/controllers/metrics-server/` |
| **VPA** | `fairwinds-stable/vpa` | `vertical-pod-autoscaler` | `infrastructure/controllers/vertical-pod-autoscaler/` |
| **Kyverno VPA policy** | — | `kyverno` | `infrastructure/controllers/kyverno/policies/vpa-auto-generate.yaml` |

metrics-server and VPA are deployed via the **Infrastructure ApplicationSet** (Wave 4). The Kyverno policy is deployed as part of Kyverno (Wave 3).

### VPA Sub-Components

| Component | Purpose |
|-----------|---------|
| **Recommender** | Analyzes metrics, generates recommendations |
| **Updater** | Applies changes when mode is not Off (evicts or in-place resizes) |
| **Admission Controller** | Sets resources on new pods when mode is not Off |

### Update Modes by Namespace

| Namespace Type | Update Mode | Behavior |
|---------------|-------------|----------|
| Infrastructure (argocd, cilium, etc.) | `Off` | Recommend only — manual GitOps workflow |
| Monitoring (prometheus-stack, loki-stack, etc.) | `Off` | Recommend only — manual GitOps workflow |
| GPU workloads (runtimeClassName: nvidia) | `Off` | Recommend only — VPA can't manage GPU resources |
| User apps (everything else) | `InPlaceOrRecreate` | Auto-resize pods without restart when possible |

---

## CLI Tools & Scripts

### vpa-report.sh

The `scripts/vpa-report.sh` script provides a formatted table of all VPA recommendations with human-readable values.

```bash
# All namespaces
./scripts/vpa-report.sh

# Single namespace
./scripts/vpa-report.sh argocd
```

Example output:
```
==========================================
  VPA Resource Recommendations Report
==========================================

NAMESPACE            WORKLOAD                            CONTAINER                    CPU TGT  CPU RANGE    MEM TGT  MEM RANGE
-------------------------------------------------------------------------------------------------------------------------------------------------
argocd               Deployment/argocd-server            server                          23m    12m-100m     175Mi   88Mi-700Mi
argocd               Deployment/argocd-repo-server       repo-server                   2975m  1488m-11900m  523Mi  262Mi-2.0Gi
...

Total: 42 containers with VPA recommendations

Action needed if your current request is:
  < lowerBound  →  INCREASE NOW (pod is being throttled)
  < target      →  INCREASE (under-provisioned)
  ≈ target      →  KEEP (well-tuned)
  > 2x target   →  DECREASE (over-provisioned)
```

### kubectl One-Liners

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

# Current resource usage vs requests (side-by-side comparison)
kubectl top pods -n <namespace>
kubectl get deploy <name> -n <ns> -o jsonpath='{.spec.template.spec.containers[0].resources}'
kubectl get vpa <name> -n <ns> -o jsonpath='{.status.recommendation.containerRecommendations[0].target}'
```

---

## Reading Recommendations

### The Four VPA Values

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

---

## Applying Changes (GitOps Workflow)

### For Infrastructure Namespaces (updateMode: Off)

1. Read the VPA recommendation (`./scripts/vpa-report.sh` or Grafana dashboard)
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

### For User App Namespaces (updateMode: InPlaceOrRecreate)

No manual action needed. VPA automatically:
1. Watches pod resource usage
2. Calculates optimal requests
3. Patches pods in-place (K8s 1.35 GA feature)
4. Falls back to evict+recreate if in-place resize fails

### Setting Requests vs Limits

| Field | Rule of Thumb |
|-------|--------------|
| `requests.cpu` | VPA `target` (or 1.1-1.2x for buffer) |
| `requests.memory` | VPA `target` (or 1.2-1.5x — memory OOM is fatal, CPU throttling is not) |
| `limits.cpu` | 2-4x request (allows burst). Or omit entirely to let pods burst freely. |
| `limits.memory` | 2-4x request (or match VPA `upperBound` if spikes are expected) |

---

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
VPA only tracks CPU/memory, not GPU. Recommendations will show low CPU/memory because compute happens on GPU VRAM. Set CPU/memory based on data loading needs, not inference. GPU workloads automatically get `updateMode: "Off"` via the Kyverno policy.

---

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
controller:     cpu: 2000m, memory: 4Gi    # DOUBLED CPU, quadrupled memory
repo-server:    cpu: 3000m, memory: 768Mi  # TRIPLED CPU, halved memory
server:         cpu: 50m,   memory: 512Mi  # REDUCED 10x CPU
applicationSet: cpu: 100m,  memory: 128Mi  # REDUCED 2.5x
redis:          cpu: 50m,   memory: 128Mi  # REDUCED 2x
Total: 5.2 CPU, 5.5Gi memory
```

**Result**: +2.35 CPU where it was needed (controller/repo-server), memory properly sized, no more throttling.

See `infrastructure/controllers/argocd/values.yaml` for the actual implementation with inline VPA documentation.

---

## In-Place Pod Resize (K8s 1.35)

This cluster runs K8s v1.35.2 where In-Place Pod Resize is GA. VPA supports `updateMode: "InPlaceOrRecreate"` which resizes pods **without restarting them** when possible.

### How It Works

1. VPA Updater watches pods with `InPlaceOrRecreate` mode
2. If recommendation differs significantly from current resources, it patches the pod spec
3. Kernel applies new CPU/memory limits **without restarting** the container (when supported)
4. If in-place resize fails, pod is evicted and recreated with new resources

### Namespace Strategy

The Kyverno `vpa-auto-generate` policy sets update modes automatically:
- **Infrastructure/monitoring**: `Off` — changes go through GitOps review
- **User apps**: `InPlaceOrRecreate` — automatic resource adjustment
- **GPU workloads**: `Off` — VPA can't manage GPU resources

---

## Kyverno VPA Policy

### How It Works

The `vpa-auto-generate` ClusterPolicy (`infrastructure/controllers/kyverno/policies/vpa-auto-generate.yaml`) watches for Deployment, StatefulSet, and DaemonSet resources and generates a matching VPA.

**Three rules**:
1. **generate-vpa-infra-off**: Infrastructure/monitoring namespaces get `updateMode: "Off"`
2. **generate-vpa-gpu-off**: GPU workloads (runtimeClassName: nvidia) get `updateMode: "Off"`
3. **generate-vpa-apps-auto**: Everything else gets `updateMode: "InPlaceOrRecreate"`

Generated VPAs have `ownerReferences` set to the parent workload, so they're automatically cleaned up when the workload is deleted.

### Excluded Namespaces

- `kube-system` — excluded from all rules
- `kyverno` — excluded from all rules (prevents circular dependency)
- `volsync-system` — excluded from all rules (transient mover jobs)

### Checking Generated VPAs

```bash
# See all Kyverno-managed VPAs
kubectl get vpa -A -l app.kubernetes.io/managed-by=kyverno

# Check a specific VPA's update mode
kubectl get vpa -n immich -o jsonpath='{.items[0].spec.updatePolicy.updateMode}'
# Expected: InPlaceOrRecreate

kubectl get vpa -n argocd -o jsonpath='{.items[0].spec.updatePolicy.updateMode}'
# Expected: Off
```

---

## Troubleshooting

### No recommendations showing
- VPA needs ~5-10 minutes for initial data, 24+ hours for accuracy
- Check metrics-server: `kubectl top nodes` (should return data)
- Check VPA recommender: `kubectl logs -n vertical-pod-autoscaler -l app.kubernetes.io/component=recommender`

### VPAs not being created
- Check Kyverno background controller: `kubectl get pods -n kyverno`
- Check Kyverno logs: `kubectl logs -n kyverno -l app.kubernetes.io/component=background-controller`
- Verify the policy is ready: `kubectl get clusterpolicy vpa-auto-generate`
- Check VPA CRDs are installed: `kubectl get crd verticalpodautoscalers.autoscaling.k8s.io`

### VPA recommendations seem too high/low
- Not enough data — wait 7-14 days
- Workload changed recently — VPA is backward-looking
- Check `upperBound` for peak usage context
- Batch/cron workloads have spiky usage — use `upperBound` for limits

### Pods OOMKilled after applying VPA
- VPA target reflects steady-state, not initialization spikes
- Set `limits.memory` well above `requests.memory` (2-4x)
- Check startup memory with `kubectl top pod` during pod init

### Duplicate VPA resources
- Kyverno is the sole VPA creator — if you see duplicates, check for manually created VPAs
- Remove any hand-crafted VPA manifests from Git and let Kyverno manage them

---

## Grafana Dashboard

A community VPA dashboard is auto-provisioned in Grafana under the **Infrastructure** folder:

| Dashboard | Grafana.com ID | What It Shows |
|-----------|---------------|---------------|
| **K8s Autoscaling VPA** | [22168](https://grafana.com/grafana/dashboards/22168) | Cluster overview with drill-down to pod-level VPA details (target, lower/upper bounds) |

**URL**: https://grafana.vanillax.me → search for "VPA"

This dashboard reads VPA metrics exposed by kube-state-metrics Custom Resource State (`kube_customresource_verticalpodautoscaler_*`). Combined with `vpa-report.sh`, you have two ways to view VPA data:

1. **Grafana VPA dashboard** — time-series graphs and historical trends
2. **CLI** — `./scripts/vpa-report.sh` for quick terminal output

---

## Quick Reference

```bash
# Human-readable VPA report
./scripts/vpa-report.sh
./scripts/vpa-report.sh <namespace>

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

# Check Kyverno VPA policy
kubectl get clusterpolicy vpa-auto-generate
kubectl describe clusterpolicy vpa-auto-generate

# Check VPA recommender
kubectl logs -n vertical-pod-autoscaler -l app.kubernetes.io/component=recommender

# List Kyverno-managed VPAs
kubectl get vpa -A -l app.kubernetes.io/managed-by=kyverno

# Monitor VPA auto-resize events
kubectl get events -A --field-selector reason=VpaUpdated
```

---

## Related Docs

- [Monitoring README](../monitoring/README.md) — metrics-server vs Prometheus pipelines
- [VPA component README](../infrastructure/controllers/vertical-pod-autoscaler/README.md)
- [Kyverno VPA policy](../infrastructure/controllers/kyverno/policies/vpa-auto-generate.yaml)

---

**Last Updated**: 2026-03-09
**Cluster**: talos-prod-cluster (K8s v1.35.2, Talos v1.12.5)
