# Network Topology

## Overview

The cluster uses a single network with 10G switch infrastructure:
- **Main LAN (192.168.10.0/24)** - All cluster traffic via 10G switch
- **TrueNAS Storage** - 192.168.10.133 (10G connected via switch)

## Physical Topology

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              NETWORK TOPOLOGY                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────────┐                                ┌─────────────────┐    │
│   │    Proxmox      │                                │    TrueNAS      │    │
│   │   hp-server-1   │                                │  192.168.10.133 │    │
│   │  192.168.10.14  │                                │                 │    │
│   └────────┬────────┘                                └────────┬────────┘    │
│            │ 10G                                              │ 10G         │
│            │                                                  │             │
│            ▼                                                  ▼             │
│   ┌────────────────────────────────────────────────────────────────────┐   │
│   │                        10G SWITCH                                   │   │
│   │                     192.168.10.0/24                                 │   │
│   └────────────────────────────────────────────────────────────────────┘   │
│            │              │              │              │                    │
│            ▼              ▼              ▼              ▼                    │
│   ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│   │ Control Plane│ │ Control Plane│ │ Control Plane│ │   Workers    │       │
│   │  .237        │ │  .76         │ │  .140        │ │ .164/.219/.159│      │
│   └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘       │
│                                                                              │
│   ┌──────────────────────────────────────────────────────────────────┐      │
│   │                        GPU Worker VM 100                          │      │
│   │  ┌─────────────────┐                                             │      │
│   │  │ net0 (ens18)    │                                             │      │
│   │  │ vmbr0 → 10G LAN │                                             │      │
│   │  │ 192.168.10.x    │                                             │      │
│   │  │ (DHCP)          │                                             │      │
│   │  └─────────────────┘                                             │      │
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
| TrueNAS | 192.168.10.133 | NAS (NFS/SMB/MinIO S3) - 10G |
| Control Plane 1 | 192.168.10.237 | K8s master |
| Control Plane 2 | 192.168.10.76 | K8s master |
| Control Plane 3 | 192.168.10.140 | K8s master |
| Worker 1 | 192.168.10.164 | K8s worker |
| Worker 2 | 192.168.10.219 | K8s worker |
| Worker 3 | 192.168.10.159 | K8s worker |
| GPU Worker | 192.168.10.x (DHCP) | K8s GPU worker |
| Wyze Bridge | 192.168.10.46 | RTSP camera streams |
| LoadBalancer Pool | 192.168.10.32-63 (/27) | Cilium L2 announcements |

## Talos Configuration

```yaml
machine:
  network:
    interfaces:
      - interface: ens18
        dhcp: true
  kubelet:
    nodeIP:
      validSubnets:
        - 192.168.10.0/24
```

## Proxmox Bridge Configuration

| Bridge | Physical NIC | CIDR | Purpose |
|--------|--------------|------|---------|
| vmbr0 | ens2 | 192.168.10.14/24 | Main LAN (10G) |

## TrueNAS Network Configuration

| Interface | IP | Speed | Purpose |
|-----------|-----|-------|---------|
| enp67s0 | 192.168.10.133/24 | 10G SFP+ | Main LAN (via 10G switch) |

## Whitelisted Storage Access

The Cilium network policy allows these storage connections:

| Destination | Ports | Purpose |
|-------------|-------|---------|
| 192.168.10.133 | 2049, 111 | NFS |
| 192.168.10.133 | 445 | SMB |
| 192.168.10.133 | 9000 | MinIO S3 |
| 192.168.10.133 | 30292, 30293 | RustFS |

## Troubleshooting

### Can't Reach Storage

```bash
# Test connectivity to TrueNAS
ping 192.168.10.133

# Test NFS mount
showmount -e 192.168.10.133
```

### Storage Performance Testing

```bash
# Test 10G link to TrueNAS
kubectl exec -n <ns> <pod> -- dd if=/dev/zero of=/mnt/nfs/test bs=1G count=1
# Should see ~1GB/s+ throughput on 10G link
```
