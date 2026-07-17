# Network Topology

## Overview

The cluster (`talos-singlenode-gpu-prod`) runs a wired control plane and GPU
worker on a flat LAN with 10G switch infrastructure, plus one routed Wi-Fi
CPU worker:

- **Main LAN (192.168.10.0/24)** — all wired cluster traffic via the 10G switch.
- **Control-plane VM** — `192.168.10.81`.
- **GPU worker VM** — `192.168.10.177` (dual RTX 3090 passed through from the
  bare-metal X399/2950X host).
- **Dell CPU worker VM** — `192.168.123.119` on the routed libvirt subnet
  `192.168.123.0/24` behind the Wi-Fi Dell host `192.168.10.20`; see
  [routed Wi-Fi Talos workers](wifi-libvirt-talos-workers.md).
- **Storage** — TrueNAS/RustFS-S3 at `192.168.10.133` (NFS/SMB/RustFS S3).

Verify live node addresses with `kubectl get nodes -o wide`.

PodCIDRs are natively routed (Cilium, no overlay). **Firewalla carries no pod
routes** — only `192.168.123.0/24 → 192.168.10.20` for the routed node subnet.
Wired↔wired pod routes are installed by Cilium (`autoDirectNodeRoutes`); the
wired nodes carry one permanent machine-config aggregate route
`10.244.0.0/16 via 192.168.10.20` for the routed worker, and the Dell host
routes each PodCIDR to its owner (see
[routed Wi-Fi Talos workers](wifi-libvirt-talos-workers.md)).

| PodCIDR | Node | Routed by |
|---------|------|-----------|
| 10.244.0.0/24 | GPU worker | Cilium direct routes + Dell host return route |
| 10.244.1.0/24 | Control plane | Cilium direct routes + Dell host return route |
| 10.244.2.0/24 | Dell CPU worker | wired-node /16 aggregate → Dell host → VM |

## Physical Topology

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              NETWORK TOPOLOGY                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────────┐                                ┌─────────────────┐    │
│   │    Proxmox      │                                │    TrueNAS      │    │
│   │  192.168.10.14  │                                │  192.168.10.133 │    │
│   └────────┬────────┘                                └────────┬────────┘    │
│            │ 10G                                              │ 10G         │
│            ▼                                                  ▼             │
│   ┌────────────────────────────────────────────────────────────────────┐   │
│   │                        10G SWITCH                                   │   │
│   │                     192.168.10.0/24                                 │   │
│   └────────────────────────────────────────────────────────────────────┘   │
│            │                                    │                            │
│            ▼                                    ▼                            │
│   ┌──────────────────────┐          ┌──────────────────────────────────┐    │
│   │  Control-Plane VM    │          │        GPU Worker VM             │    │
│   │   192.168.10.81      │          │       192.168.10.177            │    │
│   │                      │          │  net0 (ens18) → vmbr0 → 10G LAN │    │
│   └──────────────────────┘          │  dual RTX 3090 (passthrough)    │    │
│                                     └──────────────────────────────────┘    │
│                                                                              │
│   Wi-Fi ┌──────────────────────┐  virbr1  ┌──────────────────────────┐      │
│   ~~~~~▶│  Dell CachyOS host   │─────────▶│    Dell CPU Worker VM    │      │
│         │   192.168.10.20      │  routed  │    192.168.123.119       │      │
│         └──────────────────────┘ .123/24  └──────────────────────────┘      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## IP Assignments

### Main LAN (192.168.10.0/24)

| Device | IP | Purpose |
|--------|-----|---------|
| Router/Gateway | 192.168.10.1 | Default route + client DNS (Firewalla) |
| Proxmox | 192.168.10.14 | Hypervisor |
| Technitium / Omni (NUC) | 192.168.10.15 | Split-DNS for `vanillax.me` + self-hosted Omni |
| Dell Wi-Fi host | 192.168.10.20 | CachyOS libvirt router for 192.168.123.0/24 |
| Control Plane | 192.168.10.81 | K8s control-plane node |
| GPU Worker | 192.168.10.177 | K8s GPU worker node |
| TrueNAS | 192.168.10.133 | NAS (NFS/SMB/RustFS S3) — 10G |
| Dell CPU Worker | 192.168.123.119 | K8s worker on routed libvirt subnet |
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
| 192.168.10.133 | 9000, 30292, 30293 | RustFS S3 (Loki, Tempo, pgBackRest) |

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
# Test raw wire speed (target ~9.4 Gbps)
iperf3 -c 192.168.10.133

# Test NFS throughput from inside a pod
kubectl exec -n <ns> <pod> -- dd if=/mnt/nfs/testfile of=/dev/null bs=1M status=progress

# Test NFS throughput from Proxmox host (bypasses VM layer)
mount -t nfs -o nfsvers=4.1,nconnect=16,rsize=1048576,wsize=1048576 192.168.10.133:/mnt/BigTank/k8s/llama-cpp /mnt/nfstest
dd if=/mnt/nfstest/testfile of=/dev/null bs=1M status=progress
```

### NFS 10G Tuning

The default Linux kernel `read_ahead_kb` of 128 KB limits NFS sequential reads to ~140 MB/s on any link speed. The cluster applies these fixes via Talos machine config:

| Layer | Setting | Value |
|-------|---------|-------|
| **VFS readahead** | udev rule `ATTR{read_ahead_kb}` | 16384 (16MB) |
| **NFS readahead** | `siderolabs/nfsrahead` extension | Installed on all nodes |
| **RPC concurrency** | `sunrpc.tcp_slot_table_entries` | 128 |
| **TCP congestion** | `net.ipv4.tcp_congestion_control` | bbr |
| **TCP buffers** | `net.core.rmem_max` / `wmem_max` | 64MB |
| **NIC ring buffers** | Proxmox + TrueNAS | 8192 (max) |
| **NFS mount options** | Per-PV CSI mountOptions | `nconnect=16,rsize=1M,wsize=1M` |

Reference throughput (TrueNAS ARC-cached 4GB file):

| Layer | Speed |
|-------|-------|
| iperf3 (wire) | 9.4 Gb/s |
| Proxmox host → NFS | 2.7 GB/s |
| Talos VM → NFS (untuned) | ~128 MB/s |

**Debug commands**:
```bash
# Verify readahead is 16384 (not 128)
kubectl exec -n <ns> <pod> -- cat /sys/class/bdi/0:*/read_ahead_kb

# Verify sunrpc slots are 128 (not 2)
kubectl exec -n <ns> <pod> -- cat /proc/sys/sunrpc/tcp_slot_table_entries

# Full NFS mount stats (connections, slots, RTT)
kubectl exec -n <ns> <pod> -- cat /proc/self/mountstats
```

See `scripts/debug-nfs-server.sh` (TrueNAS) and `scripts/debug-nfs-client.sh` (Proxmox) for comprehensive debugging.
