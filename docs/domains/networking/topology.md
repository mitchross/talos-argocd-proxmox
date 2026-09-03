# Network Topology

## Overview

The cluster (`talos-prod-cluster-v2`) spans five Proxmox hosts on a flat LAN.
Four are wired through the 10G switch; the fifth sits in the shed behind a Wi-Fi
media bridge. Every node address is on the same `192.168.10.0/24`:

- **Main LAN (192.168.10.0/24)** — all cluster traffic; wired nodes via the
  10G switch.
- **Control-plane VM** — DHCP on the wired LAN, on the HP SFF host.
- **GPU worker VM** — DHCP on the wired LAN; one RTX 3090 passed through from
  the bare-metal X399/2950X Threadripper host.
- **General worker VM** — DHCP on the wired LAN; 8 vCPU and 24 GiB RAM for
  CPU-only compute.
- **HP SFF worker VM** — DHCP on the wired LAN; carries the `wired-storage`
  Longhorn tag.
- **HP Elite worker VM** — DHCP on the wired LAN; 13th-gen i5-13500T, NVMe
  Longhorn disk, also `wired-storage`.
- **Dell Optiplex worker VM** — DHCP on the wired LAN (2.5 GbE add-in card on
  the Optiplex host); see the
  [Dell Proxmox Talos worker runbook](dell-proxmox-talos-worker.md).
- **HP micro worker VM** — DHCP, in the shed behind an ASUS RT-AX86U media
  bridge; carries the USB radios and is tainted `node.vanillax.dev/link=wifi`.
- **Storage** — TrueNAS/RustFS-S3 at `192.168.10.133` (NFS/SMB/RustFS S3).

Wall-plug draw and cost per host are metered separately — see
[power metering](../power/metering.md).

Verify live node addresses with `kubectl get nodes -o wide`.

Cross-node pod traffic rides a **Cilium VXLAN tunnel between node IPs**
(`routingMode: tunnel`) — **no pod routes exist anywhere** (not on Firewalla,
not in machine config, not on any host), and no device between nodes ever
sees a pod IP on the wire. Tunnel mode was adopted because the shed's
media bridge silently drops inbound-first frames for IPs without an
ARP-learned binding — i.e. every pod IP. Direct node/LAN traffic
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
│   │ Control Plane +      │          │        GPU Worker VM             │    │
│   │ General Worker VMs   │          │                                  │    │
│   │      DHCP            │          │            DHCP                  │    │
│   │                      │          │  net0 (ens18) → vmbr0 → 10G LAN │    │
│   └──────────────────────┘          │  dual RTX 3090 (passthrough)    │    │
│                                     └──────────────────────────────────┘    │
│                                                                              │
│   Wi-Fi ┌──────────────────┐  eth  ┌────────────────┐ vmbr0 ┌────────────┐  │
│   ~~~~~▶│  ASUS RT-AX86U   │──────▶│ HP micro (.20) │──────▶│ HP micro   │  │
│         │  media bridge    │       │ shed, USB      │       │ Worker VM  │  │
│         │  192.168.10.70   │       │ radios         │       │ DHCP       │  │
│         └──────────────────┘       └────────────────┘       └────────────┘  │
│                                                                              │
│   2.5G   ┌────────────────┐ vmbr0 ┌────────────┐    ┌────────────────────┐  │
│   ──────▶│ Dell Optiplex  │──────▶│ Optiplex   │    │ HP SFF host (.21)  │  │
│          │ host (.16)     │       │ Worker VM  │    │ → control plane +  │  │
│          └────────────────┘       └────────────┘    │   HP SFF Worker VM │  │
│                                                     └────────────────────┘  │
│          ┌────────────────┐ vmbr0 ┌──────────────────┐                       │
│          │ HP Elite (.22) │──────▶│ HP Elite Worker  │                       │
│          └────────────────┘       │ VM               │                       │
│                                   └──────────────────┘                       │
│          (every node appears directly on 192.168.10.0/24)                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## IP Assignments

### Main LAN (192.168.10.0/24)

| Device | IP | Purpose |
|--------|-----|---------|
| Router/Gateway | 192.168.10.1 | Default route + client DNS (Firewalla) |
| Proxmox | 192.168.10.14 | Hypervisor |
| Dell Optiplex Proxmox | 192.168.10.16 | CPU-only hypervisor (wired 2.5 GbE) |
| HP micro Proxmox | 192.168.10.20 | Shed hypervisor behind the media bridge; USB radios |
| HP SFF Proxmox | 192.168.10.21 | CPU-only hypervisor (wired); hosts the control plane |
| HP Elite Proxmox | 192.168.10.22 | CPU-only hypervisor (wired, i5-13500T) |
| Technitium / Omni (rpi5) | 192.168.10.15 | Split-DNS for `vanillax.me` + self-hosted Omni |
| ASUS RT-AX86U | 192.168.10.70 | Media bridge (Wi-Fi → Ethernet) for the shed |
| Control Plane | DHCP | K8s control-plane node; verify live address with `kubectl` |
| Dell CPU Worker | DHCP | K8s CPU worker node; verify live address with `kubectl` |
| TrueNAS | 192.168.10.133 | NAS (NFS/SMB/RustFS S3) — 10G |
| GPU Worker | DHCP | K8s GPU worker node; verify live address with `kubectl` |
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
| vmbr0 (Dell) | `uplink25g` (RTL8125B) | 192.168.10.16/24 | Wired 2.5 GbE; the onboard I219 `nic0` is unused (e1000e hang bug) |

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
