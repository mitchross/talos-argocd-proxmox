# Threadripper GPU Cluster

`talos-singlenode-gpu-prod` runs three VMs on the Threadripper Proxmox host:

- `threadripper-control-plane`: 4 vCPU, 16 GiB RAM, 100 GiB disk.
- `threadripper-worker`: 8 vCPU, 32 GiB RAM, 64 GiB `local-lvm` boot disk.
- `threadripper-gpu-worker`: 32 vCPU, 64 GiB RAM, two 450 GiB disks, one
  300 GiB flash disk, and two RTX 3090s.

The split keeps Kubernetes control-plane services away from GPU and app
workloads. It improves stability and scheduler headroom, but it is still not HA
because there is only one etcd member.

## Rebuild Guidance

Treat the all-in-one to split-node change as a controlled rebuild window, not a
clean live migration. The current all-in-one cluster has one etcd member, so
moving the control plane to a different VM will interrupt the API server.

Do not wipe app data as the first option. Verify backups, apply the machine
classes, sync the template, reprovision the Talos VMs, and let Argo restore the
apps.

## Notes

- Provision and ready the 32 GiB general worker before resizing the GPU VM.
  The GPU node used about 68 GiB while Dell was offline; non-GPU workloads
  must move before the GPU node is reduced to 64 GiB.
- Cold-resize the existing GPU VM in Proxmox; do not replace its Omni machine
  request. Reprovisioning would destroy the provider-owned Longhorn disks.
- The general worker boot disk belongs on `local-lvm`. Do not place it on
  `nvme0-vmstore` or `nvme1-vmstore`; those pools back the existing Longhorn
  disks and were already 73% and 38% allocated at this decision point.
- The Dell's added Samsung SSD is separate capacity. It does not reduce the
  space required by any Threadripper VM disk.
- Keep `siderolabs/nfs-utils` off GPU worker nodes. Use the CSI NFS path.
- The second Longhorn disk is attached at VM creation time by the provider.
- Longhorn uses one replica per volume in this single-worker cluster. It places
  volumes across both disks; it does not mirror data between them. Disk-loss
  recovery therefore depends on the off-host kopiur/Kopia backups.
- The Cilium L2 policy must allow the current single control-plane node to
  announce VIPs until the rebuild is complete.

Durable incident details live in Mink notes:

- `projects/talos-argocd-proxmox/omni-split-gpu-cluster-into-control-plane-and-gpu-worker.md`
- `resources/talos-gpu-passthrough-host-lock-root-cause-guest-memory-pressure-vfio-pins-all-g.md`
- `resources/talos-uservolume-diskselector-transportscsi-breaks-proxmox-virtio-scsi-disk-long.md`
