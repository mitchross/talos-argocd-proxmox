# VPA Resource Optimization Guide

How to use VPA and Goldilocks to right-size Kubernetes resource requests based on actual workload behavior.

## TL;DR — Just Tell Me What To Do

**Everything is automatic.** Goldilocks auto-creates VPA resources for every workload in the cluster. You don't need to set anything up.

### Step 1: Open the dashboard

Go to **https://goldilocks.vanillax.me** in your browser (must be on LAN/VPN).

### Step 2: Pick a namespace

Click any namespace (e.g., `argocd`, `immich`, `home-assistant`). You'll see every workload with its current resource settings and what VPA recommends.

### Step 3: Look for problems

The dashboard shows color-coded recommendations. Look for:
- **Current request way below "Target"** = pod is starved, increase it
- **Current request way above "Target"** = wasting resources, decrease it
- **Current request below "Lower Bound"** = pod is actively throttled, fix ASAP

### Step 4: Apply changes

Edit the app's `values.yaml` in Git, update the `resources:` block, push, ArgoCD applies it. Add a comment explaining why:

```yaml
# VPA-optimized (2026-02-24) — target was 2000m, previous 500m
resources:
  requests:
    cpu: 2000m
    memory: 1Gi
```

### Step 5: Wait and re-check

VPA recommendations update continuously. Check back in a week to see if the new values are good. Don't change things daily.

### Quick script to see all recommendations

```bash
# Full report with human-readable values and action guidance
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
Goldilocks Controller (on-by-default: "true")
    │  • watches all namespaces
    │  • auto-creates a VPA (updateMode: "Off") for every Deployment, StatefulSet, DaemonSet
    ▼
VPA resources (one per workload, recommend-only)
    │
    ▼
Goldilocks Dashboard (reads VPA .status, renders per-namespace view)
    │
    ▼
Human reviews → updates values.yaml → Git push → ArgoCD applies
```

**Goldilocks is the sole VPA creator.** With `on-by-default: "true"`, it auto-creates VPA resources for all workloads cluster-wide. No manual VPA manifests needed.

---

## Components

| Component | Chart | Version | Namespace | Location |
|-----------|-------|---------|-----------|----------|
| **metrics-server** | `metrics-server/metrics-server` | — | `kube-system` | `infrastructure/controllers/metrics-server/` |
| **VPA** | `fairwinds-stable/vpa` | 4.10.1 | `vertical-pod-autoscaler` | `infrastructure/controllers/vertical-pod-autoscaler/` |
| **Goldilocks** | `fairwinds-stable/goldilocks` | 10.3.0 | `goldilocks` | `infrastructure/controllers/goldilocks/` |

All three are deployed via the **Infrastructure ApplicationSet** (Wave 4).

### VPA Sub-Components

| Component | Purpose |
|-----------|---------|
| **Recommender** | Analyzes metrics, generates recommendations |
| **Updater** | Applies changes when mode is not Off (evicts or in-place resizes) |
| **Admission Controller** | Sets resources on new pods when mode is not Off |

Currently the cluster runs VPA in **Off mode** — recommendations only, no automatic changes.

---

## Goldilocks Dashboard

### Accessing the Dashboard

**URL**: https://goldilocks.vanillax.me (routed via `gateway-internal`, LAN/VPN only)

Fallback if gateway is down:
```bash
kubectl port-forward -n goldilocks svc/goldilocks-dashboard 8080:80
# Open http://localhost:8080
```

### What the Dashboard Shows

For each namespace, every workload with a VPA gets a card showing:
- **Current requests/limits** — what's set in the deployment spec
- **Guaranteed QoS** — suggested `requests` YAML block (requests = limits)
- **Burstable QoS** — suggested `requests` YAML block (requests only, no limits)
- **Lower bound, Target, Upper bound** per container

### Excluding Namespaces

With `on-by-default: "true"`, all namespaces are included. To exclude one:

```bash
kubectl label namespace <ns> goldilocks.fairwinds.com/enabled=false
```

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
goldilocks           Deployment/goldilocks-controller     goldilocks                      12m     6m-48m      64Mi    32Mi-256Mi
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

### Step-by-Step

1. Read the VPA recommendation (Goldilocks dashboard or `./scripts/vpa-report.sh`)
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
VPA only tracks CPU/memory, not GPU. Recommendations will show low CPU/memory because compute happens on GPU VRAM. Set CPU/memory based on data loading needs, not inference.

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
controller:     cpu: 2000m, memory: 1536Mi  # DOUBLED (was throttled)
repo-server:    cpu: 3000m, memory: 768Mi   # TRIPLED CPU, halved memory
server:         cpu: 50m,   memory: 256Mi   # REDUCED 10x
applicationSet: cpu: 100m,  memory: 128Mi   # REDUCED 2.5x
redis:          cpu: 50m,   memory: 128Mi   # REDUCED 2x
Total: 5.2 CPU, 2.8Gi memory
```

**Result**: +2.35 CPU where it was needed (controller/repo-server), -0.1Gi memory overall, no more CPU throttling on the controller.

See `infrastructure/controllers/argocd/values.yaml` for the actual implementation with inline VPA documentation.

---

## In-Place Pod Resize (K8s 1.35)

This cluster runs K8s v1.35.1 where In-Place Pod Resize is GA. VPA supports `updateMode: "InPlaceOrRecreate"` which resizes pods **without restarting them** when possible.

Currently we use `updateMode: "Off"` (manual review via Goldilocks). When confident in VPA accuracy after 2-4 weeks of observation, you can enable auto-tuning per workload.

### How to Enable

Goldilocks creates VPAs with `updateMode: "Off"`. To enable in-place resize for a specific workload, create a manual VPA that overrides the Goldilocks-managed one:

```yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: my-app              # Must match Goldilocks VPA name
  namespace: my-app
  labels:
    goldilocks.fairwinds.com/enabled: "false"  # Prevent Goldilocks from overwriting
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: my-app
  updatePolicy:
    updateMode: "InPlaceOrRecreate"  # Live resize when possible
```

**Start with non-critical workloads** (dev tools, media apps) before enabling on infrastructure.

### How It Works

1. VPA Updater watches pods with `InPlaceOrRecreate` mode
2. If recommendation differs significantly from current resources, it patches the pod spec
3. Kernel applies new CPU/memory limits **without restarting** the container (when supported)
4. If in-place resize fails, pod is evicted and recreated with new resources

---

## Troubleshooting

### No recommendations showing
- VPA needs ~5-10 minutes for initial data, 24+ hours for accuracy
- Check metrics-server: `kubectl top nodes` (should return data)
- Check VPA recommender: `kubectl logs -n vertical-pod-autoscaler -l app.kubernetes.io/component=recommender`

### Goldilocks dashboard is empty
- Check if Goldilocks controller is running: `kubectl get pods -n goldilocks`
- Goldilocks is set to `on-by-default: "true"` — all namespaces should appear
- Check Goldilocks controller logs: `kubectl logs -n goldilocks -l app.kubernetes.io/name=goldilocks,app.kubernetes.io/component=controller`
- Verify VPA CRDs are installed: `kubectl get crd verticalpodautoscalers.autoscaling.k8s.io`

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
- Goldilocks is the sole VPA creator — if you see duplicates, check for manually created VPAs
- Remove any hand-crafted VPA manifests from Git and let Goldilocks manage them

---

## Quick Reference

```bash
# Goldilocks dashboard (LAN)
https://goldilocks.vanillax.me

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

# Check Goldilocks controller
kubectl get pods -n goldilocks
kubectl logs -n goldilocks -l app.kubernetes.io/name=goldilocks,app.kubernetes.io/component=controller

# Check VPA recommender
kubectl logs -n vertical-pod-autoscaler -l app.kubernetes.io/component=recommender
```

## Grafana Dashboards

Two community dashboards are auto-provisioned in Grafana under the **Infrastructure** folder:

| Dashboard | Grafana.com ID | What It Shows |
|-----------|---------------|---------------|
| **VPA Recommendations** | [14588](https://grafana.com/grafana/dashboards/14588) | Table of target/lower/upper bounds per container, namespace summary |
| **K8s Autoscaling VPA** | [22168](https://grafana.com/grafana/dashboards/22168) | Cluster overview with drill-down to pod-level VPA details |

**URL**: https://grafana.vanillax.me → search for "VPA"

These dashboards read VPA metrics exposed by kube-state-metrics (`kube_verticalpodautoscaler_*`). Combined with Goldilocks and `vpa-report.sh`, you have three ways to view VPA data:

1. **Goldilocks dashboard** — per-namespace cards with copy-paste YAML
2. **Grafana VPA dashboards** — time-series graphs and historical trends
3. **CLI** — `./scripts/vpa-report.sh` for quick terminal output

---

## Related Docs

- [Monitoring README](../monitoring/README.md) — metrics-server vs Prometheus pipelines
- [VPA component README](../infrastructure/controllers/vertical-pod-autoscaler/README.md)
- [Goldilocks config](../infrastructure/controllers/goldilocks/)

---

**Last Updated**: 2026-02-28
**Cluster**: talos-prod-cluster (K8s v1.35.1, Talos v1.12.4)
