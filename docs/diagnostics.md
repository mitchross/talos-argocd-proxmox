# Diagnostics Hardware Report

The September 9 reinspection covers physical drives, hosts, Talos nodes,
resource use, replicas, applications and recovery. Click any drive for the
reason behind its recommendation, urgency, impact and replacement constraints.
Each section dates its current observations and retains repair history separately.

[Open full screen](assets/inspection/index.html){ .md-button .md-button--primary }
[Open in Grafana](https://grafana.vanillax.me/d/homelab-diagnostics){ .md-button }
[Download inventory](assets/inspection/inventory.json){ .md-button }

<iframe src="../assets/inspection/index.html" title="Diagnostics Hardware Report" style="width:100%;height:85vh;min-height:650px;border:1px solid #ddd6cb;border-radius:6px;"></iframe>

This report is a recorded inspection, not live polling. Physical SMART values,
passive I/O, workload health and recovery evidence have their own timestamps.
The Grafana dashboard adds live guest metrics; physical SMART/PVE/ZFS trends
remain a monitoring gap. A passing SMART summary does not certify durability.

A disk move or replacement needs a separate reviewed migration with verified
backups and surviving replicas. See the [storage architecture](storage-architecture.md)
and [disaster recovery runbook](disaster-recovery.md) for the recovery requirements.
