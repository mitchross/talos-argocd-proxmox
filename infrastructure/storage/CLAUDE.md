# Storage Guidelines

## Storage Classes

| Class | Use Case |
|-------|----------|
| `longhorn` | Distributed block storage — **cluster default**, served by the **V1 data engine** (chart default). The active Threadripper worker has two 450 GiB XFS filesystems: `/var/lib/longhorn` on its Talos/system disk and `/var/mnt/longhorn-nvme1` on its second disk. **V2/SPDK was tried and retired 2026-06-12** — it failed under full-DR restore load (open Longhorn 1.12 bugs #13315/#13314); forensics in git history; short version in `docs/disaster-recovery.md`. Do not re-enable V2 without a fixed release + a passed DR drill. |
| `truenas-nfs` | Official TrueNAS CSI dynamic NFS (canary-gated, non-default) |
| `nfs-comfyui-10g` | NFS 10G for ComfyUI models |
| `nfs-llama-cpp-10g` | NFS 10G for LLM models |
| `smb-csi` | Windows shares |
| `local-path` | Node-local fast storage |

`truenas-nfs` provisions new datasets under `BigTank/k8s/nfs/v`. It does not
replace static `nfs.csi.k8s.io` PVs for pre-existing data. TrueNAS CSI (pinned
**v1.1.1**) creates NFS shares with `mapall` semantics; run the documented
ownership canary before adopting the class for a workload that runs as a
non-root UID.

**Do not add a network-attached block tier for databases.** This was built and
measured on 2026-07-13 (a `flashpool` of 3x enterprise SATA SSD on the NAS, exported
over NVMe-oF/TCP) and **abandoned**. The driver worked, but sync writes do not survive
the network hop: the same zvol did **2,510 fsync IOPS locally on the NAS and 437 over
the wire** — only 1.7x better than Longhorn's 259, nowhere near the ~11x the local
numbers implied. It is not the wire (RTT is 0.147ms); it is that every fsync becomes
ext4-journal -> NVMe-oF FLUSH -> nvmet -> ZFS ZIL commit, each a round trip. A real SAN
array hides this behind battery-backed NVRAM; a NAS running honest ZFS cannot.
Databases fsync on every commit, so they are the **worst** workload to put behind a
network. Put database flash **local to the node that runs them** instead.

## Longhorn PVC Template

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: app-data
  namespace: app-name
spec:
  accessModes:
  - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
  storageClassName: longhorn  # Cluster default (V1 data engine), can be omitted
```

## NFS Static PVs (CRITICAL: Use CSI, NOT legacy nfs:)

**Always use CSI driver** (`nfs.csi.k8s.io`), never legacy `nfs:` block. The legacy driver **silently ignores `mountOptions`** — `nconnect`, `noatime`, etc. won't apply and you'll get ~140 MB/s instead of multi-GB/s.

```yaml
# CORRECT - CSI driver (mountOptions work)
apiVersion: v1
kind: PersistentVolume
metadata:
  name: app-nfs-pv
spec:
  capacity:
    storage: 150Gi
  accessModes:
    - ReadWriteMany
  persistentVolumeReclaimPolicy: Retain
  storageClassName: ""
  mountOptions:
    - nfsvers=4.1
    - nolock
    - tcp
    - nconnect=16
  csi:
    driver: nfs.csi.k8s.io
    volumeHandle: app-nfs-pv
    volumeAttributes:
      server: "192.168.10.133"
      share: "/mnt/BigTank/k8s/app-name"

# WRONG - legacy nfs: (mountOptions silently ignored!)
# spec:
#   nfs:
#     server: 192.168.10.133
#     path: /mnt/BigTank/k8s/app-name
```

**Reference**: `infrastructure/storage/csi-driver-nfs/storage-class.yaml` (immich static PV)

## NFS 10G Performance Tuning (CRITICAL)

Linux kernel (5.4+) defaults NFS `read_ahead_kb` to **128 KB**, limiting sequential reads to ~140 MB/s regardless of link speed.

**Fix applied in Talos machine config** (`omni/cluster-template/cluster-template.yaml`):

| Setting | Purpose | Where |
|---------|---------|-------|
| `udev rule: ATTR{read_ahead_kb}="16384"` | Sets NFS readahead to 16MB on mount | `machine.udev.rules` (cluster patch) |
| `siderolabs/nfsrahead` extension | Kernel nfsrahead tool + udev rule | `systemExtensions` (all node types) |
| `sunrpc.tcp_slot_table_entries: "128"` | Max outstanding RPCs per connection | `machine.sysctls` (cluster patch) |
| `net.ipv4.tcp_congestion_control: bbr` | Better congestion algorithm for 10G | `machine.sysctls` (cluster patch) |
| NIC ring buffers = 8192 | Max ring buffer on Proxmox + TrueNAS | Applied on both hosts (persisted) |

**Required NFS mount options** (set per-PV via CSI `mountOptions`):
- `nconnect=16` — 16 TCP connections per mount
- `rsize=1048576` / `wsize=1048576` — 1MB per NFS READ/WRITE op
- `nfsvers=4.1` — NFSv4.1 with session slots
- `noatime` — skip access time updates

## Proxmox Storage Configuration

| Storage Pool | Physical Backing | Purpose | Type / Provisioning |
|--------------|------------------|---------|---------------------|
| `nvme0-vmstore` | `/dev/nvme0n1` (EDILOCA EN605 512GB NVMe) | Worker VM Disk 1 (`scsi0`) / Control Plane | LVM-Thin |
| `nvme1-vmstore` | `/dev/nvme1n1` (EDILOCA EN605 512GB NVMe) | Worker VM Disk 2 (`scsi1`) | LVM-Thin |
| `local-lvm` | `/dev/sda` (SanDisk SD7TB3Q 256GB SATA SSD) | Proxmox Boot & Host Storage | LVM-Thin |

**LVM-Thin** is utilized to provide thin provisioning, preventing virtual disks from reserving their full size up front.

**EDILOCA EN605 note**: These are consumer NVMe SSDs; this repository has no
verified evidence of enterprise power-loss protection or a particular DRAM
cache design. Do not blame a pod startup storm from the model name alone. The
2026-07-05 all-pod restart was verified as Kubernetes CPU-request pressure plus
Longhorn controller/volume reattach churn, not as an SSD-latency incident.

## Debugging Storage

```bash
kubectl get pvc -A
kubectl describe pvc app-data -n app-name
kubectl get pods -n longhorn-system
kubectl get volumes -n longhorn-system
```

### Debugging NFS Performance

```bash
# Check readahead (should be 16384, NOT 128)
kubectl exec -n <ns> <pod> -- cat /sys/class/bdi/0:*/read_ahead_kb

# Check sunrpc slot table (should be 128, NOT 2)
kubectl exec -n <ns> <pod> -- cat /proc/sys/sunrpc/tcp_slot_table_entries

# Check mount options (verify nconnect=16, rsize=1048576)
kubectl exec -n <ns> <pod> -- cat /proc/self/mountstats | grep -A3 "192.168.10.133"

# Full NFS stats (connection distribution, slot usage, RTT)
kubectl exec -n <ns> <pod> -- cat /proc/self/mountstats

# Server-side debugging
scripts/debug-nfs-server.sh   # Run on TrueNAS SSH
scripts/debug-nfs-client.sh   # Run on Proxmox SSH
```
