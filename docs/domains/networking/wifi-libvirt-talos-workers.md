# Wi-Fi Talos workers with Omni and libvirt

This guide explains how a Wi-Fi-only Linux machine contributes replaceable CPU
capacity to `talos-singlenode-gpu-prod` without becoming a control-plane or
storage failure dependency.

!!! info "Status — current, bridged architecture (2026-07-17)"
    The Dell worker is Ready at `192.168.10.119` **directly on the HomeLab
    VLAN**, bridged through an ASUS RT-AX86U in Media Bridge mode. The earlier
    routed design (dedicated `192.168.123.0/24` subnet, host routing, egress
    NAT, per-PodCIDR routes) is fully retired — its history and rationale
    live in git (PR #1657) and the fallback section below.

**Scope:** this procedure prepares a CachyOS host, connects its libvirt
provider to self-hosted Omni, and adds a bridged Talos VM to the existing
production cluster as a worker. It deliberately leaves the wired control
plane, GPU worker, Proxmox hosts, TrueNAS, and Longhorn storage ownership
unchanged.

![Omni provisions a Wi-Fi-hosted Talos worker bridged onto the HomeLab VLAN](../../assets/wifi-libvirt-worker-routing.svg)

*The invariant is that the Wi-Fi host adds optional compute. Omni owns the
VM, the media bridge owns the Wi-Fi hop, and wired systems retain the durable
control-plane and storage roles.*

## The mental model

CachyOS remains the physical operating system. Kubernetes does not run
directly on it. QEMU/KVM runs a complete Talos VM, and the official Omni
libvirt provider turns Omni `MachineRequest` resources into local libvirt
disks and domains.

```text
NUC: Omni API and desired-state repositories
  |
  | MachineRequest
  v
Dell CachyOS: libvirt + provider agent
  |
  | br0 -> eno1 -> ASUS media bridge -> Wi-Fi -> AP -> HomeLab VLAN
  v
Talos VM: kubelet + Cilium + ordinary production workloads
```

The trick that makes this simple is the **media bridge**: an ASUS RT-AX86U
(Asuswrt-Merlin) in Media Bridge mode is a Wi-Fi client that presents true
multi-MAC Ethernet. The Dell host and the Talos VM each appear on
`192.168.10.0/24` with their own MAC and address, exactly as if wired. A
plain Wi-Fi station cannot do this — 3-address 802.11 frames cannot carry
foreign source MACs, which is why hanging a worker directly off a host
wlan requires the far more complex routed design in the fallback section.

Address layers:

| Layer | CIDR or address | Owner | Purpose |
|---|---|---|---|
| HomeLab Wi-Fi/LAN | `192.168.10.0/24` | Firewalla | Every node, including the Dell VM |
| Dell host on br0 | DHCP (`.186` at time of writing) | Firewalla DHCP | Hypervisor + provider agent |
| Talos VM | `192.168.10.119` static | Omni machine config (git) | Worker node address |
| Kubernetes pods | `10.244.0.0/16` aggregate | Kubernetes + Cilium | A distinct `/24` per node, fully automatic |

**Cross-node pod traffic is VXLAN-tunneled between node IPs** (Cilium
`routingMode: tunnel`), so nothing between the nodes — including the media
bridge — ever sees a pod IP on the wire, and no pod routes exist anywhere.
Firewalla carries no cluster routes at all.

Tunneling is load-bearing, not optional. The first bridged deployment ran
Cilium native routing and hit a subtle defect: the media bridge is
**L3-aware** and forwards inbound frames only for IPs it has ARP-learned.
Pod IPs never ARP (they are routed behind the node address), so
inbound-first connections to Dell pod IPs — Prometheus scrapes, service
traffic to Dell-scheduled backends, cilium-health endpoint probes — were
silently dropped or worked only intermittently after the bridge eventually
learned an address, while node-IP traffic and Dell-initiated flows worked
perfectly. Encapsulating pod traffic inside node-IP UDP (port 8472) removes
the entire class of problem for any bridge or transport. The cost lands
only on cross-node pod↔pod packets (~50 bytes + encap CPU); NFS, Longhorn
iSCSI attach, and API traffic ride node IPs untunneled.

## Why the VM address is static

The media bridge's proxy-STA forwards unicast traffic for secondary MACs
perfectly, but **breaks DHCP for every MAC after the first** (the DISCOVER
leaves, the lease never arrives — NetworkManager sits in "getting IP
configuration" forever). The Dell host, as the bridge's primary client,
leases normally; the VM cannot. The VM therefore carries a static address in
its Omni machine-set patch, which is also the more rebuild-proof choice: a
replacement VM has a new random MAC, and a static-in-git address doesn't
care. Keep `192.168.10.119` outside (or reserved against) the Firewalla DHCP
pool.

## Owning configuration

The version-controlled inputs are:

- [`omni/machine-classes/libvirt-dell-single-node.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/omni/machine-classes/libvirt-dell-single-node.yaml) — VM size, pool, and network name.
- [`omni/cluster-template/cluster-template-singlenode-gpu.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/omni/cluster-template/cluster-template-singlenode-gpu.yaml) — the `dell-cpu-workers` machine set, including the static `192.168.10.119` network patch.
- [`omni/libvirt-provider/talos-routed-network.xml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/omni/libvirt-provider/talos-routed-network.xml) — the libvirt network, now a plain bridge onto `br0` (the name `talos-routed` survives because the machine class references it).
- [`omni/libvirt-provider/omni-infra-provider-libvirt.service`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/omni/libvirt-provider/omni-infra-provider-libvirt.service) — hardened provider service.

Host-side state that is deliberate but not in git: the NetworkManager `br0`
bridge (below), the AX86U's Media Bridge configuration, and the Firewalla
DHCP reservations for the Dell host and the AX86U.

The NUC at `192.168.10.15` runs Omni. The provider agent runs on the Dell
because `qemu:///system` is the Dell-local libvirt API. A root-only
`provider.env` contains the provider service-account key and is never
committed.

## Build the bridge path

### 1. ASUS media bridge

Put the RT-AX86U in **Media Bridge** mode joined to the HomeLab SSID, and
cable it to the Dell's Ethernet port. Give the AX86U a Firewalla DHCP
reservation so it stays findable. Verify from the Dell that the wired NIC
leases a `192.168.10.x` address.

Prove multi-MAC forwarding before touching the cluster — this is the test
that validates the whole design:

```bash
sudo ip link add mbtest0 link eno1 type macvlan mode bridge
sudo ip link set mbtest0 up
sudo ip addr add 192.168.10.199/24 dev mbtest0   # any free address
ping -c 3 -I mbtest0 192.168.10.1                 # expect replies
sudo ip link del mbtest0
```

A second MAC pinging the gateway proves proxy-STA forwards foreign MACs both
ways. (Expect DHCP on that same interface to fail — that is the known
limitation, handled by the VM's static address.)

### 2. Host bridge

```bash
sudo nmcli connection add type bridge ifname br0 con-name br0 \
  bridge.stp no ipv4.method auto ipv6.method disabled \
  ethernet.cloned-mac-address <eno1-mac>
sudo nmcli connection add type ethernet ifname eno1 con-name br0-port-eno1 \
  master br0
sudo nmcli connection down "Wired connection 1"
sudo nmcli connection modify "Wired connection 1" connection.autoconnect no
sudo nmcli connection up br0-port-eno1 && sudo nmcli connection up br0
```

Cloning eno1's MAC onto br0 keeps the host's existing DHCP lease. The host's
own Wi-Fi (`wlan0`) can stay up as an out-of-band path during surgery; long
term it is optional.

### 3. libvirt network

```bash
sudo virsh net-define omni/libvirt-provider/talos-routed-network.xml
sudo virsh net-start talos-routed
sudo virsh net-autostart talos-routed
```

When redefining an existing network, embed its current UUID in the XML first
(`virsh net-dumpxml talos-routed | grep uuid`) or `net-define` refuses.
Switching an existing VM's network requires: guest shutdown → `net-define` →
`net-destroy` → `net-start` → guest start.

### 4. Provider and template

Install the pinned provider binary and service as in the provider unit file,
create the provider identity with `omnictl infraprovider create libvirt`,
then apply the machine class and sync the template from the repository:

```bash
omnictl apply -f omni/machine-classes/libvirt-dell-single-node.yaml
cd omni/cluster-template
omnictl cluster template validate -f cluster-template-singlenode-gpu.yaml
omnictl cluster template sync --dry-run -f cluster-template-singlenode-gpu.yaml
omnictl cluster template sync -v -f cluster-template-singlenode-gpu.yaml
```

Template patch paths resolve relative to the working directory: apply the
machine class from the repository root, run template commands from
`omni/cluster-template/`.

Keep `omnictl` at the same version as the Omni backend before trusting its
output. A v1.4.7 client against a v1.9.0 backend reported stale or missing
phase data while the UI was already healthy. Do not intervene during a
system-extension reboot merely because readiness briefly drops; wait for
`machine is up to date` with identical desired/current schematic IDs.

## Verification

```bash
omnictl get clusterstatus talos-singlenode-gpu-prod -o yaml
kubectl get nodes -o custom-columns='NODE:.metadata.name,IP:.status.addresses[?(@.type=="InternalIP")].address,POD_CIDR:.spec.podCIDR'
kubectl -n kube-system exec <wired-cilium-pod> -c cilium-agent -- ip route show | grep 10.244
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded
```

Expected state:

- three Ready nodes, the Dell worker at `192.168.10.119` with
  `node.vanillax.dev/class=dell-cpu` and `topology.kubernetes.io/zone=yard`;
- every wired node shows a direct `10.244.x.0/24 via 192.168.10.119` route
  installed by Cilium (no static routes anywhere);
- cross-node pod probes, cluster DNS, service reachability, and internet
  egress succeed from Dell-scheduled pods;
- the Dell domain, network, pool, libvirt service, and provider service all
  autostart.

Longhorn needs no exclusion for this node. The cluster sets
`createDefaultDiskLabeledNodes: "true"`, and only the GPU worker carries the
`node.longhorn.io/create-default-disk` label, so the Dell registers with
zero disks and owns no replicas. Its `longhorn-csi-plugin` DaemonSet pod
stays — that is what lets Dell-scheduled workloads mount Longhorn volumes
served from the wired node.

!!! warning "Longhorn volumes attach over Wi-Fi"
    Any pod with a Longhorn PVC scheduled onto the Dell does its disk I/O
    via iSCSI across the Wi-Fi hop. Under RF congestion this surfaces as
    `input/output error` in the pod (seen on kopiur movers). Prefer
    stateless or NFS-backed workloads on this node, and consider a taint if
    movers land there too often — kopiur's mover spec has no placement
    fields.

## Failure paths

| Symptom | Stop and inspect | Recovery |
|---|---|---|
| Dell host has no lease on the wired NIC | AX86U parent-AP status, cabling, Firewalla | Fix the bridge before anything else |
| VM never gets its address | machine-set static patch synced? `virsh domiflist` shows `br0`? | Sync template; flip the network per step 3 |
| Second MAC cannot DHCP | — | Known media-bridge limitation; static addresses only |
| Node Ready but cross-node pods fail | wired nodes' `ip route` for the Dell `/24` | Cilium reinstalls direct routes when node IPs are on one L2; check node InternalIP |
| Sluggish or failing disk I/O in Dell pods | Longhorn volume attached over Wi-Fi | Reschedule to a wired node; see warning above |
| Provider replaces the domain | New domain lacks autostart; new MAC | Re-enable autostart; static IP makes the MAC change a non-event |
| Wi-Fi is unstable | AX86U RSSI/link rate, AP airtime | Cordon/drain and scale the worker set to zero |

To remove the worker, delete the `dell-cpu-workers` document from the
template, validate, and sync. Omni deprovisions the provider-owned VM while
leaving the original control plane and GPU worker intact.

## Fallback: no bridge device available

If a site has no media-bridge-capable device, a routed design works with a
plain host wlan: a dedicated libvirt subnet routed through the host, a
Firewalla route for the node subnet, static PodCIDR routes (or FRR + Cilium
BGP), and public-only egress NAT. This repository ran that design first —
the full procedure, its systemd units, and its hard-won gotchas are in git
history (PR #1657). The two gotchas worth remembering even now:

- libvirt `mode="route"` networks install `LIBVIRT_FWI/FWO` FORWARD rules
  that permit only the network's own subnet and REJECT everything else
  (including pod CIDRs) with ICMP port-unreachable, before UFW is consulted.
  Routed libvirt networks for Cilium must use `mode="open"`.
- A brand-new Talos client DHCPs from `0.0.0.0:68`, which does not match a
  subnet-scoped UFW allow — routed-network DHCP needs an explicit UDP
  client-port-68 rule on the bridge.

## Scaling beyond one Wi-Fi worker

Each additional Wi-Fi site needs its own media bridge (or an AP7 in wireless
backhaul with its bridged Ethernet ports) and one static VM address from the
LAN — nothing else. There are no per-site subnets or routes to plan anymore.
Keep VM lifecycle in Omni; prepare hosts with Ansible if the fleet grows.

## Upstream references

- [Omni infrastructure providers](https://docs.siderolabs.com/omni/infrastructure-and-extensions/infrastructure-providers)
- [Omni cluster templates](https://docs.siderolabs.com/omni/reference/cluster-templates)
- [libvirt network format](https://www.libvirt.org/formatnetwork.html)
- [Asuswrt-Merlin](https://www.asuswrt-merlin.net/)
- [Talos KubeSpan and Cilium limitations](https://docs.siderolabs.com/talos/v1.13/networking/kubespan)
