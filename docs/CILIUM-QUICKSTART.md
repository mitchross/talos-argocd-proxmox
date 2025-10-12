# Quick Start: Install Cilium on Omni Cluster

## Current Status
- ✅ Cluster managed by Omni (192.168.10.15 / omni.vanillax.me)
- ✅ Nodes are up but NotReady (no CNI)
- ✅ Ready to install Cilium

## One-Command Install

```bash
# Install Gateway API CRDs first
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.3.0/standard-install.yaml
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.3.0/experimental-install.yaml

# Install Cilium with VIP configuration
kubectl kustomize infrastructure/networking/cilium --enable-helm | kubectl apply -f -

# Watch it come up (takes 2-3 minutes)
kubectl get pods -n kube-system -l app.kubernetes.io/name=cilium -w
```

## Quick Verification

```bash
# 1. Check Cilium pods
kubectl get pods -n kube-system | grep cilium

# 2. Verify nodes are Ready
kubectl get nodes

# 3. Check Cilium status
kubectl exec -n kube-system ds/cilium -- cilium-dbg status --brief
```

## Correct Config for Omni! ✅

Your `infrastructure/networking/cilium/values.yaml` has been updated with the right settings:

```yaml
# ✅ kubePrism handles control plane HA via Omni's SideroLink
k8sServiceHost: localhost
k8sServicePort: 7445

# ✅ Native routing for better performance (same L2 network)
routingMode: native
ipv4NativeRoutingCIDR: 10.14.0.0/16

# ✅ L2 announcements for service LoadBalancers
l2announcements:
  enabled: true

# ✅ Updated cluster name
cluster:
  name: talos-proxmox-prod
```

**Why kubePrism?** It runs on every node and automatically load balances API requests to all 3 control planes via Omni's SideroLink network. This is the Talos/Omni way!

## What Happens

1. **Gateway API CRDs** installed → Cilium can use Gateway API
2. **Cilium Helm chart** deployed → CNI, operator, hubble all start
3. **Cilium connects via kubePrism** → localhost:7445 load balances to all 3 control planes
4. **L2 announcements** enabled → For service LoadBalancers
5. **Nodes become Ready** → CNI is working, pods can schedule

## After Installation

### Verify Installation

1. Check Cilium is using kubePrism:
   ```bash
   kubectl exec -n kube-system ds/cilium -- cilium-dbg status | grep -i k8s
   # Should show: localhost:7445
   ```

2. Open Omni UI: http://192.168.10.15 or https://omni.vanillax.me
3. Verify all 3 control plane nodes are healthy
4. kubePrism on each node automatically load balances to all control planes!

### Bootstrap ArgoCD

```bash
# Once nodes are Ready, bootstrap GitOps
kustomize build infrastructure/controllers/argocd --enable-helm | kubectl apply -f -
kubectl wait --for condition=established --timeout=60s crd/applications.argoproj.io
kubectl wait --for=condition=Available deployment/argocd-server -n argocd --timeout=300s
kubectl apply -f infrastructure/controllers/argocd/root.yaml
```

## Troubleshooting

### Cilium pods stuck in Init

**Check API connectivity**:
```bash
kubectl logs -n kube-system -l app.kubernetes.io/name=cilium --tail=20
```

**Fix**: Verify kubePrism is running on nodes:
```bash
talosctl --context omni -n <node-ip> service kubePrism
# Should show: STATE: Running
```

### Nodes still NotReady

**Check Cilium status**:
```bash
kubectl exec -n kube-system ds/cilium -- cilium-dbg status
```

**Verify native routing**:
```bash
kubectl exec -n kube-system ds/cilium -- cilium-dbg status | grep -i "routing mode"
# Should show: native
```

## Summary

Your Cilium configuration is **ready for Omni**! The key settings:

- ✅ `k8sServiceHost: localhost` (kubePrism handles control plane HA)
- ✅ `k8sServicePort: 7445` (kubePrism port)
- ✅ `routingMode: native` (better performance on same L2 network)
- ✅ `ipv4NativeRoutingCIDR: 10.14.0.0/16` (pod CIDR specified)
- ✅ `cluster.name: talos-proxmox-prod` (updated name)
- ✅ L2 announcements for service LoadBalancers
- ✅ Removed control plane VIP resources (kubePrism handles this)

**kubePrism FTW!** It automatically load balances API requests to all 3 control planes via Omni's SideroLink. 🚀
