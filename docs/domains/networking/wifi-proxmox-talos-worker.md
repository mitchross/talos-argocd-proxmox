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

The Dell VM carries no USB devices. Intercept's two RTL-SDRs (`0bda:2838`)
and the Zigbee coordinator are USB-passed to the HP 600 G4 shed VM
(`hp-workers`, `omni/machine-classes/hp-worker.yaml`); Intercept and
Home Assistant follow the NFD labels
`feature.node.kubernetes.io/custom-usb.rtl-sdr` and
`custom-usb.zigbee-coordinator` rather than a node class. The provider schema
has no USB field, so those mappings are re-added by hand after a VM
replacement of that host.

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

3. Remove the GTX 1050 Ti mapping and remove or power down the physical card
   as intended.

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

6. Replace the Dell with `dell-workers`. For an incremental GPU change, only after the general and Dell CPU workers
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
   the Dell has no NVIDIA extensions or GPU labels; Longhorn reports `dell-ssd` schedulable at
   `/var/mnt/longhorn-dell-ssd`; and every volume remains healthy.

## Rollback and stop conditions

- Stop on a stale/failed backup, a failed restore canary, an unhealthy Longhorn
  volume, or a dry run that touches the control plane unexpectedly during an
  incremental rollout.
- If the new Dell cannot register, verify DHCP, the media bridge, and that
  `kernelargs` remains empty.
- Roll back by restoring the old MachineSet and machine class from Git, but do
  not restore NVIDIA passthrough unless the extra idle power is intentionally
  accepted.

## Known failure: nodes are Ready, but pods cannot cross nodes

After a clean rebuild, all four nodes can be `Ready` while Longhorn managers
crashloop and new PVCs remain `Pending`. `Ready` only proves that the nodes can
reach Kubernetes; it does not prove that pods can reach pods on other nodes.

Check Cilium from an agent pod:

```bash
kubectl exec -n kube-system <cilium-pod> -- cilium-health status --probe
```

`Node 1/1` with `Endpoints 0/1` means the normal network works but the pod
overlay does not. In the 2026-08-14 rebuild, the cause was a virtio checksum
offload bug—not the AX86U bridge, MTU, Cilium state, or the Dell's dedicated
2.5 GbE card.

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
config current. Adding the second guard produced a real config change and made
Talos re-apply the settings. It did not visibly reboot the nodes.

Success means Cilium reports `4/4 reachable`, including every endpoint, and all
Longhorn managers return to `2/2 Running`. Let existing CrashLoop backoff expire;
do not keep restarting Longhorn, change MTU, or redesign the bridge for this
symptom.
