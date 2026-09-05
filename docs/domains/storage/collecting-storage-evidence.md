# Read-only storage evidence collection

Use this before blaming a disk, Longhorn, the NAS, or a Kubernetes request
setting. The collector creates a private JSON report and performs no benchmarks,
workload writes, migrations, node changes, SSH, sudo, trim, SMART tests, or
storage reconfiguration. It does not query Secrets, ConfigMaps, or pod logs.

## Cluster report

From a client with existing read permissions:

```sh
python scripts/collect-storage-evidence.py cluster \
  --context "$(kubectl config current-context)" \
  --output "cluster-storage-$(date -u +%Y%m%dT%H%M%SZ).json"
```

Check the selected context yourself. The report joins actual PVC -> PV ->
Longhorn volume -> replica -> node zone. It retains desired replica count,
Longhorn robustness, replica process state, unknown placement, node conditions,
and Longhorn disk availability/scheduling figures separately. It does not call a
volume healthy merely because its StorageClass requests two copies.

A detached volume or stopped replica process is not automatically a fault.
Use volume robustness and current attachment/workload context. Kubernetes zone
labels describe the configured topology, not verified independent power,
networking, or physical hardware.

## Host report

Run the same script locally on each Proxmox host, not inside its Talos guest:

```sh
python3 collect-storage-evidence.py host \
  --output "host-storage-$(date -u +%Y%m%dT%H%M%SZ).json"
```

The fixed commands are `lsblk`, `vgs`, `lvs`, and a short `iostat -x` observation.
Missing commands or insufficient read permissions are reported as unavailable;
the script never installs packages or elevates permissions. The host report
includes block-device models/mounts, thick/thin LVM inventory and allocation
headroom, plus observed device latency. It intentionally omits disk serials.

Match guest virtual disks to physical backing storage through the reviewed
Proxmox VM/storage configuration. Never infer a physical SSD model or IOPS limit
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
the existing Kopiur and application acceptance checks. SMART/endurance and
hardware/cabling/PCIe investigations remain separate; this tool does not invent
missing physical evidence.

## Handling the result

Exit 0 means all requested data sources returned, not that the system is healthy.
Exit 2 means a useful partial report was written; missing data must remain
unknown. Exit 1 means collection/output failed. Existing files are never
overwritten and new reports use mode 0600. Keep reports private: node names,
volume names, mount paths and topology are operational information. Do not
commit reports or attach them to a public issue without reviewing them.

Record the application symptom, UTC window, image/revision, current load and
concurrent maintenance beside the reports. Compare idle, normal application
load, and an already approved maintenance event. Do not start a production
replica failure or write benchmark merely to populate this report.

## Tests

```sh
python -m unittest discover -s scripts/tests -p test_storage_evidence.py -v
```

The tests use mocked subprocesses and synthetic Kubernetes objects. This change
adds tooling only; no DaemonSet or Application is deployed. Reverting the PR
removes the collector without changing any live infrastructure.
