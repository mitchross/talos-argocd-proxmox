# talos-argocd-proxmox

A GitOps Kubernetes homelab on **Talos Linux** with **self-managing ArgoCD**.
ApplicationSets discover app directories. Per-PVC Kopiur resources declare
backup and restore behavior. After the operator rebuilds Talos and seeds Argo,
protected volumes restore automatically from the off-cluster repository.

> Source: [`mitchross/talos-argocd-proxmox`](https://github.com/mitchross/talos-argocd-proxmox)
> · This site renders `docs/` from that repo.

![Logical overview of the Proxmox, Talos, Argo CD, networking, secrets, storage, and backup platform](assets/platform-overview.svg)

*Git reconstructs desired state, 1Password reconstructs credentials, and RustFS
reconstructs protected data. [Open the full-size platform map](assets/platform-overview.svg).*

!!! tip "The point"
    The whole cluster can be destroyed and rebuilt with every protected volume
    restored automatically from the off-cluster Kopia repository — no manual storage
    steps. See [disaster recovery](disaster-recovery.md).

## Stack

- **OS**: Talos Linux on Proxmox VMs, provisioned via Omni / Sidero
- **CNI**: Cilium with Gateway API + LoadBalancer
- **GitOps**: ArgoCD (self-managing) + ApplicationSets for auto-discovery
- **Storage**: Longhorn V1, placed by drive endurance; mostly one replica, with
  two for data that can't be re-created. NAS provides bulk files and
  off-cluster backups. [Current capacity and storage dependencies](inventory/2026-09-20-capacity-and-benchmarks.md).
- **Backup**: [kopiur](https://github.com/home-operations/kopiur) (Kopia-native) → RustFS S3, per-PVC `SnapshotPolicy`/`Restore` with restore-before-bind
- **Database**: plain Postgres Deployments backed up by kopiur — daily snapshots (every 6 hours for data that can't be re-created), restore-before-bind
- **Secrets**: 1Password Connect + External Secrets Operator
- **Observability**: kube-prometheus-stack, Loki, Tempo, OpenTelemetry
- **AI**: the production backend serves official `qwen3.8-27b` FP8 through vLLM
  on both RTX 3090s. The [model catalog](domains/ai-gpu/model-catalog.md)
  owns the local backend and Pi's optional OpenRouter DeepSeek Flash route; use the
  [scale-swap runbook](domains/ai-gpu/gpu-scale-swap.md) to change the card owner.

## Reading order

Start with [the easy guide](easy-guide.md), then follow the sidebar from top to
bottom: understand the platform, learn how to operate it, explore the hardware,
review its measured performance, and consider future changes.

| Sidebar section | Use it for | Start here |
|---|---|---|
| Overview | Understand how the platform works | [The easy guide](easy-guide.md) |
| Operations | Learn the deployed platform and its procedures | [Operations guide](operations/index.md) |
| Inventory | Machines, disks, hardware health, and workload placement | [Inventory](inventory/index.md) |
| Audits | Performance measurements, limitations, and ranked recommendations | [Audits](audits/index.md) |
| Ongoing research | Options being considered and the tests needed to decide | [Research](research/index.md) |

For current upgrade priorities, jump to the
[September 20 decision report](audits/2026-09-20-homelab-report.html).

The dates matter: a historical inventory is not a live dashboard, and a research
proposal is not a deployed change. NAS benchmarks carry their own September 20
collection date; other host inventories retain their original dates.

## Frequent tasks

1. **Find a machine or its disks:** [Explore the lab](lab.md), or open the
   [hardware diagnostics report](diagnostics.md) for detailed evidence.
2. **Understand NAS speeds and RAM:** [NAS performance](nas-performance.md)
   separates physical-disk reads, RAM-cache reads, and flushed writes.
3. **Add or troubleshoot backups:** start with the
   [kopiur architecture](domains/storage/kopiur-backup-architecture.md), then
   [mover permissions](domains/storage/kopiur-mover-permissions.md).
4. **Recover the platform:** use the [disaster recovery runbook](disaster-recovery.md).
   The [backup simulator](kopiur-playground.md) provides a safe browser-only walkthrough.
5. **Release a worker:** use the
   [Temporal safe deployment runbook](domains/temporal/safe-deployments.md).
6. **Keep SSD wear down:** follow the [disk-write rules](domains/storage/disk-writes.md)
   and check the top writers there.

Every page follows the [documentation reader contract](documentation-standard.md):
state the current posture, explain unfamiliar choices, provide verifiable steps,
and include failure/rollback guidance for risky operations.

## Adopting any of this

This is one operator's homelab, not a product. The patterns are portable —
the label-driven backup contract, the off-cluster repository, the
restore-canary idea, the sync-wave bootstrap — but the image tags, hostnames,
and 1Password item names are not. Start with
[storage-architecture.md](storage-architecture.md).
