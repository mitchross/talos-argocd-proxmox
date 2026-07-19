# Network Topology

## Overview

The cluster (`talos-singlenode-gpu-prod`) runs a wired control plane and RTX
3090 GPU worker on a flat LAN with 10G switch infrastructure, plus a third,
Wi-Fi-bridged Dell Proxmox GPU worker (deployed 2026-07-19); all node
addresses are on the same `192.168.10.0/24`:

- **Main LAN (192.168.10.0/24)** — all cluster traffic; wired nodes via the
  10G switch.
- **Control-plane VM** — `192.168.10.81`.
- **GPU worker VM** — `192.168.10.177` (dual RTX 3090 passed through from the
  bare-metal X399/2950X host).
- **Dell GPU worker VM** — `192.168.10.119` (static, in git), GTX 1050 Ti
  passed through from Proxmox `192.168.10.16`, bridged over Wi-Fi through an
  ASUS RT-AX86U media bridge; see the
  [Wi-Fi Proxmox Talos worker runbook](wifi-proxmox-talos-worker.md).
- **Storage** — TrueNAS/RustFS-S3 at `192.168.10.133` (NFS/SMB/RustFS S3).

Verify live node addresses with `kubectl get nodes -o wide`.

Cross-node pod traffic rides a **Cilium VXLAN tunnel between node IPs**
(`routingMode: tunnel`) — **no pod routes exist anywhere** (not on Firewalla,
not in machine config, not on any host), and no device between nodes ever
sees a pod IP on the wire. Tunnel mode was adopted because the Wi-Fi
site's media bridge silently drops inbound-first frames for IPs without an
ARP-learned binding — i.e. every pod IP (see the
[Wi-Fi Proxmox Talos worker runbook](wifi-proxmox-talos-worker.md)). Direct node/LAN traffic
such as NFS to TrueNAS and API node endpoints is not encapsulated. Traffic
whose remote endpoint is a pod IP, including cross-node Longhorn
instance-manager or replica flows, uses VXLAN.

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
│   Wi-Fi ┌──────────────────┐  eth  ┌────────────────┐ vmbr0 ┌────────────┐  │
│   ~~~~~▶│  ASUS RT-AX86U   │──────▶│ Dell Proxmox   │──────▶│ Dell GPU   │  │
│         │  media bridge    │       │ host (.16)     │       │ Worker VM  │  │
│         │  192.168.10.70   │       │ GTX 1050 Ti    │       │ .119 static│  │
│         └──────────────────┘       └────────────────┘       └────────────┘  │
│          (all three nodes appear directly on 192.168.10.0/24)                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## IP Assignments

### Main LAN (192.168.10.0/24)

| Device | IP | Purpose |
|--------|-----|---------|
| Router/Gateway | 192.168.10.1 | Default route + client DNS (Firewalla) |
| Proxmox | 192.168.10.14 | Hypervisor |
| Dell Proxmox | 192.168.10.16 | Wi-Fi-site hypervisor (GTX 1050 Ti passthrough) |
| Technitium / Omni (NUC) | 192.168.10.15 | Split-DNS for `vanillax.me` + self-hosted Omni |
| ASUS RT-AX86U | 192.168.10.70 | Media bridge (Wi-Fi → Ethernet) for the Dell |
| Control Plane | 192.168.10.81 | K8s control-plane node |
| Dell GPU Worker | 192.168.10.119 | K8s worker VM with GTX 1050 Ti (static, bridged via AX86U) |
| TrueNAS | 192.168.10.133 | NAS (NFS/SMB/RustFS S3) — 10G |
| GPU Worker | 192.168.10.177 | K8s GPU worker node |
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
| vmbr0 (Dell) | enp0s31f6 (`nic0`) | 192.168.10.16/24 | Media-bridge LAN path |

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
