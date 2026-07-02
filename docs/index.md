# talos-argocd-proxmox

A production-grade GitOps Kubernetes cluster on **Talos Linux** with
**self-managing ArgoCD**: applications are discovered from directory
structure, storage is backed up declaratively via PVC labels, and the whole
cluster can be destroyed and rebuilt **unattended** — restores included.

> Source: [`mitchross/talos-argocd-proxmox`](https://github.com/mitchross/talos-argocd-proxmox)
> · This site renders `docs/` from that repo.

!!! tip
    **The headline claim, with receipts:** this cluster was fully destroyed and
    rebuilt twice in 36 hours (2026-06-12/13 — once unplanned, once planned).
    Both times, every protected volume restored automatically from the
    off-cluster Kopia repository. The second rebuild took ~75 minutes with
    **zero manual storage steps**. See [disaster-recovery.md](disaster-recovery.md#proof-history).

## Stack

- **OS**: Talos Linux on Proxmox VMs, provisioned via Omni / Sidero
- **CNI**: Cilium with Gateway API + LoadBalancer
- **GitOps**: ArgoCD (self-managing) + ApplicationSets for auto-discovery
- **Storage**: Longhorn (V1 engine, 1 replica — single-node)
- **Backup**: [kopiur](https://github.com/home-operations/kopiur) (Kopia-native) → RustFS S3, per-PVC `SnapshotPolicy`/`Restore` with restore-before-bind
- **Database**: CloudNativePG (Postgres) with Barman backups to S3
- **Secrets**: 1Password Connect + External Secrets Operator
- **Observability**: kube-prometheus-stack, Loki, Tempo, OpenTelemetry
- **AI**: vLLM (Qwen3.6-27B, default app inference) + llama-cpp (Qwen3.6-35B multimodal, for ComfyUI) on mutually-exclusive whole-card GPUs

## Documentation

<div class="grid cards" markdown>

-   📖 **The easy guide** — *share this one*

    ---

    The whole system from zero: GitOps → sync waves → Kustomize components →
    kopiur → restore-before-bind. Real YAML, an adoption ladder for
    "I just want to try kopiur", and the colleague FAQ.

    [→ easy-guide.md](easy-guide.md)

-   💾 **kopiur backup architecture** — *the one doc*

    ---

    The pieces, the component pattern, backup + restore flow diagrams, and
    the 6-step add-a-backup checklist.

    [→ kopiur-backup-architecture.md](domains/storage/kopiur-backup-architecture.md)

-   ☠️ **Disaster recovery** — *the runbook*

    ---

    Destroy → rebuild → restore: pre-nuke checklist, restore-wave
    expectations, proof history, the restore canary.

    [→ disaster-recovery.md](disaster-recovery.md)

-   🗄️ **Storage architecture** — *operator's reference*

    ---

    Design decisions, who-provides-what, day-2 operations
    (enable / exempt / drill), troubleshooting, and the honest limitations.

    [→ storage-architecture.md](storage-architecture.md)

</div>

### 💾 More storage & backups

Backups are **kopiur** (Kopia-native operator; replaced pvc-plumber + VolSync 2026-06-27).

- **[kopiur-playground.md](kopiur-playground.md)** — 🕹️ interactive, in-browser
  simulation of backup + restore-before-bind: delete a PVC, take S3 offline,
  nuke the cluster, watch what happens.
- **[domains/storage/kopiur-mover-permissions.md](domains/storage/kopiur-mover-permissions.md)** —
  why the backup mover runs as the data owner (the #1 gotcha), plain English + technical.
- **[backup-repository-setup.md](backup-repository-setup.md)** — the one-time backend
  setup: RustFS S3 bucket, credentials, the kopiur `ClusterRepository`.

### 🗃️ Domains

- **Databases**: [Backup/restore/start — beginner guide](domains/cnpg/backup-restore-start-guide.md) · [CNPG explained](domains/cnpg/explained.md) · [CNPG disaster recovery](domains/cnpg/disaster-recovery.md)
- **GitOps / ArgoCD**: [argocd](domains/argocd/argocd.md) · [entrypoints & waves](domains/argocd/entrypoints.md)
- **Networking**: [topology](domains/networking/topology.md) · [policy](domains/networking/policy.md) · [Technitium `vanillax.me` migration](domains/networking/technitium-vanillax-me-migration.md)
- **Storage**: [kopia maintenance](domains/storage/kopia-maintenance-plan.md) · [RWO/RWX model & sizing](domains/storage/storage-model-rwo-rwx-and-sizing.md) · [RustFS credentials](domains/rustfs/credential-runbook.md) · [future: tiered storage](domains/storage/architecture-future.md)
- **Multicluster**: [PRD](domains/multicluster/prd.md) · [handoff notes](domains/multicluster/handoff-notes.md)
- **Observability**: [radar-ng](domains/observability/radar-ng.md)
- **AI / GPU**: [model catalog](domains/ai-gpu/model-catalog.md) · [3090 LLM optimization](domains/ai-gpu/3090-llm-optimization.md)

## Adopting any of this

This is one operator's homelab, not a product. The patterns are portable —
the label-driven backup contract, the off-cluster repository, the
restore-canary idea, the sync-wave bootstrap — but the image tags, hostnames,
and 1Password item names are not. Start with
[storage-architecture.md](storage-architecture.md).
