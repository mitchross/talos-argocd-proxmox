# Control plane: 1 to 3 members

## Current state

One control plane VM runs on hp-sff (`192.168.10.21`). Omni provisions it from
the `hp-sff-control-plane` class. etcd tolerates zero failures. The rule
"never delete the only control plane" applies until step 6 below completes.

## Target state

Three control planes on three wired hosts: hp-sff, the HP Elite Mini 800 G9 and
the Dell Pro Micro QCM1250. The template's `ControlPlane` document selects them
with the `control-plane-ha` class (`omni/machine-classes/control-plane-ha.yaml`),
which matches the machine label `vanillax.dev/role = control-plane`.

Why a label class: one Proxmox provider points at one host, and a `ControlPlane`
document takes one class. Autoprovisioning cannot spread three CPs over three
standalone hosts. Hand-built VMs plus a label class can.

## Rules

- Keep an odd member count. Go 1 to 3 in one sync. Never run two members.
- Never sync the `size: 3` template before both new VMs are registered in Omni
  with the label. Omni rolls CP changes one machine at a time.
- Do not add CPs to repair a broken quorum.
- Machine-class edits do not resize running VMs.

## New CP VM spec (per Mini)

Build with `qm create` on the Mini's Proxmox host. Match the hp-sff CP class:

| Setting | Value |
|---|---|
| cores / sockets | 4 / 1 |
| memory | 12288 MiB, `balloon: 0` |
| cpu / machine / bios | `host` / `q35` / `seabios` |
| scsi0 | 100 GiB, thick LVM, `cache=none,iothread=1,aio=io_uring,discard=on,ssd=1` |
| net0 | `virtio`, `vmbr0` (wired) |
| boot media | Omni ISO generated with `omnictl download --initial-labels vanillax.dev/role=control-plane` |
| onboot | 1 |

One 100 GiB system disk. The template's `control-plane-ephemeral` (64 GiB) and
`control-plane-etcd` (32 GiB) `VolumeConfig` patches carve etcd out of it, the
same layout the hp-sff CP uses today. Never put the VM disk on lvmthin.

## Procedure

1. Take an etcd snapshot off-node:
   `talosctl -n <cp-ip> etcd snapshot /tmp/etcd-pre-ha.db` and copy it off the node.
2. Install Proxmox on both Minis. BIOS: power on after power loss. Build the two
   CP VMs from the table above and boot them from the labelled Omni ISO. Confirm
   both appear in Omni as unallocated machines with the label.
3. Add the same label to the existing hp-sff CP machine in the Omni UI
   (Machines, select the machine, Labels). Confirm with
   `omnictl get machinestatus -o yaml | grep -B2 'vanillax.dev/role'`.
4. Apply the class: `omnictl apply -f omni/machine-classes/control-plane-ha.yaml`.
5. Dry-run: `git pull` first (a stale `main` makes the sync a silent no-op), then
   `omnictl cluster template diff -f omni/cluster-template/cluster-template-prod-v2.yaml`.
   Accept only if the diff adds two MachineSetNodes to the control-planes set and
   does not remove the existing CP machine. If it removes it, stop. Omni's
   behaviour when a class-allocated CP set switches to a label class is not
   documented; the diff is the proof.
6. Sync: `omnictl cluster template sync -f omni/cluster-template/cluster-template-prod-v2.yaml`.
   Expected: `omnictl get clustermachinestatus` shows three Ready control planes
   and `talosctl etcd members` lists three members.
7. Soak seven days. Watch `etcd_server_leader_changes_seen_total` (at most one
   change) and `etcd_server_proposals_failed_total` (zero) in Grafana.

## Rollback

Before step 6: revert the template `ControlPlane` block to
`hp-sff-control-plane` / `size: 1`; nothing has changed on the cluster.
After step 6: do not scale back to 1 while any member is unhealthy. Restore from
the step 1 snapshot only if quorum is lost (`docs/disaster-recovery.md`).

## Not in this change

- Scheduling workloads on the CPs. The default `NoSchedule` taint stays until
  the three members have soaked. Longhorn DaemonSets have no nodeSelector and
  would land on the CPs if the taint were removed.
- Omni etcd backups (`EtcdBackupS3Configs` + `features.backupConfiguration`).
- Retiring `hp-sff-control-plane` and the dell worker.
