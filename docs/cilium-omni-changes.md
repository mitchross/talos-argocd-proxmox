# Cilium Configuration Changes for Omni

## Summary of Changes

Your Cilium configuration has been updated to work with Sidero Omni instead of the traditional talhelper/kubePrism setup.

## Files Modified

### 1. `infrastructure/networking/cilium/values.yaml`

| Setting | Old Value (kubePrism) | New Value (Omni) | Reason |
|---------|----------------------|------------------|---------|
| `cluster.name` | `talos-default` | `talos-proxmox-prod` | Updated cluster name |
| `routingMode` | `tunnel` | `native` | Better performance on same L2 network |
| `ipv4NativeRoutingCIDR` | `# 10.14.0.0/16` (commented) | `10.14.0.0/16` (enabled) | Required for native routing |
| `k8sServiceHost` | `localhost` | `192.168.10.100` | Point to Omni's load balancer |
| `k8sServicePort` | `7445` | `6443` | Standard Kubernetes API port |

### 2. `infrastructure/networking/cilium/kustomization.yaml`

**Removed resources** (Omni handles control plane HA):
- ❌ `vip-pool.yaml` - Control plane VIP pool
- ❌ `kube-apiserver-vip.yaml` - Control plane VIP Service  
- ❌ `control-plane-l2-policy.yaml` - Control plane L2 announcement policy

**Kept resources** (for service LoadBalancers):
- ✅ `announce.yaml` - L2 announcement CRD
- ✅ `ip-pool.yaml` - LoadBalancer IP pool (192.168.10.50-99)
- ✅ `l2-policy.yaml` - L2 announcement policy for services

## Key Differences: kubePrism vs Omni

### Traditional Talos (kubePrism)
```yaml
# Uses local API proxy on each node
k8sServiceHost: localhost
k8sServicePort: 7445

# Cilium manages control plane VIP
- kube-apiserver-vip.yaml (192.168.10.199)
- L2 announcements for control plane HA
```

### Omni-Managed Talos
```yaml
# Points to Omni's managed load balancer
k8sServiceHost: 192.168.10.100
k8sServicePort: 6443

# Omni manages control plane HA
- No VIP resources needed
- Omni handles control plane load balancing
```

## Installation Commands

```bash
# 1. Install Gateway API CRDs
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.3.0/standard-install.yaml
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.3.0/experimental-install.yaml

# 2. Install Cilium with updated config
kubectl kustomize infrastructure/networking/cilium --enable-helm | kubectl apply -f -

# 3. Watch pods come up
kubectl get pods -n kube-system -l app.kubernetes.io/name=cilium -w
```

## Verification

```bash
# Check routing mode
kubectl exec -n kube-system ds/cilium -- cilium-dbg status | grep -i "routing mode"
# Output: Routing Mode: native

# Check API connectivity
kubectl exec -n kube-system ds/cilium -- cilium-dbg status | grep -i "k8s"
# Output: K8s: 192.168.10.100:6443 (should be Omni endpoint)

# Verify nodes are Ready
kubectl get nodes
```

## What Still Works

✅ **L2 announcements for services** - Still enabled for LoadBalancer services  
✅ **LoadBalancer IP pool** - Services can still get IPs from 192.168.10.50-99  
✅ **Gateway API** - Still enabled for ingress  
✅ **Hubble** - Observability still configured  
✅ **Native routing** - Better performance than tunnel mode  

## What Changed

❌ **Control plane VIP** - Omni manages this, no longer need Cilium VIP  
❌ **kubePrism** - Not using localhost:7445 proxy  
✅ **Direct API access** - Cilium talks directly to Omni's load balancer  

## Benefits of This Setup

1. **Simplified** - Omni handles control plane HA, less to manage in Cilium
2. **Native routing** - Better performance (no encapsulation overhead)
3. **Cleaner separation** - Omni does control plane, Cilium does CNI
4. **Still have L2LB** - Services still get LoadBalancer IPs via Cilium

## Network Architecture

```
                    Omni-Managed Load Balancer
                    192.168.10.100:6443
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
    ┌─────▼──────┐     ┌─────▼──────┐     ┌─────▼──────┐
    │ Control-01 │     │ Control-02 │     │ Control-03 │
    │  (Cilium)  │     │  (Cilium)  │     │  (Cilium)  │
    └────────────┘     └────────────┘     └────────────┘
          │                   │                   │
          └───────────────────┴───────────────────┘
                              │
                    Native Routing Mode
                    (10.14.0.0/16 pod CIDR)
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
    ┌─────▼──────┐     ┌─────▼──────┐     ┌─────▼──────┐
    │ Worker-01  │     │ Worker-02  │     │ GPU-Worker │
    │  (Cilium)  │     │  (Cilium)  │     │  (Cilium)  │
    └────────────┘     └────────────┘     └────────────┘
```

## Rollback (If Needed)

If you need to revert to kubePrism setup:

```bash
cd infrastructure/networking/cilium
git checkout HEAD -- values.yaml kustomization.yaml
```

Then apply the old config:
```bash
kubectl kustomize infrastructure/networking/cilium --enable-helm | kubectl apply -f -
```

## Next Steps

After Cilium is installed and nodes are Ready:

1. ✅ Verify Cilium is using native routing
2. ✅ Check Omni dashboard shows healthy cluster
3. ✅ Bootstrap ArgoCD to deploy rest of stack
4. ✅ Test service LoadBalancers work (should get IPs from 192.168.10.50-99)

---

**Configuration complete!** Your Cilium is now properly configured for Omni. 🚀
