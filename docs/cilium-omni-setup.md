# Cilium Installation for Omni-Managed Cluster

## Overview
This guide covers installing Cilium CNI on your Omni-managed Talos cluster with proper VIP configuration for high-availability control plane access.

## Key Concepts

### Control Plane VIP: 192.168.10.199
- **Purpose**: Provides a single, stable IP for accessing the Kubernetes API
- **Managed by**: Cilium L2 announcements
- **Benefits**: 
  - No need for external load balancer
  - Automatic failover between control plane nodes
  - Native to Cilium, no additional infrastructure

### Current vs Target State

| Component | Current (Pre-Cilium) | Target (Post-Cilium) |
|-----------|---------------------|---------------------|
| API Access | Single control plane node (192.168.10.100) | VIP (192.168.10.199) |
| CNI | None | Cilium 1.18.2 |
| Load Balancing | None | Cilium L2 + LB-IPAM |
| Gateway API | CRDs only | Cilium-managed |

## Prerequisites

```bash
# Verify cluster is accessible
export TALOSCONFIG=~/.talos/config-omni
kubectl get nodes

# Should see nodes but they'll be NotReady (no CNI yet)
```

## Step 1: Install Gateway API CRDs

Cilium requires Gateway API CRDs to be installed first:

```bash
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.3.0/standard-install.yaml
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.3.0/experimental-install.yaml

# Verify CRDs are installed
kubectl get crd | grep gateway
```

Expected output:
```
gatewayclasses.gateway.networking.k8s.io
gateways.gateway.networking.k8s.io
httproutes.gateway.networking.k8s.io
...
```

## Step 2: Review Cilium Values for Omni

Your current `infrastructure/networking/cilium/values.yaml` needs these key settings for Omni:

### Critical Settings

```yaml
# ✅ Correct for Omni - Uses localhost with Talos API forwarding
k8sServiceHost: localhost
k8sServicePort: 7445

# ✅ Tunnel mode - Safe default for mixed networking
routingMode: tunnel

# ✅ Required for kube-proxy replacement
kubeProxyReplacement: true

# ✅ L2 announcements for VIP
l2announcements:
  enabled: true

# ✅ Gateway API support
gatewayAPI:
  enabled: true
  enableAlpn: true
```

### Why `localhost:7445`?

**Omni-managed clusters**: Talos on each node runs a local API proxy that forwards to the control plane. Using `localhost:7445` allows Cilium to communicate with the API server through this local proxy, which is more reliable than trying to reach control plane nodes directly during CNI initialization.

**After Cilium is running**: The VIP (192.168.10.199) will be available, but Cilium itself uses localhost for bootstrapping.

## Step 3: Install Cilium via Kustomize

```bash
# From repository root
cd /Users/mitchross/Documents/Programming/k3s-argocd-proxmox

# Apply Cilium with all configuration
kubectl kustomize infrastructure/networking/cilium --enable-helm | kubectl apply -f -
```

This installs:
1. ✅ Cilium Helm chart (CNI, operator, hubble)
2. ✅ VIP pool for control plane (192.168.10.199)
3. ✅ L2 announcement policy for VIP
4. ✅ LoadBalancer IP pools for services
5. ✅ kube-apiserver-vip Service

## Step 4: Monitor Installation

```bash
# Watch Cilium pods come up
kubectl get pods -n kube-system -l app.kubernetes.io/name=cilium -w

# Check Cilium status (run this after pods are running)
kubectl exec -n kube-system ds/cilium -- cilium-dbg status --brief

# Verify nodes are now Ready
kubectl get nodes

# Check VIP Service
kubectl get svc -n kube-system kube-apiserver-vip
```

Expected output for VIP:
```
NAME                 TYPE           CLUSTER-IP      EXTERNAL-IP      PORT(S)
kube-apiserver-vip   LoadBalancer   10.15.x.x       192.168.10.199   6443:xxxxx/TCP
```

## Step 5: Verify VIP is Working

```bash
# Test API access via VIP
curl -k https://192.168.10.199:6443/healthz
# Should return: ok

# Check which node is announcing the VIP
kubectl get svc kube-apiserver-vip -n kube-system -o yaml | grep -A 5 loadBalancer

# Verify L2 announcements
kubectl get ciliuml2announcementpolicy -n kube-system
kubectl get ciliumloadbalancerippool -n kube-system
```

## Step 6: Update Omni Endpoint (Important!)

After Cilium VIP is working, update your Omni cluster configuration:

1. **In Omni UI** (192.168.10.15 or omni.vanillax.me):
   - Go to your cluster
   - Settings → Cluster Endpoint
   - Change from `192.168.10.100:6443` to `192.168.10.199:6443`
   
2. **Download new talosconfig** from Omni with updated endpoint

3. **Update kubeconfig**:
   ```bash
   # Backup old config
   cp ~/.kube/config ~/.kube/config.backup
   
   # Get new kubeconfig with VIP endpoint
   talosctl --context omni kubeconfig ~/.kube/config-vip
   
   # Merge or replace
   mv ~/.kube/config-vip ~/.kube/config
   
   # Test
   kubectl cluster-info
   # Should show: https://192.168.10.199:6443
   ```

## Verification Checklist

- [ ] Gateway API CRDs installed
- [ ] Cilium pods running (check `kubectl get pods -n kube-system`)
- [ ] All nodes show Ready status
- [ ] VIP Service has EXTERNAL-IP 192.168.10.199
- [ ] Can curl https://192.168.10.199:6443/healthz successfully
- [ ] Omni cluster endpoint updated to VIP
- [ ] New kubeconfig uses VIP endpoint
- [ ] Cilium status shows healthy (`cilium-dbg status`)

## Troubleshooting

### Cilium Pods CrashLooping

**Check logs**:
```bash
kubectl logs -n kube-system ds/cilium --tail=50
```

**Common issue**: Can't reach API server
- Verify `k8sServiceHost: localhost` and `k8sServicePort: 7445` in values
- Check Talos API is accessible: `talosctl --context omni version`

### VIP Not Getting External IP

**Check IP pool and policy**:
```bash
kubectl describe ciliumloadbalancerippool control-plane-vip-pool -n kube-system
kubectl describe ciliuml2announcementpolicy control-plane-l2-policy -n kube-system
```

**Verify L2 announcements are enabled**:
```bash
kubectl exec -n kube-system ds/cilium -- cilium-dbg status | grep -i l2
```

### Nodes Still NotReady

**Check CNI status**:
```bash
# From any node
talosctl --context omni -n <node-ip> get links

# Check for cilium interfaces
kubectl exec -n kube-system ds/cilium -- cilium-dbg status
```

### VIP Not Accessible from Outside Cluster

**Check L2 announcements are reaching network**:
- L2 announcements only work on same L2 network segment
- Verify interface selector in `control-plane-l2-policy.yaml` matches your nodes
- Default `e*` matches `eth0`, `eno1`, `enp*` interfaces
- Check with: `ip link show` on nodes

## Network Architecture

```
                   ┌─────────────────────────┐
                   │   192.168.10.199:6443   │
                   │  (Cilium VIP Service)   │
                   └───────────┬─────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
    ┌─────▼──────┐      ┌─────▼──────┐      ┌─────▼──────┐
    │ Control-01 │      │ Control-02 │      │ Control-03 │
    │ .10.100:6443│      │ .10.101:6443│      │ .10.102:6443│
    └────────────┘      └────────────┘      └────────────┘
         │                    │                    │
         └────────────────────┴────────────────────┘
                              │
                    Cilium L2 Announcement
                    (Active on one node at a time)
```

## Post-Installation: Bootstrap ArgoCD

Once Cilium is healthy and nodes are Ready:

```bash
# Bootstrap ArgoCD to manage everything else
kustomize build infrastructure/controllers/argocd --enable-helm | kubectl apply -f -
kubectl wait --for condition=established --timeout=60s crd/applications.argoproj.io
kubectl wait --for=condition=Available deployment/argocd-server -n argocd --timeout=300s
kubectl apply -f infrastructure/controllers/argocd/root.yaml

# Watch ArgoCD sync all applications
kubectl get applications -n argocd -w
```

## Key Differences: Omni vs Traditional Talos

| Aspect | Traditional (talhelper) | Omni-Managed |
|--------|------------------------|--------------|
| **Initial API access** | Direct to control plane node | Via Omni proxy |
| **Cilium k8sServiceHost** | `localhost:7445` ✅ | `localhost:7445` ✅ |
| **VIP configuration** | In talconfig.yaml | In Cilium manifests |
| **Endpoint updates** | Edit talconfig, regenerate | Update in Omni UI |
| **Node management** | talosctl + files | Omni UI + talosctl |

## Configuration Files Reference

All files are in `infrastructure/networking/cilium/`:

- `values.yaml` - Main Cilium Helm values
- `kube-apiserver-vip.yaml` - LoadBalancer Service for control plane
- `vip-pool.yaml` - IP pool for VIP (192.168.10.199)
- `control-plane-l2-policy.yaml` - L2 announcement policy
- `ip-pool.yaml` - General LoadBalancer IP pool (192.168.10.50-192.168.10.99)
- `l2-policy.yaml` - General L2 announcement policy
- `kustomization.yaml` - Combines everything

## Next Steps

After successful Cilium installation:

1. ✅ VIP is working
2. ✅ Nodes are Ready
3. ✅ Bootstrap ArgoCD (see above)
4. ✅ ArgoCD will deploy remaining infrastructure
5. ✅ Profit! 🎉

## References

- [Cilium L2 Announcements](https://docs.cilium.io/en/stable/network/l2-announcements/)
- [Cilium LoadBalancer IPAM](https://docs.cilium.io/en/stable/network/lb-ipam/)
- [Talos with Cilium](https://www.talos.dev/latest/kubernetes-guides/network/deploying-cilium/)
- [Omni Documentation](https://omni.siderolabs.com/docs/)
