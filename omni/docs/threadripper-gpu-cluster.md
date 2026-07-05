# Threadripper GPU Cluster

`talos-singlenode-gpu-prod` is intended to run on the Threadripper Proxmox host
as two VMs:

- `single-node-control-plane`: 4 vCPU, 16 GiB RAM, 100 GiB disk.
- `single-node-talos-gpu`: 32 vCPU, 96 GiB RAM, two 450 GiB disks, two RTX 3090s.

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

- The GPU worker is set to 96 GiB and the control plane to 16 GiB. VFIO pins
  guest RAM during GPU passthrough, so retain enough Proxmox host headroom.
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
