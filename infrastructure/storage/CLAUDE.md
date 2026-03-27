# Storage Guidelines

> **Required reading before modifying VPA or resource optimization:**
> - `docs/vpa-resource-optimization.md` — VPA architecture, auto-scaling modes, Kyverno auto-generation policy

## Storage Classes

| Class | Use Case |
|-------|----------|
| `longhorn` | Distributed block storage (default) |
| `nfs-comfyui-10g` | NFS 10G for ComfyUI models |
| `nfs-llama-cpp-10g` | NFS 10G for LLM models |
| `smb-csi` | Windows shares |
| `local-path` | Node-local fast storage |

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
  storageClassName: longhorn  # Default, can be omitted
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

## Proxmox ZFS Storage Pools

| Pool | Backing | Purpose | Thin Provisioning |
|------|---------|---------|-------------------|
| `ssdpool` | 4x PNY CS900 1TB SATA SSD (stripe) | Worker + GPU node disks | `sparse 1` (enabled) |
| `fastpool` | 3x 480GB MK000480GWCEV SSD (stripe) | Control plane disks | `sparse 1` (enabled) |

**Thin provisioning (`sparse 1`)** is enabled on both pools in `/etc/pve/storage.cfg`. Without it, ZFS zvols reserve their full size via `refreservation`, wasting ~2.5 TB on ssdpool alone (600 GB reserved per worker VM even when only 30 GB is used).

To verify or change: `pvesm set ssdpool --sparse 1` / `pvesm set fastpool --sparse 1`

**PNY CS900 note**: These are DRAM-less SATA SSDs. ZFS performance degrades past ~80% pool capacity due to copy-on-write fragmentation. With thin provisioning enabled this is not a concern at current data volumes (~400 GB actual on 4 TB pool).

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
