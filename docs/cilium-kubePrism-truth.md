# Cilium Configuration for Omni - CORRECTED

## TL;DR - The Truth About Omni + kubePrism

**I was wrong earlier!** Here's what's actually happening:

- ✅ **192.168.10.100 is NOT a VIP** - it's the IP of your first control plane node (talos-c7r-dgh)
- ✅ **kubePrism IS the load balancer** - it runs on every node and load balances to all 3 control planes
- ✅ **localhost:7445 is CORRECT** - this is how you access kubePrism
- ✅ **Omni uses SideroLink** - kubePrism leverages this to reach all control planes

## What is kubePrism?

kubePrism is a **local load balancer** that runs on every Talos node. With Omni:

1. **Runs on every node** at `localhost:7445`
2. **Knows about all control planes** via Omni's SideroLink network
3. **Automatically load balances** API requests across all 3 control plane nodes
4. **Handles failover** - if one control plane is down, routes to healthy ones
5. **No external VIP needed** - each node has its own local LB

## Network Architecture with Omni + kubePrism

```
┌─────────────────────────────────────────────────┐
│                  Omni SideroLink                │
│         (manages connectivity between nodes)     │
└───────────┬────────────────────────┬────────────┘
            │                        │
            │                        │
    ┌───────▼────────┐      ┌───────▼────────┐
    │  Worker Node   │      │ Control Plane  │
    │                │      │   Node 1       │
    │  kubePrism     │      │ 192.168.10.100 │
    │  localhost:7445├──────►                │
    │                │      │  kube-apiserver│
    │  Cilium pod    │      │  :6443         │
    │  connects here │      └────────────────┘
    └────────────────┘              │
            │                       │
            │           ┌───────────┴────────────┐
            │           │                        │
            │   ┌───────▼────────┐      ┌───────▼────────┐
            │   │ Control Plane  │      │ Control Plane  │
            │   │   Node 2       │      │   Node 3       │
            │   │ 192.168.10.101 │      │ 192.168.10.102 │
            │   │                │      │                │
            │   │  kube-apiserver│      │  kube-apiserver│
            └───►  :6443         │      │  :6443         │
                └────────────────┘      └────────────────┘
                
    kubePrism load balances to all 3 control planes
```

## Correct Configuration

### values.yaml (CORRECT)

```yaml
cluster:
  name: talos-proxmox-prod  # ✅ Updated cluster name
  id: 1

kubeProxyReplacement: true

routingMode: native  # ✅ Better performance on same L2 network
ipv4NativeRoutingCIDR: 10.14.0.0/16  # ✅ Your pod CIDR

# ✅ CORRECT - Point to kubePrism!
k8sServiceHost: localhost
k8sServicePort: 7445  # kubePrism port

# Rest of config...
l2announcements:
  enabled: true  # ✅ For service LoadBalancers
```

### What Changed vs Original talhelper Setup

| Setting | Original (talhelper) | Omni-Managed | Reason |
|---------|---------------------|--------------|---------|
| `cluster.name` | `talos-default` | `talos-proxmox-prod` | Better name |
| `routingMode` | `tunnel` | `native` | Performance optimization |
| `ipv4NativeRoutingCIDR` | Commented | `10.14.0.0/16` | Required for native mode |
| `k8sServiceHost` | `localhost` | `localhost` | ✅ SAME! kubePrism is still used |
| `k8sServicePort` | `7445` | `7445` | ✅ SAME! kubePrism port |
| Control plane VIP | Had VIP resources | Removed | kubePrism handles HA |

## What We Removed

Since kubePrism handles control plane HA, we don't need these:

- ❌ `kube-apiserver-vip.yaml` - Control plane VIP service
- ❌ `vip-pool.yaml` - IP pool for control plane VIP  
- ❌ `control-plane-l2-policy.yaml` - L2 announcements for control plane

## What We Kept

- ✅ `ip-pool.yaml` - LoadBalancer IP pool for services (192.168.10.50-99)
- ✅ `l2-policy.yaml` - L2 announcements for service LoadBalancers
- ✅ `announce.yaml` - L2 announcement CRD

## Why This is Better

### Omni + kubePrism Benefits

1. **Built-in HA** - kubePrism automatically load balances
2. **SideroLink magic** - Connectivity managed by Omni
3. **No external LB needed** - Each node has local LB
4. **Automatic failover** - kubePrism detects unhealthy control planes
5. **Simple config** - Just point to localhost!

### Native Routing Benefits

1. **Better performance** - No encapsulation overhead
2. **Lower latency** - Direct routing between pods
3. **Less CPU usage** - No tunneling overhead
4. **Simpler troubleshooting** - Standard routing

## Installation

```bash
# 1. Install Gateway API CRDs
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.3.0/standard-install.yaml
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.3.0/experimental-install.yaml

# 2. Install Cilium
kubectl kustomize infrastructure/networking/cilium --enable-helm | kubectl apply -f -

# 3. Verify
kubectl get pods -n kube-system -l app.kubernetes.io/name=cilium -w
```

## Verification

```bash
# Check Cilium is using kubePrism
kubectl exec -n kube-system ds/cilium -- cilium-dbg status | grep -i "k8s"
# Should show: K8s: Ok  Api: localhost:7445 [...]

# Check routing mode
kubectl exec -n kube-system ds/cilium -- cilium-dbg status | grep -i "routing mode"
# Should show: Routing Mode: native

# Verify kubePrism is running on all nodes
talosctl --context omni get services | grep kubePrism
# Should show: kubePrism running on all nodes
```

## Key Takeaways

1. ✅ **kubePrism is always used** - even with Omni!
2. ✅ **192.168.10.100 is just one node** - not a VIP
3. ✅ **Omni enhances kubePrism** - via SideroLink
4. ✅ **localhost:7445 is correct** - this accesses kubePrism
5. ✅ **Native routing is a win** - better performance
6. ✅ **No control plane VIP needed** - kubePrism handles it

## Sorry for the Confusion!

I initially thought Omni replaced kubePrism with its own load balancer, but that's not how it works. Omni **enhances** Talos's built-in features (like kubePrism) with better management, visualization, and SideroLink networking.

**The moral**: Trust the Talos architecture! kubePrism is brilliant and Omni makes it even better. 🎉

---

**Your config is now correct!** Install Cilium and enjoy your cluster. 🚀
