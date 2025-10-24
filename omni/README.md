# Talos + Omni + Cilium Configuration

## Overview

This cluster uses:
- **Talos OS** (via Sidero Omni)
- **Cilium** with kube-proxy replacement
- **KubePrism** for control plane load balancing
- **L2 Announcements** for LoadBalancer services

## Critical Configuration: kube-proxy Disabled

**IMPORTANT**: This cluster runs Cilium with `kubeProxyReplacement: true` (see `infrastructure/networking/cilium/values.yaml:12`).

Therefore, **kube-proxy MUST be disabled** in Talos to avoid conflicts.

### The Problem (Before Fix)

Without disabling kube-proxy:
- ❌ Cilium and kube-proxy fight over LoadBalancer health check ports
- ❌ Gateway services fail with "address already in use" errors
- ❌ ArgoCD, Longhorn, and other services become inaccessible
- ❌ Random connection resets and 503 errors

### The Solution

**File**: `omni/disable-kube-proxy.yaml`

Apply this config patch to **ALL machines** (control plane + workers) in Omni:

```yaml
cluster:
  proxy:
    disabled: true
```

## How to Apply in Omni

1. Go to your cluster in Omni UI
2. Navigate to **Config Patches**
3. Create a new patch:
   - **Name**: `disable-kube-proxy`
   - **Target**: All machines (or create separate patches for control plane/workers)
   - **Content**: Copy from `disable-kube-proxy.yaml`
4. Apply and wait for machines to reconcile

**NOTE**: Machines will NOT reboot, but kube-proxy pods will be removed.

## Verification

After applying:

```bash
# Should return NO results
kubectl get pods -n kube-system -l k8s-app=kube-proxy

# Should show services without health check errors
kubectl get events -n gateway --field-selector type=Warning

# Gateway services should be healthy
kubectl get svc -n gateway
```

## Config Files

- **`non-gpu-workers.yaml`**: Patch for non-GPU worker nodes
  - Longhorn volume config
  - Containerd settings
  - KubePrism enabled

- **`gpu-workers.yaml`**: Patch for GPU worker nodes
  - All non-GPU settings
  - NVIDIA container runtime
  - NVIDIA kernel modules

- **`disable-kube-proxy.yaml`**: Critical patch to disable kube-proxy
  - **MUST** be applied when using Cilium kube-proxy replacement

- **`example-worker-config.yaml`**: Full worker config example
  - For reference only
  - Shows complete Talos machine config structure

## Architecture Notes

### KubePrism (Port 7445)

KubePrism provides HA load balancing for Kubernetes API server access:
- Runs on each node
- Listens on `localhost:7445`
- Load balances to all control plane nodes
- Cilium configured to use it: `k8sServiceHost: localhost`, `k8sServicePort: "7445"`

### Network Stack

1. **Cilium** handles:
   - Pod networking (CNI)
   - Service load balancing (replaces kube-proxy)
   - Network policies
   - Gateway API (Ingress replacement)
   - L2 LoadBalancer announcements

2. **KubePrism** handles:
   - Control plane HA/LB

3. **kube-proxy**:
   - ❌ **DISABLED** - Cilium replaces it entirely

## Troubleshooting

### Gateway services failing with port conflicts

**Symptoms**:
```
Warning FailedToStartServiceHealthcheck service/cilium-gateway-gateway-internal
node X failed to start healthcheck on port 31245: bind: address already in use
```

**Cause**: kube-proxy is still running while Cilium is also active.

**Fix**: Apply `disable-kube-proxy.yaml` patch to all machines.

### Temporary CLI workaround (not permanent)

If you need to disable kube-proxy immediately before applying the Omni patch:

```bash
# This disables kube-proxy until next node reboot
kubectl -n kube-system patch daemonset kube-proxy \
  -p '{"spec":{"template":{"spec":{"nodeSelector":{"non-existing":"true"}}}}}'
```

**NOTE**: This is NOT permanent. Machines will re-enable kube-proxy on reboot unless the Omni config patch is applied.

## References

- [Talos + Cilium Guide](https://www.talos.dev/v1.11/kubernetes-guides/network/cilium/)
- [Cilium kube-proxy replacement](https://docs.cilium.io/en/stable/network/kubernetes/kubeproxy-free/)
- [Omni Config Patches](https://omni.siderolabs.com/docs/how-to-guides/how-to-configure-machines/)
