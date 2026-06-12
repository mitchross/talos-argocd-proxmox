# talos-argocd-proxmox

A production-grade GitOps Kubernetes cluster on **Talos Linux** with
**self-managing ArgoCD**: applications are discovered from directory
structure, storage is backed up declaratively via PVC labels, and the whole
cluster can be destroyed and rebuilt **unattended** — restores included.

> Source: [`mitchross/talos-argocd-proxmox`](https://github.com/mitchross/talos-argocd-proxmox)
> · This site renders `docs/` from that repo.

> [!TIP]
> **The headline claim, with receipts:** this cluster was fully destroyed and
> rebuilt twice in 36 hours (2026-06-12/13 — once unplanned, once planned).
> Both times, every protected volume restored automatically from the
> off-cluster Kopia repository. The second rebuild took ~75 minutes with
> **zero manual storage steps**. See [disaster-recovery.md](disaster-recovery.md#proof-history).

## Stack

- **OS**: Talos Linux on Proxmox VMs, provisioned via Omni / Sidero
- **CNI**: Cilium with Gateway API + LoadBalancer
- **GitOps**: ArgoCD (self-managing) + ApplicationSets for auto-discovery
- **Storage**: Longhorn (V1 engine, 2× replicas)
- **Backup**: VolSync + Kopia → RustFS S3, wired by [pvc-plumber](https://github.com/mitchross/pvc-plumber) from PVC labels
- **Database**: CloudNativePG (Postgres) with Barman backups to S3
- **Secrets**: 1Password Connect + External Secrets Operator
- **Observability**: kube-prometheus-stack, Loki, Tempo, OpenTelemetry
- **AI**: llama-cpp (Qwen3.6-35B multimodal) + ComfyUI on dedicated GPUs

## Documentation

### 🚰 Storage & backups (start here)

1. **[storage-architecture.md](storage-architecture.md)** — **the one doc.**
   Why it exists, plain-English explanation, the label contract, every
   diagram, day-2 operations (add/exempt/verify/drill), troubleshooting,
   adapting it to your cluster, honest limitations. *Send people this link.*
   Visual learner? **[🎮 the interactive simulator](simulator.html)** lets you
   nuke a toy cluster and watch the restore.
2. **[backup-repository-setup.md](backup-repository-setup.md)** — the one-time
   backend setup: S3 box, bucket, credentials, fan-out, the fail-closed gate.
3. **[disaster-recovery.md](disaster-recovery.md)** — the full-cluster
   destroy/rebuild runbook: pre-nuke checklist, calibrated restore-wave
   expectations, proof history, the restore canary.

### 🗃️ Domains

- **Databases**: [CNPG disaster recovery](domains/cnpg/disaster-recovery.md) · [CNPG explained](domains/cnpg/explained.md)
- **GitOps / ArgoCD**: [argocd](domains/argocd/argocd.md) · [entrypoints & waves](domains/argocd/entrypoints.md)
- **Networking**: [topology](domains/networking/topology.md) · [policy](domains/networking/policy.md)
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
