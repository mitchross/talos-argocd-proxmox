# Bare-metal Talos workers

**Purpose:** add a machine to `talos-prod-cluster-v2` as a bare-metal Talos node,
or convert a Proxmox host to one. Bare-metal nodes PXE-boot into Omni through
[booter](https://github.com/mitchross/talos-argocd-proxmox/blob/main/omni/pi-services/booter/README.md)
on the Pi. They have no Proxmox provider and no machine class.

**Status:** current procedure. Three nodes use it today:

| Node | Hardware | Talos disk | Longhorn disk | Notes |
|---|---|---|---|---|
| `mini-pc-dell-ultra-worker` | Dell Pro Micro, Core Ultra 5 245T, 2× 16 GiB | KIOXIA BG7 NVMe | `dell-ultra-ssd` (Apple SATA SSD) | iGPU + NPU; runs Frigate (NPU detection, iGPU decode; [#3088](https://github.com/mitchross/talos-argocd-proxmox/issues/3088)) |
| `hp-elite-gen12` | HP Elite Mini 800 G9, i5-12500T, 2× 8 GiB | Samsung NVMe | — (compute-only) | Zigbee stick; Home Assistant runs here |
| `hp-elite-gen13` | HP Elite Mini 600 G9, i5-13500T, 1× 16 GiB | WD SN530 NVMe | `hp-elite-nvme` (Intel 660p) | Keeps class label `hp-elite-worker` |

Disk serials and roles are in the [disk map](../storage/disk-map.md).

## How it works

1. The machine finds no bootable disk and falls back to network boot.
2. booter serves iPXE, which loads Talos with the Omni join arguments.
3. Talos runs from RAM in maintenance mode and appears in **Omni → Machines**.
   Nothing is written to disk yet.
4. The cluster template pins the machine by UUID. A template sync installs Talos
   on the disk that `install.diskSelector` names, and the node joins.

## Add or convert a machine

### 1. Check the data first (conversion only)

The host's disks are wiped. Find every Longhorn volume with a replica there:

```bash
kubectl -n longhorn-system get replicas.longhorn.io -o json \
  | jq -r '.items[]|select(.spec.nodeID=="<old-node>")|.spec.volumeName'
```

Expected result: each volume has another healthy replica, a recent kopiur
snapshot, or a `backup-exempt` label. Restore or copy anything else before you
continue. Move any LXC or VM you still need off the host.

### 2. Set the BIOS and PXE-boot

Turn Secure Boot off. Turn network boot on, with the disk first. For a one-time
boot, press F12 on HP or Dell and pick IPv4 network boot. Follow the boot in
`docker logs -f booter` on the Pi.

Expected result: the machine shows as **available** in `omnictl get machines`.

### 3. Collect the UUID, disk serials and NICs

```bash
omnictl get machinestatus <uuid> -o yaml
```

Record `blockdevices[].serial`, `model` and `size`, plus `networklinks`.
Some SATA drives report no serial; match those by model.

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

If the machine has a second disk for Longhorn, add a `UserVolumeConfig` that
selects it by serial (or by `disk.model` when there is no serial), plus the
Longhorn `create-default-disk` label and `default-disks-config` annotation.
Without an install pin, Omni picks the smallest disk. Add new patches at the end
of a machine set's list: Omni numbers patch IDs by position.

Validate before the PR:

```bash
cd omni/cluster-template
omnictl cluster template validate -f cluster-template-prod-v2.yaml
omnictl cluster template diff -f cluster-template-prod-v2.yaml
```

Expected result: the diff adds only the new machine set, its patches and its
`MachineInstallDiskConfigs`. After merge, run
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

Longhorn reads `default-disks-config` only when its node first registers. For a
node that already exists, add the disk to the live node:

```bash
kubectl -n longhorn-system patch nodes.longhorn.io <node> --type merge -p \
  '{"spec":{"disks":{"<disk>":{"path":"/var/mnt/longhorn-<disk>","allowScheduling":true,"diskType":"filesystem","storageReserved":0,"tags":["<disk>"]}}}}'
```

Expected result: the disk shows `Ready` and `Schedulable` in
`nodes.longhorn.io/<node>` status.

### 7. Remove the old Proxmox VM (conversion only)

Remove the old `Workers` block from the template in the same PR as step 4.
If the old machine is offline, Omni cannot reset it and the teardown waits.
Delete its SideroLink, which removes the machine and its Kubernetes node:

```bash
omnictl get links
omnictl delete link <old-uuid>
```

Then remove the old Longhorn node. Longhorn refuses while the node allows
scheduling or still lists replicas. Delete the stale replica records first,
but only for volumes with healthy copies elsewhere:

```bash
kubectl -n longhorn-system patch nodes.longhorn.io <old-node> --type merge -p '{"spec":{"allowScheduling":false}}'
kubectl -n longhorn-system delete replicas.longhorn.io <stale-replica>...
kubectl -n longhorn-system delete nodes.longhorn.io <old-node>
```

Keep the host's Proxmox provider running until `omnictl get machinesets` no
longer lists the old set. The provider deletes the old VM through the Proxmox
API, so wipe Proxmox only after that.

Then remove the provider from `omni/proxmox-providers/docker-compose.yml` and
the Pi, and delete its machine class and Omni provider object:

```bash
docker compose stop <host> && docker compose rm -f <host>   # on the Pi
omnictl delete machineclasses.omni.sidero.dev <host>-worker
omnictl infraprovider delete proxmox-<host>
```

## Swap a node's NIC (for example a USB 2.5G adapter)

Talos needs no config change. These nodes have no per-NIC network settings, so
Talos runs DHCP on every physical NIC. The Talos kernel includes the Realtek
(`r8152`) and ASIX (`ax88179_178a`) USB NIC drivers. A USB NIC is named `enx<MAC>`.

1. In Firewalla, move the node's DHCP reservation to the new NIC's MAC. A new MAC
   otherwise gets a new IP.
2. Unplug the old cable, then plug in the new NIC. Use one NIC at a time: two
   cables give the node two IPs on the same subnet.
3. Check that the node is `Ready` with its old IP: `kubectl get node <node> -o wide`.
4. Check that the live L2 policy matches the new name:
   `kubectl get ciliuml2announcementpolicy l2-policy -o jsonpath='{.spec.interfaces}'`.
   If the lease holder's NIC does not match, its LoadBalancer IPs stop answering.

## Gotchas

| Symptom | Cause | Fix |
|---|---|---|
| `wipe disk` fails with `blockdevice "sdX" is in use by disk "dm-0"` | Talos auto-activates LVM volume groups it finds on reused disks | Remove the mapping from a privileged debug pod in `kube-system` (the default namespace enforces Pod Security `baseline`): `kubectl debug -n kube-system node/<node> --profile=sysadmin --image=alpine:3.22 -q --attach=true -- sh -c 'apk add -q device-mapper && dmsetup remove <vg>-<lv>'`. Then wipe. Find `<vg>-<lv>` with `talosctl -n <ip> ls /dev/mapper`. |
| Volume status `no disks matched … 1 have wrong format` | The selected disk still holds old partitions or LVM | Wipe the disk (step 5) |
| Longhorn node shows no data disk after the volume is ready | The node registered before the disk existed | Patch the live node (step 6) |
| `talosctl` loops on browser login (`invalid signature`, "this login link is not valid") | Its context name does not match the key `omnictl` registered | `omnictl talosconfig -c talos-prod-cluster-v2 --force <file>`, rename the context to `default`, and pass `--talosconfig <file>` |
| Old machine stays `tearingDown` | Omni cannot reach the machine to reset it | `omnictl delete link <uuid>` (step 7) |
| Old machine set and machine request stay `tearingDown`; provider logs `no route to host` on `:8006` | Proxmox was removed before the provider deleted the VM | Stop the provider on the Pi, then `omnictl infraprovider delete proxmox-<host>` (step 7) |
| Machine boots the old OS instead of PXE | The disk is still bootable | Use F12 one-time network boot until Talos is installed |
| A merged change is not live and the app stays `OutOfSync` | ArgoCD auto-sync does not retry a revision whose sync failed (for example, it timed out while a node was down) | Sync the app or the one resource by hand |

## Add a disk to an existing Proxmox VM

The Proxmox provider sets disks only when it creates a VM. To hot-add a disk to a
running worker, follow [adding a disk to a running node](../storage/disk-map.md#adding-a-disk-to-a-running-node).
On a host disk that is empty, first run `vgcreate <vg> /dev/<disk>` and
`pvesm add lvm <storage> --vgname <vg> --content images`.
