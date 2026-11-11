# Network topology

This page shows how the machines in `talos-prod-cluster-v2` connect, which addresses
are fixed, and how pod traffic crosses between nodes. Read it before you debug a
network symptom or add a machine.

The cluster runs on three Proxmox hosts and three bare-metal mini PCs. All of them
are on one flat LAN, `192.168.10.0/24`. Every machine is wired, except the shed host,
which sits behind a Wi-Fi media bridge.

## How the machines connect

| Physical host | Talos role | Network link |
| --- | --- | --- |
| HP SFF `.21` (Proxmox) | One control-plane VM and one worker VM. The worker has the `wired-storage` Longhorn tag | Wired. Both VMs fail with the same chassis |
| Threadripper `.14` (Proxmox) | One GPU worker VM with two RTX 3090s passed through | Wired |
| Dell Pro Micro (bare metal) | Worker `mini-pc-dell-ultra-worker` | Wired 1 GbE, no Proxmox |
| HP Elite Mini 800 G9 (bare metal) | Worker `hp-elite-gen12`, holds the Zigbee stick | Wired 1 GbE, no Proxmox |
| HP Elite Mini 600 G9 (bare metal) | Worker `hp-elite-gen13` | Wired 1 GbE, no Proxmox |
| ASUS NUC 13 Pro (bare metal, joining) | Planned worker `asus-nuc13`. Not in Omni yet | Wired 2.5 GbE capable (Intel i226-V). Switch port and negotiated speed to be recorded |
| Shed HP micro `.20` (Proxmox) | One worker VM with the USB radios and the taint `node.vanillax.dev/link=wifi` | Ethernet to an ASUS RT-AX86U, then a Wi-Fi media bridge |
| Pi 5 `.15` | Omni, Technitium and booter (PXE). Outside Kubernetes | Separate management and DNS host |
| TrueNAS `.133` | NAS and RustFS. Also hosts the worker VM `truenas-worker-01` | 10 GbE on `eno49` for the NAS. The VM uses the second 10 GbE port, `eno50`. NAS downtime stalls the apps that use it and stops the VM |

Wired nodes connect through the 10G switch. A 10G switch does not give every
attached host a 10 GbE link. The [fleet inventory](../../inventory/2026-11-03-fleet-inventory.md)
has the measured capacity of each host, and the [disk map](../storage/disk-map.md)
has the disks. Wall-plug draw and cost per host are in [power metering](../power/metering.md).

The bare-metal minis PXE-boot into Omni through booter on the Pi. Firewalla DHCP
sends PXE clients to the Pi with option 66 `192.168.10.15` and option 67 `snp.efi`.
See [bare-metal Talos workers](../hosts/bare-metal-talos.md) and the
[booter README](https://github.com/mitchross/talos-argocd-proxmox/blob/main/omni/pi-services/booter/README.md).

## IP addresses

All Talos nodes get their address from DHCP. Read the live node addresses with
`kubectl get nodes -o wide`. The fixed addresses on the main LAN are:

| Device | IP | Purpose |
|--------|-----|---------|
| Router and gateway (Firewalla) | 192.168.10.1 | Default route and client DNS |
| Threadripper Proxmox | 192.168.10.14 | Hypervisor for the GPU worker |
| HP micro Proxmox | 192.168.10.20 | Shed hypervisor behind the media bridge, with the USB radios |
| HP SFF Proxmox | 192.168.10.21 | CPU-only hypervisor (wired). Hosts the control plane |
| Technitium and Omni (Pi 5) | 192.168.10.15 | Split DNS for `vanillax.me`, self-hosted Omni, booter PXE server |
| ASUS RT-AX86U | 192.168.10.70 | Media bridge (Wi-Fi to Ethernet) for the shed |
| TrueNAS | 192.168.10.133 | NAS (NFS, SMB, RustFS S3), 10G |
| Wyze Bridge | 192.168.10.46 | RTSP camera streams |
| LoadBalancer pool | 192.168.10.32-63 (/27) | Cilium L2 announcements |

The Threadripper host and TrueNAS each have one 10G interface on the main LAN:

| Machine | Interface | Address | Speed |
|---------|-----------|---------|-------|
| Threadripper Proxmox | bridge `vmbr0` on NIC `ens2` | 192.168.10.14/24 | 10G |
| TrueNAS | `enp67s0` | 192.168.10.133/24 | 10G SFP+ |

## How pod traffic crosses nodes

Cilium, the cluster's network plugin, carries pod traffic between nodes in a VXLAN
tunnel between node IPs (`routingMode: tunnel`). A VXLAN tunnel wraps each pod packet
inside a packet addressed to the other node.

No pod routes exist on Firewalla, in machine config, or on any host. No device
between two nodes sees a pod IP on the wire.

Keep tunnel mode. The shed's media bridge silently drops inbound-first frames for an
IP that has no ARP-learned binding. No pod IP has one, so without the tunnel the
bridge drops those frames for every pod on the shed node.

Traffic whose remote end is a pod IP uses VXLAN. That includes cross-node Longhorn
instance-manager and replica traffic. Traffic between a node and a LAN address is not
wrapped. That includes NFS to TrueNAS and the API endpoints on each node.

## Talos network settings

The nodes have no per-NIC network settings, so Talos runs DHCP on every physical NIC.
Each worker machine set pins the kubelet node IP to the main LAN in
`omni/cluster-template/cluster-template-prod-v2.yaml`:

```yaml
apiVersion: v1alpha1
kind: KubeNodeConfig
nodeIP:
  validSubnets:
  - 192.168.10.0/24
```

## Storage access from pods

A shared Cilium NetworkPolicy blocks pod traffic to private LAN addresses unless a
rule allows it. It allows the TrueNAS ports for NFS, SMB, the TrueNAS CSI API, and
RustFS S3. The list of ports is in [Cilium policies](policy.md).

## Expected shed-node downtime

The shed HP micro worker runs on solar and battery power. It becomes unavailable
during its power and sleep cycle, and that is intended.

A `NotReady` period or missing host metrics on this node is expected, not an
incident. Do not act only to bring the node back online. Check the current power
state and the affected workloads before you diagnose a fault.

Investigate normally when you see an unexpected network or power symptom, or when a
workload that depends on the node fails.

## Troubleshooting

### Pods cannot reach storage

```bash
# Test connectivity to TrueNAS
ping 192.168.10.133

# Test NFS mount
showmount -e 192.168.10.133
```

### Nodes are Ready, but pods cannot cross nodes

After a clean rebuild, every node can be `Ready` while Longhorn managers crashloop
and new PVCs stay `Pending`. `Ready` proves only that the nodes can reach Kubernetes.
It does not prove that pods can reach pods on other nodes.

Check Cilium from an agent pod:

```bash
kubectl exec -n kube-system <cilium-pod> -- cilium-health status --probe
```

`Node 1/1` with `Endpoints 0/1` means the node network works but the pod tunnel does
not. The cause is a virtio checksum offload bug. It is not MTU, Cilium state, or the
host's NIC.

Keep both offload guards in the cluster-level Talos `EthernetConfig`:

```yaml
apiVersion: v1alpha1
kind: EthernetConfig
name: eth0
features:
  tx-checksum-ip-generic: false
  tx-udp_tnl-csum-segmentation: false
```

A template sync that changes nothing does nothing, because Omni already considers the
config current. Talos applies the settings again only when the config really changes.
The nodes do not visibly reboot for this change.

The fix works when Cilium reports every node and endpoint reachable and all Longhorn
managers return to `2/2 Running`. Let the existing CrashLoop backoff expire. Do not
keep restarting Longhorn, change MTU, or redesign the bridge for this symptom.

### NFS reads are slow

The default Linux kernel `read_ahead_kb` of 128 KB limits NFS sequential reads to
about 140 MB/s on any link speed. The cluster applies these settings through Talos
machine config:

| Layer | Setting | Value |
|-------|---------|-------|
| VFS readahead | udev rule `ATTR{read_ahead_kb}` | 16384 (16MB) |
| NFS readahead | `siderolabs/nfsrahead` extension | Installed on all nodes |
| RPC concurrency | `sunrpc.tcp_slot_table_entries` | 128 |
| TCP congestion | `net.ipv4.tcp_congestion_control` | bbr |
| TCP buffers | `net.core.rmem_max` / `wmem_max` | 64MB |
| NIC ring buffers | Proxmox + TrueNAS | 8192 (max) |
| NFS mount options | Per-PV CSI mountOptions | `nconnect=16,rsize=1M,wsize=1M` |

Check that a pod sees the tuned values:

```bash
# Verify readahead is 16384 (not 128)
kubectl exec -n <ns> <pod> -- cat /sys/class/bdi/0:*/read_ahead_kb

# Verify sunrpc slots are 128 (not 2)
kubectl exec -n <ns> <pod> -- cat /proc/sys/sunrpc/tcp_slot_table_entries

# Full NFS mount stats (connections, slots, RTT)
kubectl exec -n <ns> <pod> -- cat /proc/self/mountstats
```

Then measure each layer:

```bash
# Test raw wire speed (target ~9.4 Gbps)
iperf3 -c 192.168.10.133

# Test NFS throughput from inside a pod
kubectl exec -n <ns> <pod> -- dd if=/mnt/nfs/testfile of=/dev/null bs=1M status=progress

# Test NFS throughput from Proxmox host (bypasses VM layer)
mount -t nfs -o nfsvers=4.1,nconnect=16,rsize=1048576,wsize=1048576 192.168.10.133:/mnt/BigTank/k8s/llama-cpp /mnt/nfstest
dd if=/mnt/nfstest/testfile of=/dev/null bs=1M status=progress
```

Reference throughput, read from a 4GB file held in the TrueNAS ARC cache:

| Layer | Speed |
|-------|-------|
| iperf3 (wire) | 9.4 Gb/s |
| Proxmox host to NFS | 2.7 GB/s application read. This exceeds a 10 GbE wire, so do not treat it as wire throughput. Separate cache effects from the test method first. |
| Talos VM to NFS (untuned) | ~128 MB/s |

For deeper checks, run `scripts/debug-nfs-server.sh` on TrueNAS and
`scripts/debug-nfs-client.sh` on Proxmox.
