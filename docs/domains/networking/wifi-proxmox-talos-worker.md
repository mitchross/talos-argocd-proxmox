# Wi-Fi Proxmox Talos CPU worker

The solar-powered Dell OptiPlex with an Intel i5-8500 and 64 GiB physical RAM
behind the ASUS RT-AX86U media bridge is a CPU-only Talos worker managed by
Omni's `proxmox-dell` provider. The retired GTX 1050 Ti is not passed through
and the Talos image carries no NVIDIA extensions.

!!! warning "Desired state pending replacement"
    The repository now describes `dell-workers` with the
    `dell-worker` class. The old `dell-gpu-workers` node is offline and
    must be replaced through the ordered rollout below. Its Longhorn replica
    inventory was verified empty before this change.

## Target and source of truth

| Layer | Target | Owning configuration |
|---|---|---|
| Media bridge | ASUS RT-AX86U, Media Bridge mode | Host-side state |
| Hypervisor | Dell Proxmox VE, `192.168.10.16` | Host-side state |
| Omni provider | `proxmox-dell`, running on the NUC | `omni/proxmox-provider-dell/` |
| VM | 4 vCPU, 48 GiB RAM, 64 GiB boot + 400 GiB data disk | `omni/machine-classes/dell-worker.yaml` |
| Talos worker | Static `192.168.10.119` | `omni/cluster-template/cluster-template-singlenode-gpu.yaml` |
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

The replacement is destructive to the old VM, so do not combine these checks
into a blind template sync.

1. Verify the old Dell Longhorn replica inventory is empty:

   ```bash
   kubectl -n longhorn-system get replicas.longhorn.io \
     -l longhornnode=talos-singlenode-gpu-prod-dell-gpu-workers-kf5x8m
   ```

   Expected: no resources.

2. In **Node → Disks → LVM**, create the thick volume group/storage
   `dell-ssd-vmstore` on the unused Samsung `/dev/sda` with **Add Storage**
   enabled. Do not choose **LVM-Thin**. Stop if `/dev/sda` is no longer unused
   or does not match the Samsung serial shown in the disk audit.

3. Record the old VM's `SDR1` and `SDR-BLOGv4` mappings (`usb3=1`). Remove the
   GTX 1050 Ti mapping and remove or power down the physical card as intended.

4. Apply all changed machine classes, validate the template, and inspect the
   dry run:

   ```bash
   omnictl apply -f omni/machine-classes/threadripper-worker.yaml
   omnictl apply -f omni/machine-classes/threadripper-gpu-worker.yaml
   omnictl apply -f omni/machine-classes/dell-worker.yaml
   omnictl cluster template validate \
     -f omni/cluster-template/cluster-template-singlenode-gpu.yaml
   omnictl cluster template sync -v \
     -f omni/cluster-template/cluster-template-singlenode-gpu.yaml --dry-run
   ```

5. Stop if the dry run replaces the control plane or removes the RTX worker
   before the new `workers` MachineSet is Ready. Provision the 32 GiB general
   worker first and allow ordinary workloads to move there.

6. Replace the Dell with `dell-workers`, then reattach both RTL-SDR mappings.
   Only after the general and Dell CPU workers are Ready should the existing
   RTX VM be shut down and cold-resized from 96 to 64 GiB in Proxmox. Do not
   reprovision that VM: its attached disks own the live Longhorn data.

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

- Stop on a non-empty Dell replica inventory, an unhealthy Longhorn volume,
  or a dry run that touches the control plane unexpectedly.
- If the new Dell cannot register, verify DHCP, the media bridge, and that
  `kernelargs` remains empty.
- If Intercept cannot see radios, restore the recorded USB mappings on the
  replacement VM; do not move its pod to a node without the devices.
- Roll back by restoring the old MachineSet and machine class from Git, but do
  not restore NVIDIA passthrough unless the extra idle power is intentionally
  accepted.
