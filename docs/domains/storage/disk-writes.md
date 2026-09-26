# Disk writes

**Purpose:** keep the cluster from wearing out its consumer SSDs.
**Status:** current rules and how to check them.

Most Longhorn disks here are consumer SATA/NVMe drives with a limited write
budget (see [disk placement](../../storage-architecture.md#disk-placement-follows-drive-endurance)).
Writes pile up in a few predictable places: logs and telemetry that a database
writes about itself, backup clones, and apps that churn a cache or history on
persistent storage. Each rule below closes one of those.

## Rules

| Source | Rule | Where it lives |
|---|---|---|
| Talos audit log | Drop `auditd` records in the node-log pipeline. Talos SELinux is permissive and Longhorn volumes are `unlabeled_t`, so every pod write produces an audit line; shipping them costs a disk-backed queue write plus a Loki write each. | `filter/auditd` in `infrastructure/controllers/opentelemetry-operator/collector-agent.yaml` |
| Kubernetes API audit | Audit policy level `None`; nothing reads the audit log. | `control-plane-audit-policy` in `omni/cluster-template/cluster-template-prod-v2.yaml` |
| Database self-telemetry | Turn off ClickHouse's internal `system.*_log` tables (trace, text, metric, part, …). | `my-apps/ai/langfuse/clickhouse-system-logs.xml` |
| Backup clones | Every kopiur run clones the whole volume first. Back up **daily**; use every 6 hours only for data that can't be re-created; never hourly. Clones land only on the enterprise flash disk (`clone-ok`). | [schedules](../../storage-architecture.md#backup-schedules-retention-repository) |
| Deleted blocks | Longhorn `fstrim-daily` trims every volume in the `default` group, so clones and replicas stop copying freed blocks. | `infrastructure/storage/longhorn/recurringjob-fstrim.yaml` |
| Scratch caches | Put throwaway caches on a memory `emptyDir` (`medium: Memory`, with a size limit), not a PVC or node disk. Example: Frigate `/tmp/cache`. | `my-apps/home/frigate/deployment.yaml` |
| App history databases | Exclude high-churn derived sensors from history. Example: Home Assistant's recorder skips computed power/cost sensors (Prometheus still has them). | `my-apps/home/home-assistant/configuration.yaml` |
| Pod moves | Longhorn `dataLocality` is `disabled` on the default class: best-effort locality copies the whole volume whenever its pod lands on another node, so every reboot or drain became a copy storm. | `infrastructure/storage/longhorn/storageclass-default.yaml` |
| Duplicate telemetry | One observability stack: Prometheus, Loki, Tempo, Grafana. Don't add tools that keep their own copy of metrics/logs (e.g. an eBPF APM with its own ClickHouse) or in-cluster scanners that spawn a pod per image. | `monitoring/` |
| Bulk files | Bulk, read-mostly data (photo libraries, downloads) lives on the NAS (`truenas-nfs`), and its kopiur policy uses `copyMethod: Direct`, so no Longhorn clone is made. | [disk map](disk-map.md#where-should-new-data-go) |
| Right-sized volumes | Request what the app uses plus headroom. Longhorn books the full request, so oversized volumes fill the clone disk on paper and block backups. | [disk map](disk-map.md#where-should-new-data-go) |
| GPU-node trim | The weekly `talos-fstrim` job trims each GPU-node data mount by path; a missing path stops the job before the rest are trimmed. | `infrastructure/storage/talos-fstrim/scripts/trim-node-filesystems.sh` |
| Rebalancing | The descheduler never evicts pods with PVCs; moving one would copy its Longhorn replica. | [descheduler](../scheduling/descheduler.md) |

When adding an app, ask the same questions: does it log about itself to disk,
does it need its cache on persistent storage, and how often does it really need
a backup?

## Measure

The **Storage & SSD wear** Grafana dashboard (Cluster folder) shows all of this at a
glance: TB written per day, writes per drive, SSD wear, top writing and reading
pods, Longhorn space booked per node, and hours since each backup succeeded. The
raw queries are below for Grafana Explore.

Run in Grafana Explore (Prometheus data source).

```promql
# Top writers by pod (bytes/s over the last hour)
topk(10, sum by (namespace, pod) (rate(container_fs_writes_bytes_total{container!=""}[1h])))

# Bytes written per physical disk in the last day. Exclude dm-*/md* (LVM and RAID
# layers sit on top of sd*/nvme* and would count the same bytes two or three times).
sum by (physical_host, disk) (increase(node_disk_written_bytes_total{job="physical-node",disk!~"dm-.*|md.*"}[1d]))

# Whole fleet, TB per day (NAS excluded)
sum(increase(node_disk_written_bytes_total{job="physical-node",disk!~"dm-.*|md.*",physical_host!="truenas"}[1d])) / 1e12

# SSD wear (NVMe percent used; SATA drives report wear via smartctl_device_attribute)
smartctl_device_percentage_used
```

Expected: the fleet total stays around 1.5 TB/day or less, no single pod dominates the first query for long, and the per-disk
daily total stays roughly flat week to week. A sudden jump usually points at
one new pod — find it with the first query, then apply the matching rule.
