# Diagnostics Hardware Report

The September 9 reinspection covers physical drives, hosts, Talos nodes,
resource use, replicas, applications and recovery. Click any drive for the
reason behind its recommendation, urgency, impact and replacement constraints.
Each section dates its current observations and retains repair history separately.

[Open full screen](assets/inspection/index.html){ .md-button .md-button--primary }
[Open in Grafana](https://grafana.vanillax.me/d/homelab-diagnostics){ .md-button }
[Download inventory](assets/inspection/inventory.json){ .md-button }

<iframe src="../assets/inspection/index.html" title="Diagnostics Hardware Report" style="width:100%;height:85vh;min-height:650px;border:1px solid #ddd6cb;border-radius:6px;"></iframe>

The page above is a recorded inspection: its measurements retain their dates.
[Grafana](https://grafana.vanillax.me/d/homelab-diagnostics) is the live view.
Its physical drive inventory, temperature, wear, disk activity, host CPU and
memory come from standard collectors on each machine. Kubernetes health,
Longhorn copies, application disk space and backup results come from the
cluster's existing collectors.

The host collectors must be installed from the reviewed
[host monitoring configuration](https://github.com/mitchross/talos-argocd-proxmox/tree/main/host-monitoring).
That configuration includes installation, verification and rollback. Merging
the dashboard alone does not install software on Proxmox or TrueNAS. Until a
collector is running, Grafana shows missing readings; it does not substitute
the inspection's old numbers. A drive reporting a passing self-check still
needs its errors, temperature and performance considered.

A disk move or replacement needs a separate reviewed migration with verified
backups and surviving replicas. See the [storage architecture](storage-architecture.md)
and [disaster recovery runbook](disaster-recovery.md) for the recovery requirements.
