# Network Architecture

## Overview

This cluster uses a modern, high-performance networking stack:

- **Cilium** - CNI with kube-proxy replacement
- **KubePrism** - Control plane load balancer (Talos built-in)
- **Gateway API** - Modern ingress (replaces Ingress resources)
- **L2 Announcements** - LoadBalancer IP management
- **Sidero Omni** - Cluster management via SideroLink

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│  Management Plane (Sidero Omni)                            │
│  ───────────────────────────────────────────────────────   │
│  Protocol: WireGuard (SideroLink)                          │
│  Ports: 8090 (API), 8091 (Events), 8092 (Logs)            │
│  Purpose: Cluster management, machine provisioning         │
│  Independent: Does NOT use Kubernetes Services             │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Control Plane Load Balancing (KubePrism)                  │
│  ───────────────────────────────────────────────────────   │
│  Endpoint: localhost:7445 (each node)                      │
│  Purpose: HA load balancing for Kubernetes API Server      │
│  Backends: All control plane nodes (port 6443)             │
│  Clients: kubelet, Cilium, kubectl (via Omni)              │
│  Technology: Talos built-in proxy                          │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Data Plane (Cilium)                                        │
│  ───────────────────────────────────────────────────────   │
│  CNI: Pod networking (10.244.0.0/16)                       │
│  Service LB: ClusterIP, LoadBalancer (replaces kube-proxy) │
│  Gateway API: HTTPRoute, TLS termination                   │
│  L2 Announcements: LoadBalancer IPs (192.168.10.49-50)    │
│  Network Policy: Security rules                            │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  kube-proxy                                                 │
│  ───────────────────────────────────────────────────────   │
│  Status: ❌ DISABLED (must be disabled)                    │
│  Reason: Cilium replaces it entirely                       │
│  Conflict: If enabled, fights with Cilium over ports       │
│  Config: See omni/disable-kube-proxy.yaml                  │
└─────────────────────────────────────────────────────────────┘
```

## Critical Configuration: kube-proxy MUST be Disabled

### Why?

Cilium is configured with `kubeProxyReplacement: true` (see `cilium/values.yaml:12`).

When kube-proxy is also running:
- ❌ Both try to manage LoadBalancer health check ports
- ❌ Gateway services fail with "address already in use"
- ❌ ArgoCD, Longhorn, other services become unreachable
- ❌ Random connection resets and 503 errors

### The Fix

**File**: `../../omni/disable-kube-proxy.yaml`

This **MUST** be applied as a config patch to all machines in Omni UI.

```yaml
cluster:
  proxy:
    disabled: true
```

See `../../omni/README.md` for complete instructions.

## Component Responsibilities

### Sidero Omni (Management)

**What it handles:**
- Machine provisioning and lifecycle
- Cluster configuration
- Metrics and logs collection
- Remote cluster access

**What it does NOT use:**
- Kubernetes Services ❌
- kube-proxy ❌
- Cilium ❌

**Communication:**
- Direct WireGuard tunnels (SideroLink)
- gRPC on dedicated ports (8090-8092)

### KubePrism (Control Plane HA)

**What it handles:**
- Load balancing to Kubernetes API servers
- HA failover if control plane nodes fail
- Local endpoint on each node (localhost:7445)

**Used by:**
- kubelet (node → API server)
- Cilium agent (CNI → API server)
- kubectl (when connecting via Omni)
- Other system components

**Configuration:**
```yaml
# In Cilium values.yaml
k8sServiceHost: localhost
k8sServicePort: "7445"

# In Talos machine config (all nodes)
machine:
  features:
    kubePrism:
      enabled: true
      port: 7445
```

### Cilium (Data Plane)

**What it handles:**
1. **CNI** - Pod networking
   - IPAM (IP address management)
   - Pod-to-pod communication
   - Network policies

2. **Service Load Balancing** (replaces kube-proxy)
   - ClusterIP services
   - NodePort services
   - LoadBalancer services
   - Session affinity

3. **Gateway API**
   - HTTPRoute (modern Ingress)
   - TLS termination
   - HTTP/gRPC routing

4. **L2 Announcements**
   - LoadBalancer IP advertisement
   - ARP/NDP for local network

**Configuration:**
- Primary: `cilium/values.yaml`
- L2 Policy: `cilium/l2-policy.yaml`
- IP Pools: `cilium/ip-pool.yaml`

### Gateway API

**What it provides:**
- Modern replacement for Ingress
- Better routing capabilities
- Cross-namespace routing
- More expressive API

**Resources in this cluster:**
- `gateway/gateway-internal.yaml` - Internal services (192.168.10.50)
- `gateway/gateway-external.yaml` - External services (192.168.10.49)

**HTTPRoutes:**
- ArgoCD: `argocd.vanillax.me`
- Longhorn: `longhorn.vanillax.me`
- Many others...

## Network Flow Examples

### User → ArgoCD Web UI

```
User Browser
    ↓ DNS: argocd.vanillax.me → 192.168.10.50
Cilium Gateway (192.168.10.50:443)
    ↓ TLS termination
    ↓ HTTPRoute: argocd-server service
Cilium Service LB
    ↓ Load balance across pods
ArgoCD Server Pod
```

### Pod → External API

```
Application Pod (10.244.x.x)
    ↓ NAT via Cilium BPF
    ↓ Source IP changed to node IP
External API
```

### Kubelet → API Server

```
kubelet
    ↓ Connect to localhost:7445
KubePrism (on same node)
    ↓ Load balance to control plane
    ↓ Round-robin across all control plane nodes
API Server (one of 3 control plane nodes)
```

## Troubleshooting

### Gateway services failing

**Symptoms:**
```
Warning FailedToStartServiceHealthcheck
node X failed to start healthcheck on port 31245: bind: address already in use
```

**Cause:** kube-proxy is running (conflicts with Cilium)

**Fix:** Apply `../../omni/disable-kube-proxy.yaml` to all machines in Omni

**Verify fix:**
```bash
# Should return NO pods
kubectl get pods -n kube-system -l k8s-app=kube-proxy

# Should show no port conflict errors
kubectl get events -n gateway --field-selector type=Warning
```

### Services not accessible

**Check Cilium:**
```bash
# All pods should be Running
kubectl get pods -n kube-system -l k8s-app=cilium

# Check status
kubectl exec -n kube-system ds/cilium -- cilium status

# Check connectivity
kubectl exec -n kube-system ds/cilium -- cilium connectivity test
```

**Check Gateway:**
```bash
# Gateways should show PROGRAMMED=True
kubectl get gateway -A

# HTTPRoutes should show Accepted
kubectl get httproute -A
```

### L2 Announcements not working

**Check L2 policy:**
```bash
kubectl get ciliuml2announcementpolicy -A
kubectl get ciliumloadbalancerippool -A
```

**Check ARP announcements:**
```bash
# From external host on same network
ping 192.168.10.50
arp -a | grep 192.168.10.50
```

## Performance Tuning

### Socket-level Load Balancing

Enabled in Cilium for better pod-to-service performance:
```yaml
socketLB:
  enabled: true
  hostNamespaceOnly: false
```

### Bandwidth Manager

BBR congestion control for better TCP throughput:
```yaml
bandwidthManager:
  enabled: true
  bbr: true
```

### Connection Tracking

Optimized timeouts for long-lived connections:
```yaml
bpf:
  ctTcpTimeout: 21600  # 6 hours
  ctAnyTimeout: 3600   # 1 hour
```

### Gateway Session Affinity

Sticky sessions for 3 hours:
```yaml
gatewayAPI:
  sessionAffinity: true
  sessionAffinityTimeoutSeconds: 10800
```

## IP Address Allocation

### Pod Network
- CIDR: `10.244.0.0/16`
- Managed by: Cilium IPAM

### Service Network
- CIDR: `10.96.0.0/12`
- Managed by: Kubernetes API + Cilium

### LoadBalancer IPs
- Pool: `192.168.10.49-50` (configured in `cilium/ip-pool.yaml`)
- Assignment:
  - `192.168.10.49` - gateway-external
  - `192.168.10.50` - gateway-internal
- Managed by: Cilium L2 announcements

### Node Network
- CIDR: `192.168.10.0/24`
- Static IPs configured in Omni machine configs

## References

- [Talos + Cilium Official Guide](https://www.talos.dev/v1.11/kubernetes-guides/network/cilium/)
- [Cilium kube-proxy Replacement](https://docs.cilium.io/en/stable/network/kubernetes/kubeproxy-free/)
- [Gateway API Documentation](https://gateway-api.sigs.k8s.io/)
- [Cilium L2 Announcements](https://docs.cilium.io/en/stable/network/l2-announcements/)
- [Omni Config Patches](https://omni.siderolabs.com/docs/how-to-guides/how-to-configure-machines/)
