# Diagnostics Hardware Report

The September 10 post-reboot inspection covers drives, hosts, Talos nodes,
applications and recovery. **Keep the Dell for now:** normal compute demand fits,
but its spare wired failure domain matters when another machine fails. The
**Repair plan** tab shows the capacity budget, selective data-copy proposal and
RAM reuse options. These hardware and placement changes are not implemented.

The SFF control-plane SSD now meets the sampled etcd latency targets; replacement
is no longer the immediate recommendation. SurfSense Redis and Flatnotes were
repaired, while SurfSense PostgreSQL has confirmed filesystem corruption.
Longhorn attachment metadata, PostHog capacity and backup/restore work also
remain. Resolve data integrity before migrations or broad copy changes.
Flatnotes had no Markdown notes to recover. Detailed September 8/9 tables retain their dates beneath the newer inspection summaries.

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

All 14 physical collectors were reachable on September 10 at 22:29 UTC, and
all 24 drives reported passing SMART status. The installation source is the reviewed
[host monitoring configuration](https://github.com/mitchross/talos-argocd-proxmox/tree/main/host-monitoring).
That configuration includes installation, verification and rollback. If a
collector becomes unavailable, Grafana shows missing readings; it does not
substitute the inspection's old numbers. A drive reporting a passing self-check still
needs its errors, temperature and performance considered.

The September 10 mounted-filesystem sweep at 23:27–23:29 UTC found **66 of 67
ext4 filesystems with zero recorded errors**. SurfSense PostgreSQL had the only
known nonzero counter: 34 errors, unchanged since 22:19. This was a read-only
counter/log check, not offline fsck or a full media scan; detached Open WebUI
and Intercept volumes were excluded.

The initial proposal protects 32 selected app volumes with two copies, adding
about **25.82 GiB of current data** and **414 GiB of scheduled claims**. Existing
storage has room for that tier with explicit growth and staging allowances;
it does not require buying drives first. A compatible **1 TB Elite NVMe** remains
a preventive purchase: 74% endurance used is not a failure probability.

[PR #2350](https://github.com/mitchross/talos-argocd-proxmox/pull/2350) is open
and unmerged in this inspection: PostHog's proposed 8→32 GiB claim and Perplexica
permissions are not yet verified repairs. Ingestion, retention, fresh backups
and isolated restores still need acceptance checks after deployment.

The Open WebUI and Intercept backups passed isolated database restore checks
on September 10 at 23:11–23:15 UTC; production remains unrepaired. Those recovery
points leave possible gaps of nearly 19 hours and about 2 minutes before the
attachment fault, respectively. Application behavior and production cutover
still need verification.

Before another host reboot, wait for successful guest shutdown tasks and verify
the guests are stopped; proceed one physical host at a time with health checks.
The report records overlapping shutdowns. Reviewed
[ProxCenter inventory reboot code](https://github.com/adminsyspro/proxcenter-ui/blob/a1555e8f06c3c48be8c0174b5950901894b7528b/frontend/src/app/%28dashboard%29/infrastructure/inventory/components/InventoryDialogs.tsx#L1380)
uses a fixed five-second wait, but the installed UI/version and action used remain
unverified. This does not establish that the workflow caused the corruption.

A disk move or replacement needs a separate reviewed migration with verified
backups and surviving replicas. See the [storage architecture](storage-architecture.md)
and [disaster recovery runbook](disaster-recovery.md) for the recovery requirements.
