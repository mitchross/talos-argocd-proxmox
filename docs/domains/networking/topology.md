# Network topology

## Overview

The cluster (`talos-prod-cluster-v2`) spans four Proxmox hosts and two bare-metal
minis on a flat LAN. All are wired except the shed host, which sits behind a Wi-Fi
media bridge. Every node address is on the same `192.168.10.0/24`:

- **Main LAN (192.168.10.0/24).** All cluster traffic. Wired nodes connect through the
  10G switch.
- **Control-plane VM.** DHCP on the wired LAN, on the HP SFF host.
- **GPU worker VM.** DHCP on the wired LAN. Two RTX 3090s pass through from
  the bare-metal X399/2950X Threadripper host.
- **HP SFF worker VM.** DHCP on the wired LAN. It has the `wired-storage`
  Longhorn tag.
- **Bare-metal mini workers.** `mini-pc-dell-ultra-worker` (Dell Pro Micro),
  `hp-elite-gen12` (HP Elite Mini 800 G9) and `hp-elite-gen13` (HP Elite Mini
  600 G9). They use DHCP on the wired LAN at 1 GbE. They PXE-boot into Omni through booter
  on the Pi. See [bare-metal Talos workers](../hosts/bare-metal-talos.md).
  `hp-elite-gen12` holds the Zigbee stick.
- **HP micro worker VM.** DHCP, in the shed behind an ASUS RT-AX86U media
  bridge. It has the USB radios and the taint `node.vanillax.dev/link=wifi`.
- **Storage.** TrueNAS/RustFS-S3 at `192.168.10.133` (NFS/SMB/RustFS S3).

Wall-plug draw and cost per host are metered separately. See
[power metering](../power/metering.md).

Verify live node addresses with `kubectl get nodes -o wide`.

### Expected shed-node downtime

The solar/battery-powered shed HP micro Kubernetes worker intentionally becomes
unavailable during its power/sleep cycle. Power-related NotReady periods or
missing host metrics alone are expected, not an incident. Do not remediate
solely to bring the node online. Check the current power state and affected
workloads before diagnosing a fault. Unexpected network/power symptoms and
failures of dependent workloads still need normal investigation.

Cross-node pod traffic uses a **Cilium VXLAN tunnel between node IPs**
(`routingMode: tunnel`). **No pod routes exist anywhere.** None are on Firewalla,
in machine config, or on any host, and no device between nodes ever
sees a pod IP on the wire. The cluster uses tunnel mode because the shed's
media bridge silently drops inbound-first frames for IPs without an
ARP-learned binding, which means every pod IP. Direct node/LAN traffic
such as NFS to TrueNAS and API node endpoints is not encapsulated. Traffic
whose remote endpoint is a pod IP uses VXLAN. That includes cross-node Longhorn
instance-manager and replica flows.

## Physical topology

| Physical host | Talos role | Network boundary |
| --- | --- | --- |
| HP SFF `.21` | One control plane and one worker | Wired; both VMs fail with the same chassis |
| Threadripper `.14` | One GPU worker, two RTX 3090s | Wired |
| Dell Pro Micro (bare metal) | Worker `mini-pc-dell-ultra-worker` | Wired 1 GbE; no Proxmox |
| HP Elite Mini 800 G9 (bare metal) | Worker `hp-elite-gen12`, Zigbee stick | Wired 1 GbE; no Proxmox |
| HP Elite Mini 600 G9 (bare metal) | Worker `hp-elite-gen13` | Wired 1 GbE; no Proxmox |
| Shed HP `.20` | One worker with USB radios | Ethernet to ASUS RT-AX86U, then Wi-Fi media bridge |
| Pi 5 `.15` | Omni, Technitium and booter (PXE), outside Kubernetes | Separate management/DNS host |
| TrueNAS `.133` | NAS and RustFS, outside Kubernetes | 10 GbE; planned NAS downtime stalls its consumers |

Firewalla DHCP sends PXE clients to the Pi (option 66 `192.168.10.15`, option 67
`snp.efi`). See the [booter README](https://github.com/mitchross/talos-argocd-proxmox/blob/main/omni/pi-services/booter/README.md).

A 10G switch does not give every attached host a 10 GbE link. See the
[fleet inventory](../../inventory/2026-11-03-fleet-inventory.md) for measured
host capacity, and the [disk map](../storage/disk-map.md) for disks.

## IP assignments

### Main LAN (192.168.10.0/24)

| Device | IP | Purpose |
|--------|-----|---------|
| Router/Gateway | 192.168.10.1 | Default route + client DNS (Firewalla) |
| Proxmox | 192.168.10.14 | Hypervisor |
| HP micro Proxmox | 192.168.10.20 | Shed hypervisor behind the media bridge; USB radios |
| HP SFF Proxmox | 192.168.10.21 | CPU-only hypervisor (wired); hosts the control plane |
| Technitium / Omni (rpi5) | 192.168.10.15 | Split-DNS for `vanillax.me`, self-hosted Omni, booter PXE server |
| ASUS RT-AX86U | 192.168.10.70 | Media bridge (Wi-Fi → Ethernet) for the shed |
| Control Plane | DHCP | K8s control-plane node; verify live address with `kubectl` |
| Bare-metal mini workers | DHCP | `mini-pc-dell-ultra-worker`, `hp-elite-gen12`, `hp-elite-gen13`; verify live addresses with `kubectl` |
| TrueNAS | 192.168.10.133 | NAS (NFS/SMB/RustFS S3), 10G |
| GPU Worker | DHCP | K8s GPU worker node; verify live address with `kubectl` |
| Wyze Bridge | 192.168.10.46 | RTSP camera streams |
| LoadBalancer Pool | 192.168.10.32-63 (/27) | Cilium L2 announcements |

## Talos configuration

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

## Proxmox bridge configuration

| Bridge | Physical NIC | CIDR | Purpose |
|--------|--------------|------|---------|
| vmbr0 | ens2 | 192.168.10.14/24 | Main LAN (10G) |

## TrueNAS network configuration

| Interface | IP | Speed | Purpose |
|-----------|-----|-------|---------|
| enp67s0 | 192.168.10.133/24 | 10G SFP+ | Main LAN (via 10G switch) |

## Whitelisted storage access

The Cilium network policy allows these storage connections:

| Destination | Ports | Purpose |
|-------------|-------|---------|
| 192.168.10.133 | 2049, 111 | NFS |
| 192.168.10.133 | 445 | SMB |
| 192.168.10.133 | 443 | TrueNAS CSI API |
| 192.168.10.133 | 9000, 30292, 30293 | RustFS S3 (Kopiur, Loki, Tempo) |

## Troubleshooting

### Can't reach storage

```bash
# Test connectivity to TrueNAS
ping 192.168.10.133

# Test NFS mount
showmount -e 192.168.10.133
```

### Nodes are Ready, but pods cannot cross nodes

After a clean rebuild, every node can be `Ready` while Longhorn managers
crashloop and new PVCs remain `Pending`. `Ready` only proves that the nodes can
reach Kubernetes. It does not prove that pods can reach pods on other nodes.

Check Cilium from an agent pod:

```bash
kubectl exec -n kube-system <cilium-pod> -- cilium-health status --probe
```

`Node 1/1` with `Endpoints 0/1` means the normal network works but the pod
overlay does not. The cause is a virtio checksum offload bug, not MTU, Cilium
state, or the host's NIC.

Keep both offload guards in the cluster-level Talos `EthernetConfig`:

```yaml
apiVersion: v1alpha1
kind: EthernetConfig
name: eth0
features:
  tx-checksum-ip-generic: false
  tx-udp_tnl-csum-segmentation: false
```

An unchanged template sync may do nothing because Omni already considers the
config current. Adding the second guard produced a real config change, and
Talos re-applied the settings. The nodes did not visibly reboot.

Success means Cilium reports every node and endpoint reachable and all Longhorn
managers return to `2/2 Running`. Let existing CrashLoop backoff expire. Do not
keep restarting Longhorn, change MTU, or redesign the bridge for this symptom.

### Storage performance testing

```bash
# Test raw wire speed (target ~9.4 Gbps)
iperf3 -c 192.168.10.133

# Test NFS throughput from inside a pod
kubectl exec -n <ns> <pod> -- dd if=/mnt/nfs/testfile of=/dev/null bs=1M status=progress

# Test NFS throughput from Proxmox host (bypasses VM layer)
mount -t nfs -o nfsvers=4.1,nconnect=16,rsize=1048576,wsize=1048576 192.168.10.133:/mnt/BigTank/k8s/llama-cpp /mnt/nfstest
dd if=/mnt/nfstest/testfile of=/dev/null bs=1M status=progress
```

### NFS 10G tuning

The default Linux kernel `read_ahead_kb` of 128 KB limits NFS sequential reads to ~140 MB/s on any link speed. The cluster applies these fixes through Talos machine config:

| Layer | Setting | Value |
|-------|---------|-------|
| VFS readahead | udev rule `ATTR{read_ahead_kb}` | 16384 (16MB) |
| NFS readahead | `siderolabs/nfsrahead` extension | Installed on all nodes |
| RPC concurrency | `sunrpc.tcp_slot_table_entries` | 128 |
| TCP congestion | `net.ipv4.tcp_congestion_control` | bbr |
| TCP buffers | `net.core.rmem_max` / `wmem_max` | 64MB |
| NIC ring buffers | Proxmox + TrueNAS | 8192 (max) |
| NFS mount options | Per-PV CSI mountOptions | `nconnect=16,rsize=1M,wsize=1M` |

Reference throughput (TrueNAS ARC-cached 4GB file):

| Layer | Speed |
|-------|-------|
| iperf3 (wire) | 9.4 Gb/s |
| Proxmox host → NFS | Historical 2.7 GB/s application read. It exceeds a 10 GbE wire, so do not treat it as wire throughput. Separate cache effects from test method first. |
| Talos VM → NFS (untuned) | ~128 MB/s |

Debug commands:
```bash
# Verify readahead is 16384 (not 128)
kubectl exec -n <ns> <pod> -- cat /sys/class/bdi/0:*/read_ahead_kb

# Verify sunrpc slots are 128 (not 2)
kubectl exec -n <ns> <pod> -- cat /proc/sys/sunrpc/tcp_slot_table_entries

# Full NFS mount stats (connections, slots, RTT)
kubectl exec -n <ns> <pod> -- cat /proc/self/mountstats
```

See `scripts/debug-nfs-server.sh` (TrueNAS) and `scripts/debug-nfs-client.sh` (Proxmox) for full debugging.
