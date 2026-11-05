# Read-only storage evidence collection

Use this before blaming a disk, Longhorn, the NAS, or a Kubernetes request
setting. The collector creates a private JSON report. It runs no benchmarks, workload
writes, migrations, node changes, SSH, sudo, trim, SMART tests, or storage
reconfiguration. It does not query Secrets, ConfigMaps, or pod logs.

## Cluster report

From a client with existing read permissions:

```sh
python scripts/collect-storage-evidence.py cluster \
  --context "$(kubectl config current-context)" \
  --output "cluster-storage-$(date -u +%Y%m%dT%H%M%SZ).json"
```

Check the selected context yourself. The report joins the actual PVC, PV,
Longhorn volume, replica and node zone. It keeps desired replica count,
Longhorn robustness, replica process state, unknown placement, node conditions,
and Longhorn disk availability and scheduling figures separate. It does not call
a volume healthy merely because its StorageClass requests two copies.

A detached volume or stopped replica process is not automatically a fault.
Use volume robustness and current attachment/workload context. Kubernetes zone
labels describe the configured topology. They do not verify independent power,
networking, or physical hardware.

## Host report

Run the same script locally on each Proxmox host, not inside its Talos guest:

```sh
python3 collect-storage-evidence.py host \
  --output "host-storage-$(date -u +%Y%m%dT%H%M%SZ).json"
```

The fixed commands are `lsblk`, `vgs`, `lvs`, and a short `iostat -x` observation.
The script reports missing commands or insufficient read permissions as
unavailable. It never installs packages or elevates permissions. The host report
includes block-device models and mounts, thick and thin LVM inventory, allocation
headroom, and observed device latency. It omits disk serials on purpose.

Match guest virtual disks to physical backing storage through the reviewed
Proxmox VM and storage configuration. Never infer a physical SSD model or IOPS limit
from the name of a Kubernetes StorageClass.

## Read the layers separately

| Signal | What it means | What it does not mean |
|---|---|---|
| Thick VG free extents | Capacity still available for allocating/extending LVs | Guest filesystem free space; a nearly allocated VG is not automatically a full guest disk |
| Thin pool data/metadata percentage | Physical thin-pool utilization | The sum of PVC requests or guest filesystem occupancy |
| Longhorn scheduled bytes | Requested replica placement budget | Actual written bytes or physical host capacity |
| Longhorn available bytes | Filesystem headroom reported by its node | SSD wear, power-loss protection, or independent replicas |
| `iostat` latency sample | Observed behavior during the short interval | A benchmark, durable-write p99, or a diagnosis of the application |
| Replica zone labels | The declared node failure domains | Proof of different hypervisors, outlets, controllers, or switches |

No report establishes backup freshness or application recovery. Those still need
the existing Kopiur and application acceptance checks. SMART, endurance,
hardware, cabling and PCIe investigations remain separate. This tool does not
invent missing physical evidence.

## Handling the result

Exit 0 means all requested data sources returned, not that the system is healthy.
Exit 2 means the script wrote a useful partial report. Treat missing data as
unknown. Exit 1 means collection or output failed. The script never overwrites
existing files, and new reports use mode 0600. Keep reports private, because node
names, volume names, mount paths and topology are operational information. Do
not commit reports or attach them to a public issue without reviewing them.

Record the application symptom, UTC window, image/revision, current load and
concurrent maintenance beside the reports. Compare idle, normal application
load, and an already approved maintenance event. Do not start a production
replica failure or write benchmark just to populate this report.

## Tests

```sh
python -m unittest discover -s scripts/tests -p test_storage_evidence.py -v
```

The tests use mocked subprocesses and synthetic Kubernetes objects. This change
adds tooling only. It deploys no DaemonSet or Application. Reverting the PR
removes the collector without changing any live infrastructure.
