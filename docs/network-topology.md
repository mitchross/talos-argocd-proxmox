# Network Topology

## Overview

The cluster uses two separate networks:
1. **Main LAN (192.168.10.0/24)** - 2.5G over switch - all cluster traffic, API, etc.
2. **Storage Network (172.31.250.0/24)** - 10G DAC point-to-point - fast NFS/iSCSI to TrueNAS

## Physical Topology

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              NETWORK TOPOLOGY                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────────┐         10G DAC (Direct)        ┌─────────────────┐   │
│   │    Proxmox      │◄───────────────────────────────►│    TrueNAS      │   │
│   │   hp-server-1   │      172.31.250.2/24            │   192.168.10.133│   │
│   │                 │         ↕                       │                 │   │
│   │  vmbr1 (eno49)  │      172.31.250.1/24            │  enp67s0 (10G)  │   │
│   │                 │      (no switch!)               │                 │   │
│   └────────┬────────┘                                 └────────┬────────┘   │
│            │                                                   │            │
│   vmbr0    │  192.168.10.14/24                                │ 192.168.10.133
│   (ens2)   │                                                   │ (2.5G)     │
│            │                                                   │            │
│            ▼                                                   ▼            │
│   ┌────────────────────────────────────────────────────────────────────┐   │
│   │                     2.5G SWITCH (Main LAN)                          │   │
│   │                       192.168.10.0/24                               │   │
│   └────────────────────────────────────────────────────────────────────┘   │
│            │              │              │              │                   │
│            ▼              ▼              ▼              ▼                   │
│   ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐      │
│   │ Control Plane│ │ Control Plane│ │ Control Plane│ │   Workers    │      │
│   │  .237        │ │  .76         │ │  .140        │ │ .164/.219/.159│     │
│   └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘      │
│                                                                              │
│   ┌──────────────────────────────────────────────────────────────────┐      │
│   │                        GPU Worker VM 100                          │      │
│   │  ┌─────────────────┐              ┌─────────────────┐            │      │
│   │  │ net0 (ens18)    │              │ net1 (ens19)    │            │      │
│   │  │ vmbr0 → Main LAN│              │ vmbr1 → 10G DAC │            │      │
│   │  │ 192.168.10.x    │              │ 172.31.250.10   │            │      │
│   │  │ (DHCP)          │              │ (Static)        │            │      │
│   │  │ *** PRIMARY *** │              │ Storage only!   │            │      │
│   │  └─────────────────┘              └─────────────────┘            │      │
│   └──────────────────────────────────────────────────────────────────┘      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## IP Assignments

### Main LAN (192.168.10.0/24)

| Device | IP | Purpose |
|--------|-----|---------|
| Router/Gateway | 192.168.10.1 | Default route |
| Proxmox (hp-server-1) | 192.168.10.14 | Hypervisor |
| TrueNAS | 192.168.10.133 | NAS (NFS/SMB/MinIO S3) |
| Control Plane 1 | 192.168.10.237 | K8s master |
| Control Plane 2 | 192.168.10.76 | K8s master |
| Control Plane 3 | 192.168.10.140 | K8s master |
| Worker 1 | 192.168.10.164 | K8s worker |
| Worker 2 | 192.168.10.219 | K8s worker |
| Worker 3 | 192.168.10.159 | K8s worker |
| GPU Worker | 192.168.10.x (DHCP) | K8s GPU worker - **must use this for kubelet** |
| Wyze Bridge | 192.168.10.46 | RTSP camera streams |
| LoadBalancer Pool | 192.168.10.32-63 (/27) | Cilium L2 announcements |

### Storage Network (172.31.250.0/24)

**Point-to-point 10G DAC - NO SWITCH**

| Device | IP | Interface | Purpose |
|--------|-----|-----------|---------|
| TrueNAS | 172.31.250.1 | enp67s0 (10G SFP+) | Storage server |
| Proxmox | 172.31.250.2 | eno49 → vmbr1 | Hypervisor |
| GPU Worker VM | 172.31.250.10 | ens19 (net1) | Fast storage access |

## Critical Configuration Notes

### GPU Worker Dual-NIC Setup

The GPU worker VM has two NICs:
- **net0 (ens18)** → vmbr0 → Main LAN (192.168.10.x) - **PRIMARY for Kubernetes**
- **net1 (ens19)** → vmbr1 → 10G Storage (172.31.250.x) - **Storage traffic only**

**IMPORTANT**: Kubernetes/kubelet MUST register with the 192.168.10.x address, NOT the 172.31.250.x address. The 10G network is isolated and only reaches TrueNAS.

### Why This Matters

If kubelet registers with 172.31.250.10:
- ❌ Other nodes can't reach it (different subnet, no routing)
- ❌ kubectl logs/exec fails (API server can't reach kubelet)
- ❌ Pods scheduled there become unreachable
- ❌ Services don't work

### Talos Configuration Requirements

```yaml
machine:
  network:
    interfaces:
      - interface: ens18        # Main LAN - must be primary
        dhcp: true
        routes:
          - network: 0.0.0.0/0  # Default route MUST go through main LAN
            gateway: 192.168.10.1
      - interface: ens19        # 10G storage - secondary
        dhcp: false
        addresses:
          - 172.31.250.10/24
        # NO default route here!
  kubelet:
    nodeIP: <192.168.10.x>      # Force kubelet to use main LAN IP
```

## Proxmox Bridge Configuration

| Bridge | Physical NIC | CIDR | Purpose |
|--------|--------------|------|---------|
| vmbr0 | ens2 | 192.168.10.14/24 | Main LAN |
| vmbr1 | eno49 | 172.31.250.2/24 | 10G DAC to TrueNAS |

## TrueNAS Network Configuration

| Interface | IP | Speed | Purpose |
|-----------|-----|-------|---------|
| enp67s0 | 172.31.250.1/24 | 10G SFP+ DAC | Fast storage (Proxmox direct) |
| enp67s0d1 | - | 10G SFP+ | Unused (second port) |
| enx04421a41f284 | 192.168.10.133/24 | 2.5G USB | Main LAN access |

## Whitelisted Storage Access

The Cilium network policy allows these storage connections:

| Destination | Ports | Purpose |
|-------------|-------|---------|
| 192.168.10.133 | 2049, 111 | NFS |
| 192.168.10.133 | 445 | SMB |
| 192.168.10.133 | 9000 | MinIO S3 |
| 172.31.250.1 | 2049, 445, 9000 | 10G storage (GPU worker only) |

## Troubleshooting

### GPU Worker Shows Wrong IP

If `kubectl get nodes -o wide` shows 172.31.250.10 for GPU worker:

1. Check if DHCP is working on ens18
2. Verify default route goes through 192.168.10.1
3. Force kubelet nodeIP in Talos config
4. Reboot the node after config changes

### Can't Reach GPU Worker

```bash
# From another node, test connectivity
ping 192.168.10.x    # Should work (main LAN)
ping 172.31.250.10   # Will fail (different subnet, no routing)
```

### Storage Performance Testing

```bash
# Test 10G link from GPU worker to TrueNAS
kubectl exec -n <ns> <gpu-pod> -- dd if=/dev/zero of=/mnt/nfs/test bs=1G count=1
# Should see ~1GB/s+ throughput on 10G link
```
