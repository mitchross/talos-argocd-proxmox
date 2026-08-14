# Wi-Fi Proxmox Talos CPU worker

The solar-powered Dell OptiPlex with an Intel i5-8500 and 64 GiB physical RAM
behind the ASUS RT-AX86U media bridge is a CPU-only Talos worker managed by
Omni's `proxmox-dell` provider. The retired GTX 1050 Ti is not passed through
and the Talos image carries no NVIDIA extensions.

!!! warning "MachineClass updates are not in-place VM updates"
    The repository describes `dell-workers` with the `dell-worker` class.
    Applying that class only changes future Omni allocations; it does not
    rename, resize, or replace an existing VM. Use the ordered replacement
    checks below, or the root README's full-cluster rebuild, to make live
    hardware match the class.

## Target and source of truth

| Layer | Target | Owning configuration |
|---|---|---|
| Media bridge | ASUS RT-AX86U, Media Bridge mode | Host-side state |
| Hypervisor | Dell Proxmox VE, `192.168.10.16` | Host-side state |
| Omni provider | `proxmox-dell`, running on the NUC | `omni/proxmox-provider-dell/` |
| VM | 4 vCPU, 48 GiB RAM, 64 GiB boot + 400 GiB data disk | `omni/machine-classes/dell-worker.yaml` |
| Talos worker | Static `192.168.10.119` | `omni/cluster-template/cluster-template-threadripper-gpu-workers.yaml` |
| Node class | `node.vanillax.dev/class=dell-worker` | same cluster template |
| Longhorn | Unschedulable boot disk + schedulable Samsung SSD | same cluster template |

The Dell boots Proxmox from its 251 GB SSD and has a separate, unused Samsung
500 GB SSD at `/dev/sda`. Create a thick-LVM Proxmox storage named
`dell-ssd-vmstore` on `/dev/sda`; the machine class attaches a 400 GiB virtual
disk from that pool. Talos formats it as `longhorn-dell-ssd`, mounts it at
`/var/mnt/longhorn-dell-ssd`, and registers the Longhorn disk as schedulable.
The 64 GiB boot disk remains unschedulable.

The VM receives 48 of the host's 64 GiB RAM. The remaining 16 GiB is required
for Proxmox and provider overhead; do not allocate the full physical capacity
to the guest.

This adds capacity, not redundancy. With one replica, a volume placed on Dell
is unavailable whenever the Dell or Wi-Fi bridge is down. Increasing replica
counts would put synchronous Longhorn writes across Wi-Fi and is a separate
performance/availability decision.

The machine class deliberately carries no `ip=` kernel argument. DHCP is
required for the ISO registration phase. A static `ip=` argument with an
empty interface previously bound to Talos `bond0`, installed a dead default
route, and blackholed guest-originated traffic. Static `192.168.10.119` takes
over only after Omni applies the machine configuration.

## Hardware-bound workload

Intercept uses two RTL-SDR USB devices through `/dev/bus/usb` and selects
`node.vanillax.dev/class=dell-worker`. Before destroying the old VM, record
the Dell Proxmox VM's USB mappings: `SDR1` and `SDR-BLOGv4`, both with
`usb3=1`. The upstream provider schema has no USB field, so reattach both
mappings to the replacement VM before expecting Intercept to become Ready.

Frigate is currently scaled to zero. Its manifest remains pinned to the Dell,
but now uses CPU software decode and OpenVINO CPU detection. It no longer has
an NVIDIA runtime class, GPU resource request, driver capability environment,
or `preset-nvidia` ffmpeg configuration.

## Ordered rollout

Machine replacement destroys provider-owned VM disks. For a full-cluster
replacement, use the root README's rebuild procedure and satisfy every gate in
`docs/disaster-recovery.md`. The sequence below is for an incremental Dell
replacement; do not combine it into a blind template sync.

1. Verify every protected PVC has a recent successful off-host kopiur snapshot,
   the restore canary has a recent passing drill, every database has a
   recent completed Barman backup, and every Longhorn volume is healthy:

   ```bash
   kubectl get snapshots.kopiur.home-operations.com -A
   kubectl -n longhorn-system get volumes.longhorn.io
   ```

   Do not infer safety from an empty replica query against an old node name.
   The live Dell is a schedulable Longhorn target, and deleting its VM destroys
   its 400 GiB provider-owned disk.

2. In **Node → Disks → LVM**, create the thick volume group/storage
   `dell-ssd-vmstore` on the unused Samsung `/dev/sda` with **Add Storage**
   enabled. Do not choose **LVM-Thin**. Stop if `/dev/sda` is no longer unused
   or does not match the Samsung serial shown in the disk audit.

3. Record the old VM's `SDR1` and `SDR-BLOGv4` mappings (`usb3=1`). Remove the
   GTX 1050 Ti mapping and remove or power down the physical card as intended.

4. Apply all changed machine classes, validate the template, and inspect the
   dry run:

   ```bash
   omnictl apply -f omni/machine-classes/threadripper-control-plane.yaml
   omnictl apply -f omni/machine-classes/threadripper-worker.yaml
   omnictl apply -f omni/machine-classes/threadripper-gpu-worker.yaml
   omnictl apply -f omni/machine-classes/dell-worker.yaml
   omnictl cluster template validate \
     -f omni/cluster-template/cluster-template-threadripper-gpu-workers.yaml
   omnictl cluster template sync -v \
     -f omni/cluster-template/cluster-template-threadripper-gpu-workers.yaml --dry-run
   ```

5. Remember that the dry run updates MachineSet class references but does not
   replace existing allocations. For an incremental rollout, provision the
   24 GiB general worker first and allow ordinary workloads to move there.

6. Replace the Dell with `dell-workers`, then reattach both RTL-SDR mappings.
   For an incremental GPU change, only after the general and Dell CPU workers
   are Ready should the existing RTX VM be shut down and cold-resized. For a
   full rebuild, the provider recreates its disks and application data must
   return from the verified off-host backups.

7. Verify:

   ```bash
   kubectl get nodes -o wide \
     -L node.vanillax.dev/class,node.vanillax.dev/gpu-class,gpu-worker
   kubectl get nodes -l nvidia.com/gpu.present=true
   kubectl get pods -A -o wide --field-selector spec.nodeName=<new-dell-node>
   kubectl -n longhorn-system get nodes.longhorn.io <new-dell-node> -o yaml
   talosctl -n 192.168.10.119 get extensions
   ```

   Expected: four Ready nodes total; only the RTX node advertises NVIDIA GPUs;
   the Dell has no NVIDIA extensions or GPU labels; Intercept sees both SDRs;
   Longhorn reports `dell-ssd` schedulable at
   `/var/mnt/longhorn-dell-ssd`; and every volume remains healthy.

## Rollback and stop conditions

- Stop on a stale/failed backup, a failed restore canary, an unhealthy Longhorn
  volume, or a dry run that touches the control plane unexpectedly during an
  incremental rollout.
- If the new Dell cannot register, verify DHCP, the media bridge, and that
  `kernelargs` remains empty.
- If Intercept cannot see radios, restore the recorded USB mappings on the
  replacement VM; do not move its pod to a node without the devices.
- Roll back by restoring the old MachineSet and machine class from Git, but do
  not restore NVIDIA passthrough unless the extra idle power is intentionally
  accepted.

## Known failure: pod overlay (VXLAN) does not cross the Wi-Fi bridge

**Observed 2026-08-14, on the clean-slate rebuild of `talos-threadripper-gpu-workers`.**

The Dell worker joins the cluster, reports `Ready`, and is reachable at
`192.168.10.119` — but **no pod on it can talk to a pod on any other node**.
Node-to-node L3 works; the Cilium VXLAN overlay does not survive the AX86U
media bridge.

### Symptom

Longhorn never finishes bootstrapping. `longhorn-manager` on the Dell node
crashloops with:

```
level=fatal msg="Error starting webhooks: admission webhook service is not
accessible on cluster after 2m0s sec: timed out waiting for endpoint
https://longhorn-admission-webhook.longhorn-system.svc:9502/v1/healthz"
```

and earlier, DNS itself times out from that pod:

```
dial tcp: lookup longhorn-admission-webhook.longhorn-system.svc on 10.96.0.10:53:
read udp 10.244.3.201:37863->10.96.0.10:53: i/o timeout
```

The tell is that this **flips with webhook leadership**. `longhorn-admission-webhook`
is served by a `longhorn-manager` pod, so:

- webhook lands on the Dell pod → the three Threadripper managers time out
- webhook lands on a Threadripper pod → the Dell manager times out

Whoever is co-located with the webhook works. That symmetry rules out a
Longhorn bug and points squarely at cross-node pod networking.

Downstream, every PVC stays `Pending`, so most of the cluster sits unschedulable
with `pod has unbound immediate PersistentVolumeClaims`.

### Diagnosis (one command)

```bash
kubectl exec -n kube-system <cilium-pod-on-dell> -c cilium-agent -- cilium-health status
```

```
Cluster health:                     1/4 reachable
Name                                IP               Node   Endpoints
  ...dell-workers-... (localhost)   192.168.10.119   1/1    1/1
  ...control-planes-...             192.168.10.139   1/1    0/1
  ...gpu-workers-...                192.168.10.177   1/1    0/1
  ...workers-...                    192.168.10.166   1/1    0/1
```

**`Node 1/1` with `Endpoints 0/1` is the signature.** The node IP is reachable;
the overlay path to pods on that node is not. If both columns were `0/1` this
would be ordinary L3 loss and a different problem.

### What the evidence actually shows

Packet capture on both ends (`talosctl pcap -i eth0`, 25 s, taken 2026-08-14)
disproves the simple "the bridge blocks VXLAN" reading:

```
DELL eth0 (192.168.10.119) — VXLAN packets
   109  192.168.10.177 -> 192.168.10.119
   107  192.168.10.119 -> 192.168.10.177     <- flowing BOTH ways
     1  192.168.10.166 -> 192.168.10.119
     1  192.168.10.139 -> 192.168.10.119
```

VXLAN is on the wire in both directions between the Dell node and `.177`.
Packets arrive and are still not usable — so the traffic is being dropped
*after* decapsulation, not filtered on the link.

Two hypotheses are ruled out by this:

- **Not MTU.** DNS queries (~70 bytes) and `cilium-health` probes time out.
  MTU problems let small packets through and break large ones. A TCP connect
  timing out on a 60-byte SYN is not an MTU symptom.
- **Not stale Cilium state.** `cilium-dbg node list` on the Dell node lists all
  four nodes with correct pod CIDRs and node IPs, identical to the view from a
  Threadripper node.

### The asymmetry worth chasing

`tx-checksum-ip-generic` on `eth0`, read from `talosctl get ethernetstatus`:

| Node | Setting |
| --- | --- |
| `192.168.10.119` (Dell) | **off** |
| `192.168.10.166` (workers) | **on** |
| `192.168.10.177` (gpu-workers) | **on** |
| `192.168.10.139` (control-plane) | **on** |

The cluster-scoped `vxlan-inner-checksum` patch sets this to `false`, so it
should be **off on all four**. It is off on exactly one. Three nodes are
transmitting VXLAN under precisely the condition the patch exists to avoid,
which fits packets arriving and then being discarded.

**Unconfirmed:** why the patch took on one node and not the others. Reading the
running machine config to prove it (`talosctl get machineconfig`) returned
nothing in this Talos version, so the delivery path was never verified — only
the resulting state. Establish that before changing anything.

This also fits the strongest piece of evidence: **the same topology worked
before the cluster was rebuilt.** That points at configuration drift introduced
during reprovisioning, not at the Wi-Fi link being fundamentally unsuitable.

### Options

- **First, explain the asymmetry.** Confirm whether the `EthernetConfig`
  document reached the three Threadripper nodes at all. If it did not, that is
  the bug, and it is a config-delivery problem rather than a network one.
- **Do not reach for an MTU change.** It does not match the symptom, and it is
  architectural churn against a topology with a working history.
- **Making the Dell node compute-only does not fix this.** Pods on it still
  cannot reach pods elsewhere; it only avoids putting Longhorn replicas across
  Wi-Fi.
- **Wired Ethernet for the Dell host** remains the durable answer, but the
  evidence above says something regressed in the rebuild — find that first.

### Do not

- Do not keep restarting `longhorn-manager`. It will crashloop indefinitely,
  because the webhook it needs is unreachable by design of the current network.
- Do not raise Longhorn replica counts to "heal" the volumes. That puts
  synchronous replication across Wi-Fi, which the rollout notes already warn
  against.
