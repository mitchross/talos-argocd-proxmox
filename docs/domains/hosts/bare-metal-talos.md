# Bare-metal Talos workers

This page shows how to add a machine to `talos-prod-cluster-v2` as a bare-metal Talos
node, or convert a Proxmox host to one. A bare-metal node runs Talos directly on the
hardware, with no Proxmox, no Proxmox provider, and no machine class.

A conversion wipes every disk in the host. The procedure changes the Omni cluster
template and, for a conversion, removes the old Proxmox VM and its provider. It
leaves the other nodes alone.

Three bare-metal nodes use this procedure. One TrueNAS VM uses the same PXE path; see
[Add a TrueNAS VM](#add-a-truenas-vm).

| Node | Longhorn disk | Notes |
|---|---|---|
| `mini-pc-dell-ultra-worker` | `dell-ultra-ssd` | Has an iGPU and an NPU. Runs Frigate (NPU detection, iGPU decode) |
| `hp-elite-gen12` | None (compute-only) | Holds the Zigbee stick. Home Assistant runs here |
| `hp-elite-gen13` | `hp-elite-nvme` | Keeps the class label `hp-elite-worker` |
| `truenas-worker-01` | `truenas-ssd` | VM `talosnas1` on the TrueNAS DL360 |

The hardware in each machine is in the [fleet inventory](../../inventory/2026-11-03-fleet-inventory.md).
Disk serials and roles are in the [disk map](../storage/disk-map.md).

## How it works

A bare-metal node PXE-boots, which means it loads its operating system from the
network. The [booter](https://github.com/mitchross/talos-argocd-proxmox/blob/main/omni/pi-services/booter/README.md)
service on the Pi answers the boot request.

1. The machine finds no bootable disk and falls back to network boot.
2. booter serves iPXE, which loads Talos with the Omni join arguments.
3. Talos runs from RAM in maintenance mode and appears in **Omni → Machines**.
   Talos has written nothing to disk at this point.
4. The cluster template pins the machine by UUID. A template sync installs Talos
   on the disk that `install.diskSelector` names, and the node joins.

## Before you start

You need `omnictl`, `talosctl` and `kubectl` access to the cluster, and SSH access to
the Pi for the booter logs. For a conversion, complete step 1 before you touch the
host.

## Add or convert a machine

### 1. Check the data first (conversion only)

The conversion wipes the host's disks. Find every Longhorn volume that has a replica
on the old node:

```bash
kubectl -n longhorn-system get replicas.longhorn.io -o json \
  | jq -r '.items[]|select(.spec.nodeID=="<old-node>")|.spec.volumeName'
```

Expected result: each volume has another healthy replica, a recent backup, or a
`backup-exempt` label. Restore or copy anything else before you continue. Move any
LXC or VM that you still need off the host.

### 2. Set the BIOS and PXE-boot

Turn Secure Boot off. Turn network boot on, with the disk first in the boot order.
For a one-time network boot, press F12 on HP or Dell and pick IPv4 network boot.
Follow the boot with `docker logs -f booter` on the Pi.

Expected result: the machine shows as **available** in `omnictl get machines`.

### 3. Collect the UUID, disk serials and NICs

```bash
omnictl get machinestatus <uuid> -o yaml
```

Record `blockdevices[].serial`, `model` and `size`, plus `networklinks`. Some SATA
drives report no serial. Match those drives by model.

### 4. Add the machine to the template

In `omni/cluster-template/cluster-template-prod-v2.yaml`, add a `Workers` block
with `machines: [<uuid>]`. Copy an existing bare-metal block for the extensions
(`intel-ucode`, `i915`, storage tools; no `qemu-guest-agent`) and the kubelet
reservations. Add a `kind: Machine` block:

```yaml
kind: Machine
name: <uuid>
install:
  diskSelector: disk.serial == "<system-disk-serial>"
```

Always set the install pin. Without it, Omni installs Talos on the smallest disk.

If the machine has a second disk for Longhorn, add a `UserVolumeConfig` that selects
it by serial, or by `disk.model` when the disk has no serial. Also add the Longhorn
`create-default-disk` label and the `default-disks-config` annotation.

Add new patches at the end of a machine set's list, because Omni numbers patch IDs
by position.

Validate before you open the PR:

```bash
cd omni/cluster-template
omnictl cluster template validate -f cluster-template-prod-v2.yaml
omnictl cluster template diff -f cluster-template-prod-v2.yaml
```

Expected result: the diff adds only the new machine set, its patches and its
`MachineInstallDiskConfigs`. After the merge, run
`omnictl cluster template sync -f cluster-template-prod-v2.yaml`.

### 5. Wipe reused data disks

Talos claims only free space for a user volume. A disk with old partitions or a
Proxmox LVM stays unused until you wipe it. Confirm the device first:

```bash
talosctl -n <ip> get disks
talosctl -n <ip> get systemdisk
talosctl -n <ip> wipe disk <dev> --drop-partition
```

Expected result: `talosctl get volumestatus u-<volume-name>` reaches `ready`.

### 6. Register the disk in Longhorn

Longhorn reads `default-disks-config` only when its node first registers. For a node
that already exists, add the disk to the live Longhorn node:

```bash
kubectl -n longhorn-system patch nodes.longhorn.io <node> --type merge -p \
  '{"spec":{"disks":{"<disk>":{"path":"/var/mnt/longhorn-<disk>","allowScheduling":true,"diskType":"filesystem","storageReserved":0,"tags":["<disk>"]}}}}'
```

Expected result: the disk shows `Ready` and `Schedulable` in the status of
`nodes.longhorn.io/<node>`.

### 7. Remove the old Proxmox VM (conversion only)

Remove the old `Workers` block from the template in the same PR as step 4.

If the old machine is offline, Omni cannot reset it and the teardown waits. Delete
its SideroLink, the connection between the machine and Omni. This removes the
machine and its Kubernetes node:

```bash
omnictl get links
omnictl delete link <old-uuid>
```

Then remove the old Longhorn node. Longhorn refuses while the node allows scheduling
or still lists replicas. Delete the stale replica records first, but only for
volumes that have healthy copies elsewhere:

```bash
kubectl -n longhorn-system patch nodes.longhorn.io <old-node> --type merge -p '{"spec":{"allowScheduling":false}}'
kubectl -n longhorn-system delete replicas.longhorn.io <stale-replica>...
kubectl -n longhorn-system delete nodes.longhorn.io <old-node>
```

Keep the host's Proxmox provider running until `omnictl get machinesets` no longer
lists the old set. The provider deletes the old VM through the Proxmox API, so wipe
Proxmox only after that.

Then remove the provider from `omni/proxmox-providers/docker-compose.yml` and from
the Pi. Delete its machine class and its Omni provider object:

```bash
docker compose stop <host> && docker compose rm -f <host>   # on the Pi
omnictl delete machineclasses.omni.sidero.dev <host>-worker
omnictl infraprovider delete proxmox-<host>
```

## Add a TrueNAS VM

A VM on the NAS joins the same way as a mini PC: it PXE-boots from booter, and the
template pins it by UUID. The NAS has no Omni provider, so you create the VM by hand.
`truenas-worker-01` is the reference.

1. Create the VM in **TrueNAS → Virtual Machines → Add**:

   | Setting | Value |
   |---|---|
   | Boot method | UEFI, Secure Boot off |
   | Start on boot | on |
   | CPU | 1 socket, 8 cores, 1 thread, Host Passthrough |
   | Memory | 64 GiB |
   | Disk 1 (system) | VirtIO, new volume on pool `vm-ssd`, 60 GiB |
   | Disk 2 (Longhorn) | VirtIO, new volume on pool `vm-ssd`, 230 GiB |
   | NIC | VirtIO, attached to `eno50` |
   | Installation media | none |

2. Attach the NIC to `eno50`, not to `eno49`. A VM attached to the NAS's own port
   cannot reach the NAS, so NFS and the kopiur repository fail.
3. TrueNAS refuses a volume larger than 80% of the pool's free space. Create the
   60 GiB volume first; 230 GiB is then the limit on the 370 GiB pool.
4. Start the VM and choose the PXE entry once. See
   [booter: TrueNAS VMs](https://github.com/mitchross/talos-argocd-proxmox/blob/main/omni/pi-services/booter/README.md#truenas-vms).
5. Continue with steps 3 and 4 above. VM disks report no serial, so select them by
   size: `disk.size < 100u * GB` for the install disk and `disk.size >= 200u * GB`
   for the Longhorn volume. Leave out `intel-ucode`, `i915` and the watchdog patch.

Expected result: the node is `Ready`, and `talosctl get volumestatus u-longhorn-truenas-ssd`
reaches `ready`.

VM memory comes out of the RAM that the ZFS cache uses. A NAS reboot stops the VM
together with NFS and the kopiur repository.

## Swap a node's NIC (for example a USB 2.5G adapter)

Talos needs no config change. These nodes have no per-NIC network settings, so Talos
runs DHCP on every physical NIC. The Talos kernel includes the Realtek (`r8152`) and
ASIX (`ax88179_178a`) USB NIC drivers. Talos names a USB NIC `enx<MAC>`.

1. In Firewalla, move the node's DHCP reservation to the MAC of the replacement NIC.
   Otherwise the node gets a different IP.
2. Unplug the old cable, then plug in the replacement NIC. Use one NIC at a time,
   because two cables give the node two IPs on the same subnet.
3. Check that the node is `Ready` with its old IP: `kubectl get node <node> -o wide`.
4. Check that the live L2 policy matches the NIC name:
   `kubectl get ciliuml2announcementpolicy l2-policy -o jsonpath='{.spec.interfaces}'`.
   If the NIC of the lease holder does not match, its LoadBalancer IPs stop answering.

## Add a disk to an existing Proxmox VM

The Proxmox provider sets disks only when it creates a VM. To hot-add a disk to a
running worker, follow [adding a disk to a running node](../storage/disk-map.md#adding-a-disk-to-a-running-node).
On a host disk that is empty, first run `vgcreate <vg> /dev/<disk>` and
`pvesm add lvm <storage> --vgname <vg> --content images`.

## What goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| `wipe disk` fails with `blockdevice "sdX" is in use by disk "dm-0"` | Talos auto-activates LVM volume groups it finds on reused disks | Remove the mapping from a privileged debug pod in `kube-system` (the default namespace enforces Pod Security `baseline`): `kubectl debug -n kube-system node/<node> --profile=sysadmin --image=alpine:3.22 -q --attach=true -- sh -c 'apk add -q device-mapper && dmsetup remove <vg>-<lv>'`. Then wipe. Find `<vg>-<lv>` with `talosctl -n <ip> ls /dev/mapper`. |
| Volume status `no disks matched … 1 have wrong format` | The selected disk still holds old partitions or LVM | Wipe the disk (step 5) |
| Longhorn node shows no data disk after the volume is ready | The node registered before the disk existed | Patch the live node (step 6) |
| `talosctl` loops on browser login (`invalid signature`, "this login link is not valid") | Its context name does not match the key `omnictl` registered | `omnictl talosconfig -c talos-prod-cluster-v2 --force <file>`, rename the context to `default`, and pass `--talosconfig <file>` |
| Old machine stays `tearingDown` | Omni cannot reach the machine to reset it | `omnictl delete link <uuid>` (step 7) |
| Old machine set and machine request stay `tearingDown`; provider logs `no route to host` on `:8006` | Proxmox was removed before the provider deleted the VM | Stop the provider on the Pi, then `omnictl infraprovider delete proxmox-<host>` (step 7) |
| Machine boots the old OS instead of PXE | The disk is still bootable | Use F12 one-time network boot until Talos is installed |
| A merged change is not live and the app stays `OutOfSync` | Argo CD auto-sync does not retry a revision whose sync failed (for example, it timed out while a node was down) | Sync the Application or the one resource by hand |
