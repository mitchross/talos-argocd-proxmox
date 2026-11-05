# Network architecture

## Overview

The cluster networking stack has five parts:

- Cilium: CNI with kube-proxy replacement
- KubePrism: control plane load balancer (Talos built-in)
- Gateway API: ingress (replaces Ingress resources)
- L2 Announcements: LoadBalancer IP management
- Sidero Omni: cluster management via SideroLink

## Architecture diagram

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
│  L2 Announcements: LoadBalancer IPs (192.168.10.49-52)    │
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

## Critical configuration: kube-proxy must be disabled

### Why?

Cilium is configured with `kubeProxyReplacement: true` (see `cilium/values.yaml:12`).

When kube-proxy also runs:
- Both try to manage LoadBalancer health check ports.
- Gateway services fail with "address already in use".
- ArgoCD, Longhorn, and other services become unreachable.
- Connections reset at random and return 503 errors.

### The Fix

File: `../../omni/disable-kube-proxy.yaml`

Apply it as a config patch to all machines in the Omni UI. This is **required**.

```yaml
cluster:
  proxy:
    disabled: true
```

See `../../omni/README.md` for full instructions.

## Component responsibilities

### Sidero Omni (Management)

What it handles:
- Machine provisioning and lifecycle
- Cluster configuration
- Metrics and logs collection
- Remote cluster access

What it does not use:
- Kubernetes Services
- kube-proxy
- Cilium

Communication:
- Direct WireGuard tunnels (SideroLink)
- gRPC on dedicated ports (8090-8092)

### KubePrism (Control Plane HA)

What it handles:
- Load balancing to Kubernetes API servers
- HA failover if control plane nodes fail
- Local endpoint on each node (localhost:7445)

Used by:
- kubelet (node → API server)
- Cilium agent (CNI → API server)
- kubectl (when connecting via Omni)
- Other system components

Configuration:
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

What it handles:
1. CNI: pod networking
   - IPAM (IP address management)
   - Pod-to-pod communication
   - Network policies

2. Service load balancing (replaces kube-proxy)
   - ClusterIP services
   - NodePort services
   - LoadBalancer services
   - Session affinity

3. Gateway API
   - HTTPRoute (replaces Ingress)
   - TLS termination
   - HTTP/gRPC routing

4. L2 Announcements
   - LoadBalancer IP advertisement
   - ARP/NDP for local network

Configuration:
- Primary: `cilium/values.yaml`
- L2 Policy: `cilium/l2-policy.yaml`
- IP Pools: `cilium/ip-pool.yaml`

### Gateway API

What it provides:
- A replacement for Ingress
- More routing options
- Cross-namespace routing
- A more expressive API

Resources in this cluster:
- `gateway/gateway-internal-technitium.yaml` - Internal services, split-DNS (192.168.10.52)
- `gateway/gateway-external.yaml` - External services (192.168.10.49)

HTTPRoutes:
- ArgoCD: `argocd.vanillax.me`
- Longhorn: `longhorn.vanillax.me`
- Many others...

## Network flow examples

### User → ArgoCD Web UI

```
User Browser
    ↓ DNS: argocd.vanillax.me → 192.168.10.52
Cilium Gateway (192.168.10.52:443)
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

Symptoms:
```
Warning FailedToStartServiceHealthcheck
node X failed to start healthcheck on port 31245: bind: address already in use
```

Cause: kube-proxy is running and conflicts with Cilium.

Fix: Apply `../../omni/disable-kube-proxy.yaml` to all machines in Omni.

Verify the fix:
```bash
# Should return NO pods
kubectl get pods -n kube-system -l k8s-app=kube-proxy

# Should show no port conflict errors
kubectl get events -n gateway --field-selector type=Warning
```

### Services not accessible

Check Cilium:
```bash
# All pods should be Running
kubectl get pods -n kube-system -l k8s-app=cilium

# Check status
kubectl exec -n kube-system ds/cilium -- cilium status

# Check connectivity
kubectl exec -n kube-system ds/cilium -- cilium connectivity test
```

Check Gateway:
```bash
# Gateways should show PROGRAMMED=True
kubectl get gateway -A

# HTTPRoutes should show Accepted
kubectl get httproute -A
```

### L2 Announcements not working

Check L2 policy:
```bash
kubectl get ciliuml2announcementpolicy -A
kubectl get ciliumloadbalancerippool -A
```

Check ARP announcements:
```bash
# From external host on same network
ping 192.168.10.52
arp -a | grep 192.168.10.52
```

## Performance tuning

### Socket-level load balancing

Cilium enables it for pod-to-service traffic:
```yaml
socketLB:
  enabled: true
  hostNamespaceOnly: false
```

### Bandwidth manager

BBR congestion control raises TCP throughput:
```yaml
bandwidthManager:
  enabled: true
  bbr: true
```

### Connection tracking

Long timeouts keep long-lived connections open:
```yaml
bpf:
  ctTcpTimeout: 21600  # 6 hours
  ctAnyTimeout: 3600   # 1 hour
```

### Gateway session affinity

Sessions stay sticky for 3 hours:
```yaml
gatewayAPI:
  sessionAffinity: true
  sessionAffinityTimeoutSeconds: 10800
```

## IP address allocation

### Pod network
- CIDR: `10.244.0.0/16`
- Managed by: Cilium IPAM

### Service network
- CIDR: `10.96.0.0/12`
- Managed by: Kubernetes API + Cilium

### LoadBalancer IPs
- Pool: `192.168.10.32/27` → `192.168.10.32` – `192.168.10.63` (32 addresses, configured in `cilium/ip-pool.yaml`)
- `allowFirstLastIPs: "No"`: `.32` and `.63` are reserved for network and broadcast, so they are not used
- Current assignments:
  - `192.168.10.49`: `gateway-external`
  - `192.168.10.50`: free
  - `192.168.10.51`: `project-zomboid` (UDP game server; archived, IP kept for its return)
  - `192.168.10.52`: `gateway-internal-technitium`
- Managed by: Cilium L2 announcements (`cilium/l2-policy.yaml`)

### Adding a new LoadBalancer IP

Most apps should use Gateway API instead of claiming a new LB IP. Use an HTTPRoute
on `gateway-external` for public routes or `gateway-internal-technitium` for
private routes. Each gateway takes one IP, not each app. Use direct `LoadBalancer`
Services only for protocols Gateway API can't carry (UDP, non-HTTP TCP, custom).

1. **Pick an IP in the pool range.** Use any IP in `192.168.10.33` –
   `192.168.10.62` not listed above. `kubectl get svc -A -o wide`
   shows assigned LBs.
2. **Pin the IP explicitly** on the Service, so it survives a cluster
   rebuild without changing:
   ```yaml
   apiVersion: v1
   kind: Service
   metadata:
     name: my-service
     annotations:
       lbipam.cilium.io/ips: "192.168.10.53"   # pin a currently free IP
   spec:
     type: LoadBalancer
     ports: [...]
   ```
3. **Update this README's assignment list** and the comment block in
   `cilium/ip-pool.yaml` so the next person knows the IP is taken.
4. **Expand the pool if you run out.** Edit `cilium/ip-pool.yaml` and
   add another `cidr:` block, for example `192.168.10.64/27` for another 32
   addresses. Make sure the range is free in the Firewalla DHCP config
   first, or DHCP leases will conflict.
5. **If the IP must be LAN-reachable from outside the cluster subnet,**
   also check `cilium/l2-policy.yaml`. The L2 announcement policy
   selects which interfaces advertise which pools. By default every
   node's primary interface announces the whole pool.

### Why a `/27` and not the whole /24?

The Firewalla DHCP pool covers most of `192.168.10.0/24`. A dedicated `/27` for
LoadBalancer IPs stops DHCP from handing `192.168.10.49` to a random IoT device.
If you expand, pick another DHCP-excluded block. Don't just enlarge the CIDR.

### Node network
- CIDR: `192.168.10.0/24`
- Static IPs configured in Omni machine configs

## Talos 1.13 compatibility notes

The cluster runs Talos 1.13 (migrated from 1.12 in April 2026). These
networking-adjacent gotchas came with that migration:

- **KubePrism port (`7445`) is unchanged** across 1.12 → 1.13. Existing
  Cilium values (`k8sServiceHost: localhost`, `k8sServicePort: 7445`)
  need no change.
- **Cilium 1.19.x** is the tested pairing with Talos 1.13 in this repo
  (`infrastructure/networking/cilium/kustomization.yaml` pins 1.19.3).
  Older Cilium 1.17/1.18 may boot, but Hubble TLS behavior changed.
  Mixing versions during a rolling upgrade caused cert issues. Don't
  cross-version unless you plan to reinstall Cilium.
- **`machine.install.disk`** is now mandatory on 1.13 (new
  LifecycleService API). It matters here because a missing disk patch keeps
  the LoadBalancer unhealthy forever. The symptoms look like "L2 isn't
  announcing", but the real cause is that nodes never left `UPGRADING`.
  See the root README for the fix (already applied in
  `omni/cluster-template/cluster-template-prod-v2.yaml`).
- **NVIDIA OSS driver migration** (in progress) changes the GPU
  worker's extension set. It does not change networking: node IP, L2
  membership, and Cilium pod CIDR are unaffected.

## References

- [Talos + Cilium Official Guide](https://www.talos.dev/v1.13/kubernetes-guides/network/cilium/)
- [Cilium kube-proxy Replacement](https://docs.cilium.io/en/stable/network/kubernetes/kubeproxy-free/)
- [Gateway API Documentation](https://gateway-api.sigs.k8s.io/)
- [Cilium L2 Announcements](https://docs.cilium.io/en/stable/network/l2-announcements/)
- [Omni Config Patches](https://omni.siderolabs.com/docs/how-to-guides/how-to-configure-machines/)
