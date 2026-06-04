# talos-argocd-proxmox

A production-grade GitOps Kubernetes cluster running on **Talos OS** with
**self-managing ArgoCD**. ArgoCD manages its own configuration and discovers
applications by directory structure — no manual `Application` manifests
needed.

> Source repository: [`mitchross/talos-argocd-proxmox`](https://github.com/mitchross/talos-argocd-proxmox)
>
> This site is the rendered version of `docs/` from that repo. Pages link
> back to source files (✏️ edit icon, top right) for one-click PRs.

> [!IMPORTANT]
> **Current pvc-plumber state (2026-06-01):**
> - v4.0.1 live (permissive controller — **not** an admission gate)
> - 24 PVCs / 18 namespaces managed
> - 24/24 DR_COMPLETE
> - Kyverno **not** in the backup path
> - CNPG native / Barman → S3
> - PostHog backup-exempt · redis-instance backup-exempt
> - migration campaign **closed** — no remaining candidates

> [!WARNING]
> **Current multicluster/OpenShift state (2026-06-04):**
> - structural migration locally accepted on `feat/one-shot-multicluster-kustomize`
> - isolated live-test repo: `mitchross/talos-argocd-proxmox-multicluster-test`
> - live OpenShift `sno-ai-lab` is **not ready for bootstrap**
> - unresolved LVM Storage, Gateway LoadBalancer publishing, and route DNS
> - read [multicluster handoff notes](domains/multicluster/handoff-notes.md)
>   before OpenShift or multicluster work

## Stack

- **OS**: Talos Linux on Proxmox VMs, provisioned via Omni / Sidero
- **CNI**: Cilium with Gateway API + LoadBalancer
- **GitOps**: ArgoCD (self-managing) + ApplicationSets for auto-discovery
- **Storage**: Longhorn (RWO block) + TrueNAS/RustFS (Kopia repository on S3)
- **Backup**: VolSync + Kopia, wired by [pvc-plumber](https://github.com/mitchross/pvc-plumber) v4 (a permissive PVC-watching controller)
- **Database**: CloudNativePG (Postgres) with Barman backups to RustFS S3
- **Secrets**: 1Password Connect + External Secrets Operator
- **Observability**: kube-prometheus-stack, Loki, Tempo, OpenTelemetry, Grafana
- **AI**: llama-cpp (Qwen3.6-35B-A3B multimodal) on dedicated GPU

## Documentation

### 🚀 Start here (pvc-plumber)

1. **[pvc-plumber-start-here](pvc-plumber-start-here.md)** — visual intro: what it is, the architecture, what it does NOT do, v4-vs-v5.
2. **[pvc-plumber-cheatsheet](pvc-plumber-cheatsheet.md)** — one-page poster.
3. **[pvc-plumber-dynamic-workflow](pvc-plumber-dynamic-workflow.md)** — how the operator thinks (decision trees, `/audit` actions).
4. **[talos-argocd-pvc-plumber-integration](talos-argocd-pvc-plumber-integration.md)** — how this repo uses it (add-a-PVC checklist, labels).

### 🛠️ Operate the platform

- **[volsync-storage-recovery](volsync-storage-recovery.md)** — PVC backup/restore single source of truth + restore-drill runbook.
- **[kopia-maintenance-plan](domains/storage/kopia-maintenance-plan.md)** — repository maintenance (healthy; manual full not needed).
- **[storage-architecture-future](domains/storage/architecture-future.md)** — Longhorn-vs-restore-DR tiering (future idea).
- **[pvc-plumber-v4-cutover](pvc-plumber-v4-cutover.md)** — day-of cutover runbook (label model, ownership, rollback).
- **[pvc-plumber-v4-migration-readiness](pvc-plumber-v4-migration-readiness.md)** — per-PVC migration status (campaign closed).
- **[cluster-dr-nuke-restore-runbook](cluster-dr-nuke-restore-runbook.md)** — full cluster rebuild/restore runbook.

### Bootstrap rules from the full nuke

- CRDs first, controllers/apps second, CRs third.
- Observability is optional. Core apps must bootstrap without Prometheus.
- Do not install Prometheus Operator CRDs early to satisfy bootstrap apps.
- `kube-prometheus-stack` remains the sole owner of `monitoring.coreos.com` CRDs.

### 📐 Design / PRD

- **[pvc-plumber-v4-prd](pvc-plumber-v4-prd.md)** — locked design + **§0 canonical status** (shipped vs design).
- **[pvc-plumber-v4-roadmap](pvc-plumber-v4-roadmap.md)** — post-PRD backlog.
- **[pvc-plumber-v5-kopia-native-future](pvc-plumber-v5-kopia-native-future.md)** — v5 fork (VolSync-strict vs Kopia-native) — **parked, not built.**
- **[multicluster-prd](domains/multicluster/prd.md)** — multicluster design.

### 🗃️ Other domains

- **Databases**: [cnpg-disaster-recovery](domains/cnpg/disaster-recovery.md) · [cnpg-explained](domains/cnpg/explained.md)
- **GitOps / ArgoCD**: [argocd](domains/argocd/argocd.md) · [argocd-entrypoints](domains/argocd/entrypoints.md)
- **Networking**: [network-topology](domains/networking/topology.md) · [network-policy](domains/networking/policy.md)
- **Storage**: [rustfs-credential-runbook](domains/rustfs/credential-runbook.md) · [kopia-maintenance-plan](domains/storage/kopia-maintenance-plan.md) · [storage-architecture-future](domains/storage/architecture-future.md)
- **Multicluster**: [handoff notes](domains/multicluster/handoff-notes.md) · [prd](domains/multicluster/prd.md) · [OpenShift storage/apps](domains/multicluster/openshift-storage-and-app-migration.md)
- **Observability**: [radar-ng-observability](domains/observability/radar-ng.md)
- **AI / GPU**: [ai-model-catalog](domains/ai-gpu/model-catalog.md) · [3090-llm-optimization](domains/ai-gpu/3090-llm-optimization.md)

### 🗄️ Archive (historical only)

Historical migration, incident, design, and presentation docs live under
**[`archive/`](archive/README.md)** — preserved for context, **not** current runbooks.
Older research and plans remain under `research/` and `plans/` (also historical).

## How to read these docs

- Start with the pvc-plumber visual docs for the current operator model.
- Use the storage recovery page for application PVC operations.
- Use the CNPG DR page only for CNPG recovery.
- Use the nuke runbook only for full rebuild planning.
- Treat `archive/`, `research/`, and `plans/` as historical context.

## Adopting any of this

This is one operator's homelab, not a product. The patterns are portable,
but the specific image tags, hostnames, and 1Password item names are not.
Start with [VolSync storage recovery](volsync-storage-recovery.md) and
[Talos ArgoCD pvc-plumber integration](talos-argocd-pvc-plumber-integration.md).
