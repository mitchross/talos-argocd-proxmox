# Vertical Pod Autoscaler (VPA)

VPA monitors actual CPU/memory usage and recommends optimal resource requests for pods.

## How It Works

A Kyverno ClusterPolicy (`infrastructure/controllers/kyverno/policies/vpa-auto-generate.yaml`) automatically creates a VPA resource for every Deployment, StatefulSet, and DaemonSet in the cluster. Infrastructure/monitoring namespaces get `updateMode: "Off"` (recommend only). User app namespaces get `updateMode: "Initial"` (sets optimal resources at pod creation).

## Reading Recommendations

```bash
# Quick summary of all VPA recommendations
kubectl get vpa -A -o custom-columns=\
NAMESPACE:.metadata.namespace,\
NAME:.metadata.name,\
CPU:.status.recommendation.containerRecommendations[0].target.cpu,\
MEM:.status.recommendation.containerRecommendations[0].target.memory

# Full detail for a specific app
kubectl describe vpa <name> -n <namespace>
```

Recommendations include four values per container:
- **target** — what VPA thinks you should set
- **lowerBound** — minimum safe value
- **upperBound** — max it would recommend
- **uncappedTarget** — ideal ignoring any min/max constraints

## Components

| Component | Purpose |
|-----------|---------|
| **Recommender** | Analyzes metrics, generates recommendations |
| **Updater** | Applies changes when mode is not Off (evicts or in-place resizes) |
| **Admission Controller** | Sets resources on new pods when mode is not Off |

## Dependencies

- **metrics-server** (`infrastructure/controllers/metrics-server/`) — provides the `metrics.k8s.io` API that VPA reads from
- **Kyverno VPA policy** (`infrastructure/controllers/kyverno/policies/vpa-auto-generate.yaml`) — auto-creates VPA resources for all workloads

## Notes

- VPA only tracks CPU and memory — GPU (`nvidia.com/gpu`) and ephemeral-storage are not managed
- Recommendations need a few hours of pod runtime to stabilize
- Upper bounds will be very wide initially and tighten over days
- GPU workloads will show low CPU/memory recommendations since compute happens on GPU VRAM
