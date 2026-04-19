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
- Pool: `192.168.10.32/27` → `192.168.10.32` – `192.168.10.63` (32 addresses, configured in `cilium/ip-pool.yaml`)
- `allowFirstLastIPs: "No"` — `.32` and `.63` are reserved for network/broadcast, not used
- Current assignments:
  - `192.168.10.49` — `gateway-external`
  - `192.168.10.50` — `gateway-internal`
  - `192.168.10.51` — `project-zomboid` (UDP game server)
- Managed by: Cilium L2 announcements (`cilium/l2-policy.yaml`)

### Adding a new LoadBalancer IP

Most apps should use Gateway API (HTTPRoute on the existing
`gateway-external` or `gateway-internal`) rather than claim a fresh LB IP —
it's one IP per gateway, not per app. Reserve direct `LoadBalancer`
Services for protocols Gateway API can't carry (UDP, TCP non-HTTP,
custom).

1. **Pick an IP in the pool range.** Anything in `192.168.10.33` –
   `192.168.10.62` that isn't already listed above. `kubectl get svc -A -o wide`
   will show assigned LBs.
2. **Pin the IP explicitly** on the Service (so it survives a cluster
   rebuild without re-shuffling):
   ```yaml
   apiVersion: v1
   kind: Service
   metadata:
     name: my-service
     annotations:
       lbipam.cilium.io/ips: "192.168.10.52"   # pin this IP
   spec:
     type: LoadBalancer
     ports: [...]
   ```
3. **Update this README's assignment table** and the comment block in
   `cilium/ip-pool.yaml` so the next person knows the IP is taken.
4. **Expand the pool if you run out.** Edit `cilium/ip-pool.yaml` and
   add another `cidr:` block — e.g., `192.168.10.64/27` for another 32
   addresses. Make sure the range is free in the Firewalla DHCP config
   before expanding, or you'll fight with DHCP leases.
5. **If the IP must be LAN-reachable from outside the cluster subnet,**
   also check `cilium/l2-policy.yaml` — the L2 announcement policy
   selects which interfaces advertise which pools. By default every
   node's primary interface announces the whole pool.

### Why a `/27` and not the whole /24?

The Firewalla DHCP pool covers most of `192.168.10.0/24`. Carving out a
dedicated `/27` for LoadBalancer IPs prevents DHCP from ever handing
`192.168.10.49` to a random IoT device. If you expand, pick another
DHCP-excluded block — don't just enlarge the CIDR.

### Node Network
- CIDR: `192.168.10.0/24`
- Static IPs configured in Omni machine configs

## Talos 1.13 compatibility notes

The cluster runs Talos 1.13 (migrated from 1.12 in April 2026). Key
networking-adjacent gotchas for that migration:

- **KubePrism port (`7445`) is unchanged** across 1.12 → 1.13. Existing
  Cilium values (`k8sServiceHost: localhost`, `k8sServicePort: 7445`)
  don't need touching.
- **Cilium 1.19.x** is the tested pairing with Talos 1.13 in this repo
  (`infrastructure/networking/cilium/kustomization.yaml` pins 1.19.3).
  Older Cilium 1.17/1.18 may boot, but Hubble TLS behavior changed
  enough that mixing versions during a rolling upgrade caused cert
  issues — don't cross-version unless you plan to reinstall Cilium.
- **`machine.install.disk`** is now mandatory on 1.13 (new
  LifecycleService API). This is networking-adjacent only because a
  missing disk patch keeps the LoadBalancer unhealthy forever —
  symptoms look like "L2 isn't announcing" when the real cause is that
  nodes never made it out of `UPGRADING`. See the root README for the
  fix (already applied in `omni/cluster-template/cluster-template.yaml`).
- **NVIDIA OSS driver migration** (in progress) changes the GPU
  worker's extension set but doesn't change its networking posture —
  node IP, L2 membership, and Cilium pod CIDR are unaffected.

## References

- [Talos + Cilium Official Guide](https://www.talos.dev/v1.13/kubernetes-guides/network/cilium/)
- [Cilium kube-proxy Replacement](https://docs.cilium.io/en/stable/network/kubernetes/kubeproxy-free/)
- [Gateway API Documentation](https://gateway-api.sigs.k8s.io/)
- [Cilium L2 Announcements](https://docs.cilium.io/en/stable/network/l2-announcements/)
- [Omni Config Patches](https://omni.siderolabs.com/docs/how-to-guides/how-to-configure-machines/)
