# Cluster Topology

`talos-prod-cluster-v2` spreads one control plane and four workers across four
Proxmox hosts. Each host is its own failure domain, named by the
`topology.kubernetes.io/zone` label on its nodes.

| Host | IP | Zone | Guests |
|---|---|---|---|
| HP ProDesk SFF | 192.168.10.21 | `hp-sff` | control plane, general worker |
| Threadripper | 192.168.10.14 | `house` | GPU worker only |
| Dell OptiPlex 7060 | 192.168.10.16 | `dell` | general worker |
| HP 600 G4 micro | 192.168.10.20 | `shed` | worker with the USB radios |

There is one etcd member. The cluster is not HA: losing the HP SFF stops the
Kubernetes API until it returns.

## Storage controllers

Measure the host in front of you; do not reason from a controller's reputation.

The Threadripper's onboard AMD X399 SATA controller is the one that misbehaves
here. Its boot SSD accumulated **442 SATA CRC errors** — link-layer, so cabling
or the port rather than the flash — and the drives on it threw full-queue NCQ
timeouts with hard link resets, a handful every boot. Moving all three disks to
a 4-port Marvell 88SE9215 add-in card stopped both: zero ATA exceptions and zero
new CRC errors since, with host IO pressure dropping from 10-21% to under 3%.

The cost is real and worth knowing: that card negotiates PCIe 2.0 **x1**
(`LnkSta: Speed 5GT/s, Width x1`), so every disk behind it shares roughly
400 MB/s. It shows up in RAID resyncs and the `ssd-ent` flash tier, not in
ordinary VM IO. Check what a card actually negotiates before trusting its port
count:

```bash
lspci -vv -s <bdf> | grep -E 'LnkCap:|LnkSta:'
```

## Why etcd is not on the Threadripper

The Threadripper hard-locks — no panic, no oops, nothing written to disk, the
journal simply stops mid-line. Its SATA path is the leading suspect: `ata5`
throws full-queue NCQ timeouts with hard link resets, and the boot SSD has
accumulated hundreds of SATA CRC errors. That host must never carry etcd or any
single-replica data that cannot be rebuilt.

It keeps the GPU worker because the RTX 3090 is physically in it, and because a
GPU node is the cheapest thing to lose: the workloads are stateless inference
services that reschedule.

Set up remote kernel logging before trusting any diagnosis of that host — see
[Capturing a lockup](#capturing-a-lockup).

## Sizing

| VM | vCPU | RAM | Host RAM | Disks |
|---|---|---|---|---|
| `hp-sff-control-plane` | 4 | 12 GiB | 62 GiB | 100 GiB on its own SSD (`hp-sff-cp-vmstore`) |
| `hp-sff-worker` | 6 | 40 GiB | (same host) | 128 GiB boot + 690 GiB Longhorn |
| `threadripper-gpu-worker` | 30 | 100 GiB | 125 GiB | 2x450 GiB + 300 GiB flash + RTX 3090 |
| `dell-worker` | 4 | 30 GiB | 39 GiB | 128 GiB boot + 400 GiB Longhorn |
| `hp-micro-worker` | 4 | 12 GiB | 15 GiB | 128 GiB boot + 850 GiB Longhorn (unschedulable) |

Two ceilings are load-bearing:

- **The GPU VM stops at 100 GiB.** PCIe passthrough pins the entire guest
  allocation in host RAM. A 120 GiB guest on this 125 GiB host drove the
  hypervisor into OOM and locked it up hard. Do not raise this.
- **The GPU VM stops at 30 of 32 threads.** At 32 it can starve the host itself.

The control plane gets its own SSD on the HP SFF (`hp-sff-cp-vmstore`, thick
LVM), deliberately not `hp-prodesk-vmstore`. That disk carries Proxmox root and
around 27 Longhorn replicas, and etcd is fsync-latency-bound — it must not
queue behind replica traffic. `hp-prodesk-vmstore` also has only single-digit
GiB free, and its 690 GiB Longhorn LV is XFS, which cannot be shrunk in place.

Keep that VG thick. An lvmthin pool's metadata commits collapse fsync
throughput, which is precisely what etcd depends on.

## Storage

Longhorn runs **one replica per volume**. It spreads volumes across disks; it
does not mirror between them. Losing a worker's disk loses every volume whose
only replica sat there, and recovery is from the off-host kopiur/Kopia backups
described in `docs/disaster-recovery.md`.

The practical consequence: **evict a node's Longhorn replicas before you delete
or rebuild its VM.** Set `allowScheduling: false` and `evictionRequested: true`
on the disk in its `nodes.longhorn.io` resource, wait for the rebuilds to land
elsewhere, and only then touch the VM. A detached volume cannot be evicted —
Longhorn needs a running engine to rebuild — so attach it first or accept the
loss.

The HP micro's 850 GiB disk is registered but left unschedulable on purpose: a
replica there puts app data behind the shed's wireless bridge.

## Capturing a lockup

A host that hard-locks writes nothing to its own disk, so local logs are
useless after the fact. Three things must be in place *before* the next freeze:

- **Remote log forwarding** to the collector on the rpi5
  (`netconsole-receiver.service`, UDP 192.168.10.15:6666, writing to
  `/var/log/netconsole/`). On the Threadripper this is `journal-forward.service`,
  a journal-to-UDP streamer.
- **`SyncIntervalSec=1s` in journald.** The 5-minute default discards up to five
  minutes of local logs on a hard freeze.
- **A hardware watchdog** (`sp5100_tco` plus systemd `RuntimeWatchdogSec=60`) so
  a wedged kernel resets itself in about a minute instead of sitting dead until
  someone walks over to the machine. Skip it if Proxmox HA's `watchdog-mux` is
  running — it claims `/dev/watchdog` exclusively.

**Kernel netconsole does not work on a Proxmox host with bridged VM networking.**
netpoll refuses a bridge whose ports include the per-VM firewall veths
(`fwprNNNp0`), and it refuses the physical NIC because it is a bridge slave.
Both attempts abort with `Netpoll setup failed`. The only way to get true
netconsole — which, unlike journal forwarding, keeps sending after userspace
dies — is a NIC that belongs to no bridge. The Threadripper's ConnectX-3 has a
free second port (`nic1`) reserved for exactly that; it needs a cable.

## Moving a machine between hosts

Pointing a machine set at a different MachineClass does **not** move anything.
Omni counts the running machine as satisfying the allocation
(`machines: total 1, healthy 1, requested 1`, `ready: true`) and never
replaces it. The class governs the *next* machine provisioned, nothing more.

To actually relocate a worker: scale its machine set to 0 and back to 1, or
delete the machine. Evict its Longhorn replicas first — see [Storage](#storage).

To relocate the **control plane**, never do that. With a single etcd member,
removing it destroys cluster state. Instead:

1. `talosctl -n <cp> etcd snapshot <file>` and copy it off the host.
2. Point the `ControlPlane` block at the new MachineClass and sync. Nothing
   happens yet — this only changes where the next machine comes from.
3. Raise `size` to 2 and sync. Omni provisions a second control plane from the
   new class and joins it to etcd. Check the new host has RAM for it.
4. Wait for both members to be healthy before going further. etcd now needs
   both to hold quorum, so this window is the risky part — keep it short.
5. Remove the **old** machine explicitly rather than scaling back to 1 and
   trusting Omni to pick the right one.

## Versions

Talos and Kubernetes are coupled: Omni validates the pair and refuses the sync
outright with `invalid kubernetes version "X": is not compatible with talos
version "Y"`. Talos 1.13.9 caps Kubernetes at 1.36.4, which is where this
cluster sits — there is no headroom until Talos 1.14 is GA and Omni's catalog
offers it. Check what a Talos release actually allows before planning a bump:

```bash
omnictl get talosversion <version> -o yaml   # lists every compatible k8s version
```

## Operating rules

- Applying a MachineClass changes **future** allocations only. It does not
  resize, rename, or replace an existing Omni machine.
- To adopt new CPU/RAM values on a running VM, cold-resize it in Proxmox
  (`qm shutdown` / `qm set` / `qm start`). This preserves the provider-owned
  Longhorn disks; a full replacement destroys them.
- Keep `siderolabs/nfs-utils` off GPU worker nodes. Use the CSI NFS path.
- Additional Longhorn disks are attached at VM creation time by the provider.
  They cannot be added to an existing machine without replacing it.
- The Cilium L2 policy must allow the current control-plane node to announce
  VIPs.
- The provider has no USB field. After replacing the HP micro's VM, re-add the
  zigbee and RTL-SDR mappings by hand with `qm set`.
- Size a VM against the RAM its host has **now**. Moving DIMMs between machines
  leaves the guest config behind: a worker configured for more memory than its
  host holds does not fail loudly, it starves the node until kubelet stops
  posting status, the Talos API stops answering, and CNI and CSI DaemonSets sit
  `Pending`.
- `qm shutdown` needs the QEMU guest agent, which is not always running in these
  Talos guests. Prefer `talosctl -n <node> shutdown`. If the Talos API is also
  down, drain the node first — a hard `qm stop` marks every Longhorn replica on
  it failed, and single-replica volumes then need auto-salvage to recover.
