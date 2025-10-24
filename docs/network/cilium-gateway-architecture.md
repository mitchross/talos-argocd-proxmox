# Cilium Gateway Architecture - Quick Reference

## Overview

This document provides a quick reference for understanding how Cilium Gateway API works with L2 announcements in this cluster.

## Traffic Flow - externalTrafficPolicy: Local (CURRENT - CORRECT)

```
┌─────────────────────────────────────────────────────────────────────┐
│ Client (192.168.10.x)                                               │
└──────────────────┬──────────────────────────────────────────────────┘
                   │
                   │ 1. ARP: Who has 192.168.10.50?
                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│ L2 Network (192.168.10.0/24)                                        │
│                                                                     │
│ ┌─────────────────────────────────────────────────────────────┐   │
│ │ Cilium L2 Announcement: Worker Node 2 announces 192.168.10.50│   │
│ └─────────────────────────────────────────────────────────────┘   │
└──────────────────┬──────────────────────────────────────────────────┘
                   │
                   │ 2. ARP Reply: I have 192.168.10.50
                   │    MAC: aa:bb:cc:dd:ee:02 (Worker Node 2)
                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Worker Node 2 (192.168.10.112)                                      │
│                                                                     │
│  3. Packet arrives at ens18 interface                               │
│     eBPF intercepts at TC hook                                      │
│                                                                     │
│  4. externalTrafficPolicy: Local                                    │
│     ✅ NO SNAT - source IP preserved                                │
│     ✅ Routes ONLY to local cilium-envoy pod                        │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ cilium-envoy Pod (running on THIS node)                      │  │
│  │                                                               │  │
│  │  5. Envoy receives request with original source IP           │  │
│  │  6. Matches HTTPRoute based on Host header                   │  │
│  │  7. Routes to backend service ClusterIP                      │  │
│  └──────────────────┬───────────────────────────────────────────┘  │
└─────────────────────┼───────────────────────────────────────────────┘
                      │
                      │ 8. Service load balances to backend pod
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Backend Pod (argocd-server, longhorn-frontend, etc.)               │
│                                                                     │
│  Pod can see original client IP (192.168.10.x)                     │
│  Connection tracking is consistent                                 │
│  Session affinity works correctly                                  │
└─────────────────────────────────────────────────────────────────────┘
```

## Traffic Flow - externalTrafficPolicy: Cluster (OLD - BROKEN)

```
┌─────────────────────────────────────────────────────────────────────┐
│ Client (192.168.10.x)                                               │
└──────────────────┬──────────────────────────────────────────────────┘
                   │
                   │ 1. ARP: Who has 192.168.10.50?
                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│ L2 Network (192.168.10.0/24)                                        │
│                                                                     │
│ ┌─────────────────────────────────────────────────────────────┐   │
│ │ Cilium L2 Announcement: Worker Node 2 announces 192.168.10.50│   │
│ └─────────────────────────────────────────────────────────────┘   │
└──────────────────┬──────────────────────────────────────────────────┘
                   │
                   │ 2. ARP Reply: I have 192.168.10.50
                   │    MAC: aa:bb:cc:dd:ee:02 (Worker Node 2)
                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Worker Node 2 (192.168.10.112)                                      │
│                                                                     │
│  3. Packet arrives at ens18 interface                               │
│     eBPF intercepts at TC hook                                      │
│                                                                     │
│  4. externalTrafficPolicy: Cluster                                  │
│     ❌ SNAT applied - source IP changed to node IP (192.168.10.112) │
│     ❌ Can route to ANY cilium-envoy pod on ANY node                │
│     ❌ Different requests hit different envoy pods                  │
│                                                                     │
│     Round-robin across ALL envoy pods:                              │
│     ├─> cilium-envoy on Worker Node 1                              │
│     ├─> cilium-envoy on Worker Node 2   ← Same client, different   │
│     ├─> cilium-envoy on Worker Node 3      envoy = broken session  │
│     └─> cilium-envoy on Worker Node 4                              │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
│                                                                     │
│ PROBLEM: Connection tracking broken                                │
│ - Browser A hits envoy-1 (works)                                   │
│ - Browser B hits envoy-3 (fails)                                   │
│ - Same browser, different requests hit different envoys            │
│ - WebSocket upgrades fail                                          │
│ - Session cookies don't work                                       │
└─────────────────────────────────────────────────────────────────────┘
```

## Architecture Components

### 1. Cilium Envoy DaemonSet

```yaml
# Deployed automatically by Cilium when Gateway API is enabled
DaemonSet: cilium-envoy (runs on ALL nodes, including control plane)
Pods: 7 (one per node in this cluster)
```

**Why DaemonSet?**
- Every node needs an envoy pod for `externalTrafficPolicy: Local` to work
- When L2 announcement happens from Node X, traffic must hit envoy on Node X

### 2. Gateway LoadBalancer Services

```yaml
# Created automatically by Cilium Gateway controller
Service: cilium-gateway-gateway-internal
  Type: LoadBalancer
  externalTrafficPolicy: Local  # ← CRITICAL
  sessionAffinity: ClientIP     # ← IMPORTANT
  sessionAffinityTimeoutSeconds: 10800
  Ports: 80, 443
  Selector: io.cilium.gateway/owning-gateway: gateway-internal

Service: cilium-gateway-gateway-external
  Type: LoadBalancer
  externalTrafficPolicy: Local  # ← CRITICAL
  sessionAffinity: ClientIP     # ← IMPORTANT
  sessionAffinityTimeoutSeconds: 10800
  Ports: 80, 443
  Selector: io.cilium.gateway/owning-gateway: gateway-external
```

**How it works**:
1. Gateway controller creates LoadBalancer service
2. Cilium LB-IPAM assigns IP from pool (192.168.10.49 or .50)
3. L2 announcement makes ONE node respond to ARP for that IP
4. `externalTrafficPolicy: Local` ensures traffic stays on that node
5. Service selector targets cilium-envoy pods with matching gateway label

### 3. L2 Announcement Policy

```yaml
# infrastructure/networking/cilium/l2-policy.yaml
apiVersion: cilium.io/v2alpha1
kind: CiliumL2AnnouncementPolicy
metadata:
  name: l2-policy
spec:
  interfaces:
    - ^e.*  # Match: ens18, eth0, eno1, enp*, etc.
  loadBalancerIPs: true
  nodeSelector:
    matchExpressions:
      - key: node-role.kubernetes.io/control-plane
        operator: DoesNotExist  # Worker nodes only
```

**Important**: Only ONE policy should exist. Having multiple policies causes ARP conflicts.

### 4. IP Pool

```yaml
# infrastructure/networking/cilium/ip-pool.yaml
apiVersion: cilium.io/v2alpha1
kind: CiliumLoadBalancerIPPool
metadata:
  name: first-pool
spec:
  blocks:
    - cidr: "192.168.10.32/27"  # .32 to .63
  allowFirstLastIPs: "No"
  serviceSelector:
    matchLabels: {}  # Apply to all LoadBalancer services
```

## Configuration Matrix

| Setting | Old (Broken) | New (Fixed) | Impact |
|---------|--------------|-------------|---------|
| `externalTrafficPolicy` | Cluster | **Local** | Prevents SNAT, preserves source IP |
| `sessionAffinity` | None | **ClientIP** | Same client → same envoy pod |
| `sessionAffinityTimeoutSeconds` | N/A | **10800** | 3-hour session stickiness |
| `operator.replicas` | 1 | **2** | Eliminates single point of failure |
| L2 Announcement Policies | 2 (duplicate) | **1** | Prevents ARP conflicts |
| `bandwidthManager.enabled` | false | **true** | Better TCP performance |
| `bandwidthManager.bbr` | false | **true** | BBR congestion control |

## Troubleshooting Decision Tree

```
Is connectivity intermittent?
│
├─ YES → Check externalTrafficPolicy
│        kubectl get svc -n gateway -o yaml | grep externalTrafficPolicy
│        │
│        ├─ Shows "Cluster" → PROBLEM FOUND
│        │  Fix: Apply updated cilium values.yaml
│        │
│        └─ Shows "Local" → Check next issue
│           │
│           ├─ Check duplicate L2 policies
│           │  kubectl get ciliuml2announcementpolicy -A
│           │  Should show only ONE policy
│           │
│           └─ Check session affinity
│              kubectl get svc -n gateway -o yaml | grep sessionAffinity
│              Should show: sessionAffinity: ClientIP
│
└─ NO → Check other issues
    │
    ├─ DNS resolution issues?
    │  → Check CoreDNS
    │
    ├─ HTTPRoute not found?
    │  → kubectl get httproute -A
    │
    └─ Backend pods down?
       → kubectl get pods -A
```

## Quick Health Check Commands

```bash
# 1. Verify Cilium is healthy
kubectl exec -n kube-system ds/cilium -- cilium status | grep -E "KubeProxyReplacement|Gateway|L2"

# 2. Check gateway services have correct settings
kubectl get svc -n gateway -o yaml | grep -A2 externalTrafficPolicy

# 3. Verify only one L2 announcement policy exists
kubectl get ciliuml2announcementpolicy -A

# 4. Check which node is announcing which VIP
kubectl exec -n kube-system ds/cilium -- cilium bpf lb list | grep -E "192.168.10.49|192.168.10.50"

# 5. Verify operator has 2 replicas
kubectl get deployment -n kube-system cilium-operator

# 6. Test connectivity
curl -v https://argocd.vanillax.me
```

## Performance Tuning Applied

### 1. Bandwidth Manager with BBR

```yaml
bandwidthManager:
  enabled: true
  bbr: true  # Bottleneck Bandwidth and Round-trip propagation time
```

**Benefits**:
- 2-5x better throughput on high-latency connections
- Better handling of packet loss
- Faster ramp-up to available bandwidth

### 2. Connection Tracking Timeouts

```yaml
bpf:
  ctTcpTimeout: 21600  # 6 hours (up from default)
  ctAnyTimeout: 3600   # 1 hour for non-TCP
```

**Benefits**:
- Long-lived HTTP/2 connections don't get dropped
- WebSocket connections stay alive
- Reduces unnecessary connection resets

### 3. Session Affinity

```yaml
sessionAffinity: true
sessionAffinityTimeoutSeconds: 10800  # 3 hours
```

**Benefits**:
- Same client always routes to same backend during session
- Survives L2 announcement migrations
- Reduces connection churn

## Files Modified (2025-10-23)

1. `infrastructure/networking/cilium/values.yaml`
   - Added `gatewayAPI.externalTrafficPolicy: Local`
   - Added `gatewayAPI.sessionAffinity: true`
   - Changed `operator.replicas` from 1 to 2
   - Added operator pod anti-affinity
   - Added `bandwidthManager` config
   - Added BPF connection tracking timeouts

2. `infrastructure/networking/cilium/kustomization.yaml`
   - Removed `l2-announcement.yaml` from resources

3. `infrastructure/networking/cilium/l2-announcement.yaml`
   - Renamed to `l2-announcement.yaml.disabled`

## Summary

**Root cause**: `externalTrafficPolicy: Cluster` with L2 LoadBalancer caused SNAT and inconsistent routing to Envoy pods.

**Fix**: Changed to `externalTrafficPolicy: Local` to keep traffic on the L2-announcing node and route to local Envoy only.

**Result**: Consistent, reliable connectivity with proper source IP preservation and session handling.
