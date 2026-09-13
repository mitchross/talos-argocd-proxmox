# Rebuild disk and partition study — September 12, 2026

**Status: measured recommendation; not implemented.** The owner confirmed that
the rebuild replaces the Talos cluster through Omni while the physical hosts,
NAS/RustFS, Pi-hosted Omni/DNS, and external recovery files remain. Recommendations
must have measured evidence. The [pre-nuke gates](../disaster-recovery.md#pre-nuke-checklist)
still apply, including the unresolved fresh Kubernetes-config migration.

## Recommendation

Keep the physical drives in their current hosts. Split the GPU VM's existing
NVMe0 allocation into a **16 GiB boot disk and a 434 GiB EPHEMERAL disk**. This
resolves the smallest-disk install-selection problem while retaining nearly all
current `/var` capacity. On the control plane, reserve **32 GiB for ETCD and
64 GiB for EPHEMERAL** within its existing 100 GiB VM disk. The etcd partition
provides capacity isolation; no latency improvement from repartitioning the
same SSD has been measured.

These are replacement-layout proposals. No live disk, machine class, Talos
configuration, or storage policy was changed during the study.

## Measurements and limits

Collected September 13 around 00:54–01:00 UTC, still September 12 in Detroit.
Prometheus results are histogram estimates from the live control-plane VM,
not synthetic maximum-throughput benchmarks. The last hour includes the
pre-rebuild backup campaign; the earlier comparison uses a 20-hour window
ending two hours before collection.

| Measurement | Result | Implication |
|---|---:|---|
| etcd WAL fsync p99, last hour | 14.96 ms | Above etcd's 10 ms diagnostic target |
| etcd WAL fsync p99, last 24 hours | 12.51 ms | Tail latency merits investigation |
| etcd WAL fsync p99, earlier 20-hour window | 11.58 ms | Recent backup load does not explain the whole result |
| etcd backend commit p99, last hour / 24 hours | 20.99 / 14.87 ms | Below the corresponding 25 ms target in these aggregate windows |
| Five-minute WAL p99 windows over 24 hours | median 9.53 ms; maximum 28.08 ms; 135 of 289 above 10 ms | Averages alone hide recurring tail latency |
| etcd leader changes, last 24 hours | 0 | This sample does not establish repeated quorum instability |
| etcd backend size / configured quota | 421 MiB / 8 GiB | Database capacity is not currently the limiting resource |
| Entire etcd directory | approximately 830 MB | Includes more than the backend database file |
| Control-plane `/var` used | 8.12 GiB | Ample space for reserving an ETCD partition |
| GPU `/var` used | 253.33 GiB | A small replacement `/var` would be an unproven capacity reduction |
| GPU CRI-reported image/container filesystem usage | 194.95 GiB | Runtime storage alone rules out assuming 64–128 GiB is enough |
| GPU model-cache / flash filesystem used | approximately 356.1 / 175.7 GiB | Keep the existing 450 / 300 GiB allocations |

The imageFs and containerFs figures are identical representations of the same
runtime storage; do not add them together. A full recursive Talos directory
walk timed out, so the GPU breakdown uses kubelet's runtime statistics and
filesystem counters. No seven-day capacity maximum was established. Headroom
calculations below use the measured current usage, not an asserted peak.

The latency targets come from the [etcd FAQ](https://etcd.io/docs/v3.6/faq/#what-does-the-etcd-warning-failed-to-send-out-heartbeat-on-time-mean).
The [September 5 physical inventory](2026-09-05-inventory.md) identified the
control-plane backing device as a dedicated PNY CS900 under thick LVM. That
historical sample had approximately 49 ms WAL p99; it is not today's baseline.

Private raw queries, timestamps, native Talos output, and offline validation
receipts are in `/Users/mitchross/backups/talos-rebuild-disk-study-20260912`.

## GPU: correct boot selection without moving physical drives

| Virtual disk | Proposed size | Physical pool | Purpose |
|---|---:|---|---|
| Primary boot disk | 16 GiB | `nvme0-vmstore` | EFI/META/STATE; uniquely smallest eligible disk |
| Separate EPHEMERAL disk | 434 GiB | `nvme0-vmstore` | `/var`, including runtime and current default Longhorn path |
| Existing model disk | 450 GiB | `nvme1-vmstore` | AI model cache |
| Existing flash disk | 300 GiB | `ssd-ent` | Longhorn flash tier |

The first two disks total the existing **450 GiB** NVMe0 allocation. Total guest
allocation remains **1,200 GiB**. At the measured 253.33 GiB usage, a 434 GiB
EPHEMERAL disk leaves about **180.7 GiB before filesystem overhead**. Compared
with the current 447.6 GiB filesystem, this gives up roughly 14 GiB of usable
`/var` capacity to make installation deterministic. This is a capacity and
provisioning recommendation; the storage path remains on the same hardware,
and no I/O speedup is claimed.

The Talos 1.14 [partition-size implementation](https://github.com/siderolabs/talos/blob/v1.14.0/pkg/machinery/imager/quirks/partitions.go)
and [version defaults](https://github.com/siderolabs/talos/blob/v1.14.0/pkg/machinery/imager/quirks/quirks.go)
allocate approximately 2.15 GiB for UKI boot assets, META, and STATE. A 16 GiB
system disk has room because the large EPHEMERAL filesystem is explicitly
placed elsewhere. Simply reducing `disk_size` without relocating EPHEMERAL
would be wrong.

The replacement must also change all three Talos data selectors. The current
model selector (`disk.size >= 400u * GB`) would match both the new 434 GiB disk
and the model disk. Use distinct measured virtual sizes, for example:

| Volume | Candidate selector |
|---|---|
| EPHEMERAL | `!system_disk && disk.size == 434u * GiB` |
| ai-model-cache | `!system_disk && disk.size == 450u * GiB` |
| longhorn-ssd-flash | `!system_disk && disk.size == 300u * GiB` |

Every disk-size change must update its selector. Do not depend on a newly
generated machine UUID, a manual race against installation, or an NVMe
transport predicate: Proxmox exposes these devices as virtual SCSI disks.

## Talos 1.14: dedicated ETCD, CRI, KUBELET, and LOG volumes

The [1.14 VolumeConfig reference](https://docs.siderolabs.com/talos/v1.14/reference/configuration/block/volumeconfig)
supports dedicated partitions for ETCD, CRI, KUBELET, and LOG. They remain
directories beneath EPHEMERAL by default, including on this upgraded cluster.
The directory-versus-partition choice is made when the node is first
provisioned; changing it on an established node is rejected.

For the replacement control plane, the proposed limits are:

```yaml
apiVersion: v1alpha1
kind: VolumeConfig
name: EPHEMERAL
provisioning:
  diskSelector:
    match: system_disk
  minSize: 64GiB
  maxSize: 64GiB
---
apiVersion: v1alpha1
kind: VolumeConfig
name: ETCD
provisioning:
  diskSelector:
    match: system_disk
  minSize: 32GiB
  maxSize: 32GiB
```

The two partitions total 96 GiB, leaving room for boot assets and metadata in
the existing 100 GiB disk. Explicitly bounding EPHEMERAL prevents it from
consuming the space intended for ETCD. The 32 GiB reservation is a conservative
planning allowance for the configured 8 GiB backend quota, temporary database
copies during maintenance, WAL and filesystem overhead. It is not a benchmark
result or a claim that today's 421 MiB database needs 32 GiB.

Keep CRI, KUBELET, and LOG directory-backed for this proposal. No measurement
established a useful split size or performance gain for them. Retain Talos's
default filesystem geometry and periodic trim settings; no benchmark supports
custom tuning. Dedicated ETCD/LOG use `noexec` with secure mounts, while CRI and
KUBELET must support execution. Read the [1.14 release notes](https://github.com/siderolabs/talos/releases/tag/v1.14.0)
before changing mount behavior.

With a dedicated ETCD partition, an EPHEMERAL-only reset does **not** erase
etcd. The full Omni VM destruction planned here is a different operation;
confirm all intended guest disks are removed while external recovery storage
survives.

## What the existing benchmarks justify

The July 14 Mink measurements recorded approximately 3,069 QD1 4 KiB fsync
IOPS at the Threadripper's enterprise mirror/thick-LVM host path, 888 through
the VM's direct filesystem, and about 200 through its tested Longhorn V1 path.
The tested EDILOCA/Longhorn path measured 259 IOPS. These are historical,
path-specific measurements; the raw host figure is not an application result
and the Longhorn result is not a universal ceiling.

They do not justify moving every database onto the flash tier for a promised
speedup, replacing the storage stack, or dismantling an existing mirror. The
current control-plane tail latency justifies testing a better backing device.
It does not establish how much a particular replacement will improve it.
The HPE drive in the NAS is a boot-mirror member, not an available spare.

Before recommending a physical replacement for performance, compare current
and candidate storage through the **same disposable VM/filesystem path**:

1. Use a new temporary test file, never a production block device or database.
   Match virtual controller, thick/thin provisioning, cache mode, filesystem,
   write size, queue depth, flush semantics and representative background load.
2. Run repeated single-job QD1 synchronous-write tests and record durable
   operation latency p50/p95/p99, IOPS, guest/host CPU and I/O pressure. Preserve
   the exact fio or pg_test_fsync command and full output. Do not disable fsync
   or compare a cached/raw-host result with the existing guest path.
3. Require a repeatable tail-latency improvement, then confirm live etcd WAL
   p99 below 10 ms and backend commit p99 below 25 ms under representative
   load. A synthetic result alone does not establish application improvement.

No new synthetic write benchmark or physical disk migration was performed.

## Validation and adoption boundary

The proposed CP partition documents and GPU volume documents passed
`talosctl v1.14.0 gen config --talos-version v1.14.0` followed by
`talosctl validate --mode metal` with synthetic secrets. Size arithmetic and
selector separation were checked. These checks validate configuration syntax;
they are not a successful Omni fresh-VM install, full-template validation, or
restoration test.

Implementation needs the GPU MachineClass change, matching volume selectors,
fresh Kubernetes-config migration, and a provision/restore check together.
Before deleting the cluster, the replacement must show the intended system
disk and volume mount paths, adequate free space, working CSI/GPU devices,
and a valid Kopiur populator drill. Keep the old cluster until the pre-nuke
gates are satisfied. Roll back a candidate layout by discarding only its test
VM and returning to the preserved configuration; never attempt an in-place
filesystem shrink as rollback.
