# Dell Proxmox Talos CPU worker

The Dell OptiPlex 7060 (Intel i5-8500, 56 GB RAM) is a CPU-only Talos worker
managed by Omni's `proxmox-dell` infrastructure provider. It joins the cluster
as the `dell-workers` machine set and carries a dedicated Longhorn disk. The
retired GTX 1050 Ti is not passed through and the Talos image carries no NVIDIA
extensions.

!!! warning "MachineClass updates are not in-place VM updates"
    Applying a changed machine class only affects future Omni allocations; it
    does not rename, resize, or replace an existing VM. Use the ordered
    replacement below, or the root README's full-cluster rebuild, to make live
    hardware match the class.

## Target and source of truth

| Layer | Target | Owning configuration |
|---|---|---|
| Hypervisor | Dell Proxmox VE, `192.168.10.16` | Host-side state |
| Omni provider | `proxmox-dell`, running on the rpi5 | `omni/proxmox-providers/` (`dell` service) |
| VM | 6 vCPU, 46 GiB RAM, 128 GiB boot + 400 GiB data disk | `omni/machine-classes/dell-worker.yaml` |
| Talos worker | DHCP on `vmbr0`, zone `dell`, link `wired` | `omni/cluster-template/cluster-template-prod-v2.yaml` |
| Node class | `node.vanillax.dev/class=dell-worker` | same cluster template |
| Longhorn | Unschedulable boot disk + schedulable Samsung SSD | same cluster template |

## Networking

The host is wired at 2.5 GbE through an add-in RTL8125B card (`uplink25g`,
bridged as `vmbr0`). The onboard Intel I219 (`nic0`) is deliberately unused:
it produced 2,640 "Detected Hardware Unit Hang" dumps before a hard host crash,
a known e1000e offload bug. The host keeps TSO/GSO/GRO off on that NIC.

The machine class carries no `ip=` kernel argument and the worker uses plain
DHCP. A static `ip=` argument with an empty interface previously bound to Talos
`bond0`, installed a dead default route, and blackholed guest-originated
traffic. Never pin a NIC name in the machine config either.

## Storage

The host boots Proxmox from a 251 GB SSD (`/dev/sdb`, LVM-thin `local-lvm`,
151 GiB pool) and carries a separate Samsung 500 GB SSD at `/dev/sda`. That
second device is exposed as the **thick**-LVM Proxmox storage
`dell-ssd-vmstore` — do not use LVM-Thin for it; this repo has measured thin
metadata commits collapsing fsync performance.

The machine class puts the 128 GiB boot disk on `local-lvm` and a 400 GiB data
disk on `dell-ssd-vmstore`, so Longhorn replica writes and container image
pulls land on different physical devices. Talos formats the data disk as
`longhorn-dell-ssd`, mounts it at `/var/mnt/longhorn-dell-ssd`, and registers
it as a schedulable Longhorn disk tagged `dell-ssd`. The boot disk registers
unschedulable.

That adds capacity, not redundancy: a single-replica volume placed here is
unavailable whenever this host is down. Raise replica counts if a workload
needs availability rather than space.

## Hardware-bound workload

The Dell VM carries no USB devices. Intercept's two RTL-SDRs (`0bda:2838`) go to
the HP 600 G4 shed VM (`hp-micro-workers`,
`omni/machine-classes/hp-micro-worker.yaml`) and the Zigbee coordinator to the HP
Elite VM (`hp-elite-workers`, `omni/machine-classes/hp-elite-worker.yaml`);
Intercept and Home Assistant follow the NFD labels
`feature.node.kubernetes.io/custom-usb.rtl-sdr` and
`custom-usb.zigbee-coordinator` rather than a node class. Each machine class
declares its devices in a `usb_devices:` list of Proxmox Resource Mappings, so a
replaced VM comes back with them attached.

Frigate is pinned to `node.vanillax.dev/class=dell-worker` and currently scaled
to zero. It uses CPU software decode and OpenVINO CPU detection — no NVIDIA
runtime class, GPU resource request, driver capability environment, or
`preset-nvidia` ffmpeg configuration.

## Ordered rollout

Machine replacement destroys provider-owned VM disks. For a full-cluster
replacement, use the root README's rebuild procedure and satisfy every gate in
`docs/disaster-recovery.md`. The sequence below is for an incremental Dell
replacement; do not combine it into a blind template sync.

1. Verify every protected PVC has a recent successful off-host kopiur snapshot,
   the restore canary has a recent passing drill, and every Longhorn volume is
   healthy:

   ```bash
   kubectl get snapshots.kopiur.home-operations.com -A
   kubectl -n longhorn-system get volumes.longhorn.io
   ```

   Do not infer safety from an empty replica query against an old node name.
   The live Dell is a schedulable Longhorn target, and deleting its VM destroys
   its 400 GiB provider-owned disk.

2. In **Node → Disks → LVM**, confirm the thick volume group/storage
   `dell-ssd-vmstore` exists on the Samsung `/dev/sda` with **Add Storage**
   enabled. Stop if `/dev/sda` is no longer that device.

3. Apply the machine class, validate the template, and inspect the dry run:

   ```bash
   omnictl apply -f omni/machine-classes/dell-worker.yaml
   omnictl cluster template validate \
     -f omni/cluster-template/cluster-template-prod-v2.yaml
   omnictl cluster template sync -v \
     -f omni/cluster-template/cluster-template-prod-v2.yaml --dry-run
   ```

4. Remember that the dry run updates MachineSet class references but does not
   replace existing allocations.

5. Sync, then verify:

   ```bash
   kubectl get nodes -o wide -L node.vanillax.dev/class,topology.kubernetes.io/zone
   kubectl get pods -A -o wide --field-selector spec.nodeName=<new-dell-node>
   kubectl -n longhorn-system get nodes.longhorn.io <new-dell-node> -o yaml
   ```

   Expected: the node is `Ready` with class `dell-worker` and zone `dell`, it
   advertises no NVIDIA GPUs or extensions, Longhorn reports `dell-ssd`
   schedulable at `/var/mnt/longhorn-dell-ssd`, and every volume stays healthy.

## Rollback and stop conditions

- Stop on a stale/failed backup, a failed restore canary, an unhealthy Longhorn
  volume, or a dry run that touches the control plane unexpectedly during an
  incremental rollout.
- If the new worker cannot register, verify DHCP on `vmbr0` and that
  `kernelargs` remains empty.
- Roll back by restoring the previous MachineSet and machine class from Git.

## Known failure: nodes are Ready, but pods cannot cross nodes

After a clean rebuild, every node can be `Ready` while Longhorn managers
crashloop and new PVCs remain `Pending`. `Ready` only proves that the nodes can
reach Kubernetes; it does not prove that pods can reach pods on other nodes.

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
config current. Adding the second guard produced a real config change and made
Talos re-apply the settings. It did not visibly reboot the nodes.

Success means Cilium reports every node and endpoint reachable and all Longhorn
managers return to `2/2 Running`. Let existing CrashLoop backoff expire; do not
keep restarting Longhorn, change MTU, or redesign the bridge for this symptom.
