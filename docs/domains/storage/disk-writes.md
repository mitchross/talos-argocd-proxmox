# Disk writes

This page lists the rules that keep the cluster from wearing out its consumer SSDs, and
shows how to measure the writes. Read it when you add an app or when a drive's write rate
jumps.

Most Longhorn disks here are consumer SATA or NVMe drives. Each drive can take a limited
amount of writes before it wears out (see
[disk placement](../../storage-architecture.md#disk-placement-follows-drive-endurance)).
Writes come from a few known places: logs and telemetry that a database writes about
itself, backup clones, and apps that rewrite a cache or a history on persistent storage.
Each rule below removes one of those sources.

## Rules

| Source | Rule | Where it lives |
|---|---|---|
| Talos audit log | Drop `auditd` records in the node-log pipeline. Talos SELinux is permissive and an unlabeled Longhorn volume is `unlabeled_t`, so every pod write to it produces an audit line. Each shipped line costs a disk-backed queue write and a Loki write. | `filter/auditd` in `infrastructure/controllers/opentelemetry-operator/collector-agent.yaml` |
| Kubernetes API audit | Keep the audit policy level at `None`. Nothing reads the audit log. | `control-plane-audit-policy` in `omni/cluster-template/cluster-template-prod-v2.yaml` |
| Database self-telemetry | Turn off ClickHouse's internal `system.*_log` tables (trace, text, metric, part and the others). | `my-apps/ai/langfuse/clickhouse-system-logs.xml` |
| Backup clones | Every kopiur run clones the whole volume first. Back up **daily**. Back up every 6 hours only data that can't be re-created. Never back up hourly. Clones land only on `clone-ok` disks: the GPU enterprise flash and the consumer `hp-sff-ssd2`, which takes its share of daily clone writes. | [schedules](../../storage-architecture.md#backup-schedules-and-retention) |
| Deleted blocks | The Longhorn `fstrim-daily` job trims every volume in the `default` group, so clones and replicas stop copying freed blocks. | `infrastructure/storage/longhorn/recurringjob-fstrim.yaml` |
| Scratch caches | Put throwaway caches on a memory `emptyDir` (`medium: Memory`, with a size limit), not on a PVC or a node disk. Example: Frigate `/tmp/cache`. | `my-apps/home-automation/frigate/deployment.yaml` |
| App history databases | Exclude derived sensors that change often from history. Example: the Home Assistant recorder skips computed power and cost sensors. Prometheus still has them. | `my-apps/home-automation/home-assistant/configuration.yaml` |
| Pod moves | Keep Longhorn `dataLocality` at `disabled` on the default class. With `best-effort`, Longhorn copies the whole volume each time its pod lands on another node, so every reboot or drain causes a full volume copy. | `infrastructure/storage/longhorn/storageclass-default.yaml` |
| Duplicate telemetry | Run one observability stack: Prometheus, Loki, Tempo and Grafana. Do not add a tool that keeps its own copy of metrics or logs, such as an eBPF APM with its own ClickHouse. Do not add an in-cluster scanner that starts a pod per image. Do not bring back Coroot, Trivy Operator or Keep. | `monitoring/` |
| Bulk files | Put bulk, read-mostly data (photo libraries, downloads) on the NAS (`truenas-nfs`). Its kopiur policy uses `copyMethod: Direct`, so no Longhorn clone is made. | [disk map](disk-map.md#where-should-new-data-go) |
| Right-sized volumes | Request what the app uses plus headroom. Longhorn reserves the full request, so oversized volumes use up the clone disk's reservations and block backups. | [disk map](disk-map.md#where-should-new-data-go) |
| Node volume trim | Talos trims every `EPHEMERAL`, `STATE`, `ETCD` and user volume once a week by itself, so freed blocks reach the SSD and the Proxmox thin pools. Talos includes a new user volume automatically. Check with `talosctl -n <node> get volumetrimschedules`. | Talos 1.14 default `FilesystemTrimConfig` (168h) |
| Rebalancing | The descheduler never evicts a pod that has a PVC, because the move would copy its Longhorn replica. | [descheduler](../scheduling/descheduler.md) |

When you add an app, ask three questions. Does the app log about itself to disk? Does its
cache need persistent storage? How often does it need a backup?

## Measure

The Storage & SSD wear Grafana dashboard (Cluster folder) shows TB written per day, writes
per drive, SSD wear, the pods that write and read the most, Longhorn space reserved per
node, and hours since each backup succeeded.

To run the raw queries, open Grafana Explore and select the Prometheus data source.

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

Expect these results:

- The fleet total stays at about 1.5 TB/day or less.
- No single pod stays at the top of the first query for long.
- The daily total for each disk stays roughly flat from week to week.

A sudden jump usually comes from one new pod. Find the pod with the first query, then
apply the matching rule.
