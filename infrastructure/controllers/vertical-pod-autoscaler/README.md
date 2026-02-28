# Vertical Pod Autoscaler (VPA)

VPA monitors actual CPU/memory usage and recommends optimal resource requests for pods.

## How It Works

VPA is deployed in **Off mode** — it generates recommendations but does not apply them. A Kyverno ClusterPolicy (`vpa-auto-create`) automatically creates a VPA resource for every Deployment and StatefulSet in the cluster (excluding system namespaces).

When you're ready to let VPA auto-tune, change the `updateMode` to `InPlaceOrRecreate` (K8s 1.35 GA feature — resizes pods without restarting them).

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
- **Goldilocks** (`infrastructure/controllers/goldilocks/`) — auto-creates VPA resources for all workloads and provides dashboard UI

## Notes

- VPA only tracks CPU and memory — GPU (`nvidia.com/gpu`) and ephemeral-storage are not managed
- Recommendations need a few hours of pod runtime to stabilize
- Upper bounds will be very wide initially and tighten over days
- GPU workloads will show low CPU/memory recommendations since compute happens on GPU VRAM
