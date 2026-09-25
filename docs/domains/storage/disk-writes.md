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
| Rebalancing | The descheduler never evicts pods with PVCs; moving one would copy its Longhorn replica. | [descheduler](../scheduling/vpa-and-topology.md#descheduler-rebalancing-stateless-pods) |

When adding an app, ask the same questions: does it log about itself to disk,
does it need its cache on persistent storage, and how often does it really need
a backup?

## Measure

Run in Grafana Explore (Prometheus data source).

```promql
# Top writers by pod (bytes/s over the last hour)
topk(10, sum by (namespace, pod) (rate(container_fs_writes_bytes_total{container!=""}[1h])))

# Bytes written per physical disk in the last day
sum by (physical_host, disk) (increase(node_disk_written_bytes_total{job="physical-node"}[1d]))

# SSD wear (NVMe percent used; SATA drives report wear via smartctl_device_attribute)
smartctl_device_percentage_used
```

Expected: no single pod dominates the first query for long, and the per-disk
daily total stays roughly flat week to week. A sudden jump usually points at
one new pod — find it with the first query, then apply the matching rule.
