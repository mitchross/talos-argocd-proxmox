# Ongoing research

**Start with one decision below.** Each link opens the relevant section of the
[20 September assessment](../audits/2026-09-20-homelab-report.html), including
evidence, trial boundaries, and rollback considerations.

## Evaluated options — 20 September 2026

These are proposals from the assessment, not deployed migrations.

| Decision | Verified starting point | Proposed next step |
| --- | --- | --- |
| [NetBird](../audits/2026-09-20-homelab-report.html#netbird) | Cloudflare and Tailscale serve different access needs today. | Choose private access or public ingress, then test one noncritical resource. |
| [ProxCenter, PDM, or a PVE cluster](../audits/2026-09-20-homelab-report.html#proxmox) | ProxCenter and PDM are already installed; the five PVE hosts are standalone. | Compare the existing dashboards; consider clustering only for a specific unmet need. |
| [TrueNAS Proxmox plugin](../audits/2026-09-20-homelab-report.html#plugin) | The inspected host has the transport tools but no plugin installation. | Try a disposable VM on one wired host with a dedicated dataset and target. |

NAS replacement planning starts with the [measured performance reference](../nas-performance.md)
and the report's [RAM options](../audits/2026-09-20-homelab-report.html#ram-choice).
Candidate RAM sizes are not validated replacement specifications.

## Earlier proposals — revalidate before use

These documents retain their original URLs and context. Listing them here does
not make them active work; their assumptions were not revalidated by the
September 20 assessment.

- [Tiered storage](../domains/storage/architecture-future.md): idea only, not implemented.
- [Enterprise multi-cluster roadmap](../domains/multicluster/enterprise-gitops-roadmap.md)
  and [PRD](../domains/multicluster/prd.md): future design documents, not the current topology.
- [Flash Next study — 6 September 2026](../domains/ai-gpu/flash-next-dual-3090.md):
  researched candidate, not deployed or benchmarked on the restored dual-card
  system. The [model catalog](../domains/ai-gpu/model-catalog.md) owns the current
  serving configuration.

Use [audits](../audits/index.md) for dated findings and [inventory](../inventory/index.md)
for the observed hardware behind these choices.
