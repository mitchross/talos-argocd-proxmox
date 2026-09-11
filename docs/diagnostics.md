# Diagnostics Hardware Report

The September 10 post-reboot inspection covers drives, hosts, Talos nodes,
applications and recovery. **Keep the Dell for now:** normal compute demand fits,
but its spare wired failure domain matters when another machine fails. The
**Repair plan** tab shows the capacity budget, selective data-copy proposal and
RAM reuse options. These hardware and placement changes are not implemented.

The SFF control-plane SSD now meets the sampled etcd latency targets; replacement
is no longer the immediate recommendation. SurfSense Redis and Flatnotes were
repaired, while SurfSense PostgreSQL has confirmed filesystem corruption.
The selected plan now starts SurfSense completely fresh through GitOps,
superseding filesystem repair or restoration of its old app state. Open WebUI
and Intercept use native backup restoration; PostHog capacity and Perplexica
backup permissions are separate native fixes.
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
a preventive purchase: 74% endurance used is not a failure probability. The
capacity estimate predates the recovery PRs; replacement claims and retained
originals must be included in the final placement budget.

The open repair PRs use native GitOps resources and existing controllers:

- [PR #2350](https://github.com/mitchross/talos-argocd-proxmox/pull/2350): PostHog's 8→32 GiB claim and Perplexica backup permissions, with native scheduled backups.
- [PR #2352](https://github.com/mitchross/talos-argocd-proxmox/pull/2352): Argo/Kopiur restore Open WebUI and Intercept onto new two-copy storage while retaining their old failed data.
- [PR #2353](https://github.com/mitchross/talos-argocd-proxmox/pull/2353): discard all SurfSense app state, provision fresh PVCs and retain native future backups. The earlier filesystem-repair plan is superseded.

These changes are not yet deployed. The historical Open WebUI and Intercept
isolated database restore checks passed at 23:11–23:15 UTC on September 10;
production remains unrepaired. Their checked recovery points leave possible
gaps of nearly 19 hours and about 2 minutes before the attachment fault.
Native restores use the latest available backup.

ProxCenter **1.4.9 arm64 is verified on the Pi**. Read-only inspection of the
running frontend itself confirmed three node-power paths that discard guest
shutdown errors and wait a fixed five seconds before host power action. The
report records overlapping shutdowns; the behavior also appears in the
[ProxCenter inventory reboot code](https://github.com/adminsyspro/proxcenter-ui/blob/a1555e8f06c3c48be8c0174b5950901894b7528b/frontend/src/app/%28dashboard%29/infrastructure/inventory/components/InventoryDialogs.tsx#L1380).
The controller needs confirmed guest completion and per-host health gates. The exact user action and any causal connection to
corruption remain unproven.

Hardware purchases and placement changes remain separate proposals, dependent
on recoverable data and adequate surviving capacity. See the [storage architecture](storage-architecture.md)
and [disaster recovery runbook](disaster-recovery.md) for the recovery requirements.
