# Collect storage evidence (read-only)

This page shows how to run the storage evidence collector, a script that writes a JSON
report of where each volume lives and how each host's disks look. Run it before you blame
a disk, Longhorn, the NAS or a Kubernetes request setting for a problem.

The collector only reads. It runs no benchmarks, workload writes, migrations, node
changes, SSH, sudo, trim, SMART tests or storage reconfiguration. It does not query
Secrets, ConfigMaps or pod logs.

## Cluster report

Run this from a machine whose kubectl context already has read permissions:

```sh
python scripts/collect-storage-evidence.py cluster \
  --context "$(kubectl config current-context)" \
  --output "cluster-storage-$(date -u +%Y%m%dT%H%M%SZ).json"
```

Check that the selected context is the cluster you mean.

The report joins each PVC to its PV, its Longhorn volume, its replicas and the zone of
each replica's node. It keeps these values separate: the desired replica count, Longhorn
robustness, replica process state, unknown placement, node conditions, and the Longhorn
disk availability and scheduling figures. It does not call a volume healthy only because
its StorageClass requests two copies.

A detached volume or a stopped replica process is not automatically a fault. Judge it by
the volume's robustness and by whether a workload has the volume attached. Kubernetes zone
labels describe the configured topology. They do not prove separate power, networking or
physical hardware.

## Host report

Copy the same script to each Proxmox host and run it there, not inside the Talos guest:

```sh
python3 collect-storage-evidence.py host \
  --output "host-storage-$(date -u +%Y%m%dT%H%M%SZ).json"
```

The script runs a fixed set of commands: `lsblk`, `vgs`, `lvs`, and a short `iostat -x`
observation. If a command is missing or the script lacks read permission, the report marks
that source as unavailable. The script never installs packages and never raises its
permissions.

The host report includes block-device models and mounts, the thick and thin LVM inventory,
allocation headroom and observed device latency. It leaves out disk serials on purpose.

To match a guest virtual disk to its physical drive, use the Proxmox VM and storage
configuration, or the [disk map](disk-map.md). Never infer a physical SSD model or an IOPS
limit from the name of a Kubernetes StorageClass.

## Read the layers separately

| Signal | What it means | What it does not mean |
|---|---|---|
| Thick VG free extents | Capacity still available for allocating/extending LVs | Guest filesystem free space; a nearly allocated VG is not automatically a full guest disk |
| Thin pool data/metadata percentage | Physical thin-pool utilization | The sum of PVC requests or guest filesystem occupancy |
| Longhorn scheduled bytes | Requested replica placement budget | Actual written bytes or physical host capacity |
| Longhorn available bytes | Filesystem headroom reported by its node | SSD wear, power-loss protection, or independent replicas |
| `iostat` latency sample | Observed behavior during the short interval | A benchmark, durable-write p99, or a diagnosis of the application |
| Replica zone labels | The declared node failure domains | Proof of different hypervisors, outlets, controllers, or switches |

No report shows that backups are fresh or that an app can recover. Use the kopiur checks
and the app's own acceptance checks for those. SMART, drive endurance, hardware, cabling
and PCIe investigations are separate work. The script does not fill in physical evidence
that it cannot read.

## Read the exit code and protect the report

| Exit code | Meaning |
|---|---|
| 0 | Every requested data source returned. It does not mean the system is healthy. |
| 2 | The script wrote a useful partial report. Treat missing data as unknown. |
| 1 | Collection or output failed. |

The script never overwrites an existing file, and it writes each report with mode 0600.
Keep reports private, because node names, volume names, mount paths and topology are
operational information. Do not commit a report. Do not attach one to a public issue
before you review it.

Record these facts beside the reports: the app symptom, the UTC time window, the image or
revision, the current load, and any maintenance running at the same time. Compare an idle
period, normal app load and a maintenance event that was already approved. Do not start a
production replica failure or a write benchmark only to fill this report.

## Tests

```sh
python -m unittest discover -s scripts/tests -p test_storage_evidence.py -v
```

The tests use mocked subprocesses and synthetic Kubernetes objects. The collector is a
script only. It deploys no DaemonSet and no Application, so it changes no live
infrastructure.
