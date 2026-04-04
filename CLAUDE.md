# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Detailed instructions are in nested CLAUDE.md files** that load automatically based on which directory you're working in. This root file contains cross-cutting rules that apply everywhere.

## Project Overview

This is a production-grade GitOps Kubernetes cluster running on **Talos OS** with **self-managing ArgoCD**. The key differentiator is that ArgoCD manages its own configuration and automatically discovers applications through directory structure - no manual Application manifests needed.

**Tech Stack**: Talos OS + ArgoCD + Cilium (Gateway API) + Longhorn + 1Password + GPU support

**AI/LLM Backend**: This cluster uses **llama-cpp** (NOT ollama) for all local AI inference. The llama-cpp server runs at `http://llama-cpp-service.llama-cpp.svc.cluster.local:8080` with an OpenAI-compatible API at `/v1`. Current model: **Qwen3.5-35B-A3B** (Q4_K_XL). Always use llama-cpp when configuring AI backends for in-cluster tools.

## Core Architecture Pattern: GitOps Self-Management

```
Manual Bootstrap → ArgoCD → Root App → ApplicationSets → Auto-discovered Apps
```

1. **Bootstrap once**: Apply ArgoCD manifests manually via `scripts/bootstrap-argocd.sh`
2. **Root app triggers**: Points ArgoCD to scan `infrastructure/controllers/argocd/apps/`
3. **ApplicationSets discover**: Four ApplicationSets scan for directories and auto-create Applications
4. **Everything else is automatic**: Add directory + `kustomization.yaml` = deployed app

**Critical Understanding**: Directory = Application
```
my-apps/ai/ollama/          → ArgoCD Application "ollama"
infrastructure/storage/longhorn/ → ArgoCD Application "longhorn"
monitoring/prometheus-stack/    → ArgoCD Application "prometheus-stack"
```

## Sync Wave Architecture

Applications deploy in strict order to prevent race conditions:

| Wave | Component | Purpose |
|------|-----------|---------|
| **0** | Foundation | Cilium (CNI), ArgoCD, 1Password Connect, External Secrets, AppProjects |
| **1** | Storage | Longhorn, VolumeSnapshot Controller, VolSync |
| **2** | PVC Plumber | Backup existence checker (FAIL-CLOSED gate) |
| **3** | Kyverno | Policy engine (standalone App, webhooks must register before app PVCs) |
| **4** | Infrastructure AppSet | Explicit path list: cert-manager, external-dns, GPU operators, gateway |
| **4** | Database AppSet | Discovers `infrastructure/database/*/*` — `selfHeal: false` for DR |
| **5** | Monitoring AppSet | Discovers `monitoring/*` |
| **6** | My-Apps AppSet | Discovers `my-apps/*/*` |

**FAIL-CLOSED**: If PVC Plumber is down, Kyverno denies backup-labeled PVC creation. Apps retry via ArgoCD backoff. This prevents data loss during disaster recovery.

**Kyverno** is a standalone Application (not in an AppSet) to guarantee webhooks register before app PVCs. ApplicationSets are considered "healthy" immediately on creation.

**Databases** use a separate AppSet with `selfHeal: false` so `skip-reconcile` annotations stick during DR recovery. The infrastructure AppSet uses `selfHeal: true` which would strip manual annotations.

## Secret Management Flow

```
1Password Vault (homelab-prod) → 1Password Connect API → ClusterSecretStore → ExternalSecret → K8s Secret → Pod
```

**Never commit secrets to Git**. Always use ExternalSecret resources pointing to 1Password.

## Directory Structure

```
infrastructure/          # Core cluster components (Wave 4)
├── controllers/        # Operators and system controllers
├── database/          # Database operators and instances
├── networking/        # Cilium, Gateway API, DNS
└── storage/           # Longhorn, NFS, SMB, Local storage

monitoring/             # Observability stack (Wave 5)
my-apps/                # User applications (Wave 6)
├── ai/                # GPU workloads
├── development/       # Dev tools
├── home/              # Home automation
├── media/             # Media services
└── common/            # Shared Kustomize components

scripts/                # Automation tools
omni/                   # Omni (Sidero) deployment configs
docs/                   # Documentation
```

## Critical Rules

### DO:
- Use directory structure for application discovery (no manual Application resources)
- Name Service ports for HTTPRoute compatibility (`name: http`) — **fails silently without this**
- Use Gateway API (not Ingress) — this cluster uses Gateway API exclusively
- On **external** HTTPRoutes: add `labels: external-dns: "true"`, annotation `external-dns.alpha.kubernetes.io/target: vanillax.me`, and `sectionName: https` on the parentRef — **all three are required or DNS/routing silently fails**
- Follow GitOps workflow for all changes
- Store secrets in 1Password, reference via ExternalSecret
- Add `backup: "hourly"` or `backup: "daily"` labels to critical PVCs for automatic Kyverno backup
- Use `storageClassName: longhorn` for PVCs that need backups (volumesnapshot required)
- Use NFS CSI driver (`csi: driver: nfs.csi.k8s.io`) for static NFS PVs — **legacy `nfs:` silently ignores mountOptions**
- Add new infrastructure component paths to `infrastructure-appset.yaml` explicitly (not glob-discovered)
- List ALL YAML files in each directory's `kustomization.yaml` under `resources:` — **unlisted files are never deployed**
- Use llama-cpp (not ollama) for in-cluster AI backends
- Use sync waves when adding infrastructure components
- Add ArgoCD hook annotations to all Kubernetes Jobs — `argocd.argoproj.io/hook: Sync` + `argocd.argoproj.io/hook-delete-policy: BeforeHookCreation`. K8s Jobs are immutable after creation; without these, image tag bumps from Renovate cause "field is immutable" sync failures. For standalone Jobs, add annotations directly. For Helm-rendered Jobs, use Kustomize patches targeting `kind: Job`
- Check `helm show values <chart> | grep -A20 certManager` when adding any Helm chart with webhooks — if a `certManager.enabled` option exists, **set it to `true`**. Helm hook Jobs for webhook certs break under ArgoCD (SA deleted before Job runs = stuck forever = API server death)
- Verify Kyverno generated backup resources after creating PVCs with backup labels
- Use `strategy: type: Recreate` on Deployments with RWO PVCs — **RollingUpdate causes Multi-Attach deadlock**

### DON'T:
- Create manual ArgoCD `Application` resources (use directory discovery)
- Use `kubectl edit` on Talos nodes (changes are ephemeral)
- Create Services without named ports when using HTTPRoute
- Mix Ingress and Gateway API
- Commit secrets to Git
- Bypass GitOps workflow for configuration changes
- Deploy without considering sync wave order
- Add Kyverno backup labels to CNPG database PVCs (they use Barman to S3, not Kyverno/VolSync)
- Add backup labels to system namespace PVCs (kube-system, volsync-system, kyverno)
- Manually create or delete ReplicationSource/ReplicationDestination (Kyverno manages these)
- Use legacy `nfs:` block for NFS PVs (mountOptions silently ignored — use CSI)
- Use `RollingUpdate` strategy on Deployments with RWO PVCs (causes Multi-Attach deadlock)
- Use `background: true` on Kyverno generate policies — **causes API server overload from continuous background scanning; use `background: false`**
- Use `mutateExistingOnPolicyUpdate: true` on Kyverno generate policies — **re-evaluates ALL matching resources cluster-wide on any policy change**
- Use `synchronize: true` on Kyverno generate policies — **drift watchers create UpdateRequests on every controller status update, hammering the API server; use `synchronize: false`**
- Omit Kyverno canonical defaults (`emitWarning`, `validationFailureAction`, `skipBackgroundRequests`) from policy YAML — **Kyverno webhook adds them, ArgoCD detects the diff, app shows OutOfSync**
- Create external HTTPRoutes without the three required pieces: `external-dns: "true"` label, `external-dns.alpha.kubernetes.io/target: vanillax.me` annotation, and `sectionName: https` — **DNS won't be created and Cloudflare tunnel routing fails silently**
- Use `Replace=true,Force=true` sync-options on Jobs — causes duplicate Job execution bug ([#24005](https://github.com/argoproj/argo-cd/issues/24005)); use ArgoCD hooks instead

## Nested CLAUDE.md Files

Detailed instructions load automatically when working in these directories:

| Directory | Contains |
|-----------|----------|
| `infrastructure/` | Essential commands, AppSet rules, ArgoCD/secret debugging |
| `infrastructure/storage/` | Storage classes, NFS CSI patterns, 10G performance tuning |
| `infrastructure/controllers/kyverno/` | Full backup/restore system, PVC Plumber, Kyverno policies |
| `infrastructure/database/` | CNPG patterns, database DR procedures, serverName tracking |
| `infrastructure/networking/` | Gateway API routing patterns, HTTPRoute templates |
| `my-apps/` | App templates (minimal, web, secrets, storage), Helm+Kustomize patterns |
| `my-apps/ai/` | GPU workload patterns, llama-cpp backend |
| `monitoring/` | Monitoring pitfalls (S3 creds, ServiceMonitor selectors) |

## Custom Commands

| Command | Purpose |
|---------|---------|
| `/project:new-app <category/name>` | Guided workflow for adding a new application |
| `/project:add-backup <app-path>` | Add automatic backup to PVC(s) |
| `/project:new-database <app-name>` | Create a CNPG database |

## Reference Examples

| Pattern | Reference Location |
|---------|-------------------|
| **Minimal app** | `my-apps/development/nginx/` |
| **GPU workload** | `my-apps/ai/comfyui/` |
| **Complex app with storage** | `my-apps/media/immich/` |
| **PVC with automatic backup** | `my-apps/ai/khoj/pvc.yaml` |
| **Kyverno backup policies** | `infrastructure/controllers/kyverno/policies/volsync-pvc-backup-restore.yaml` |
| **PVC Plumber** | `infrastructure/controllers/pvc-plumber/` |
| **VolSync configuration** | `infrastructure/storage/volsync/` |
| **Helm + Kustomize** | `infrastructure/controllers/1passwordconnect/` |
| **Database with CNPG** | `infrastructure/database/cloudnative-pg/immich/` |
| **Database AppSet** | `infrastructure/controllers/argocd/apps/database-appset.yaml` |
| **Gateway API routing** | `infrastructure/networking/gateway/` |
| **OTEL Operator + Collectors** | `infrastructure/controllers/opentelemetry-operator/` |
| **OTEL auto-instrumentation** | `infrastructure/controllers/opentelemetry-operator/instrumentation.yaml` |
| **Jobs with ArgoCD hooks** | `my-apps/development/posthog/core/jobs.yaml` |
| **Helm Job Kustomize patch** | `my-apps/development/temporal/kustomization.yaml` |

## Additional Documentation

- **[docs/backup-restore.md](docs/backup-restore.md)** - Full backup/restore architecture with diagrams
- **[docs/cnpg-disaster-recovery.md](docs/cnpg-disaster-recovery.md)** - CNPG database DR procedures
- **[docs/pvc-plumber-full-flow.md](docs/pvc-plumber-full-flow.md)** - Complete PVC backup flow from bare metal
- **[docs/network-topology.md](docs/network-topology.md)** - Network architecture details
- **[docs/network-policy.md](docs/network-policy.md)** - Cilium network policies
- **[docs/argocd.md](docs/argocd.md)** - ArgoCD documentation
- **[docs/vpa-resource-optimization.md](docs/vpa-resource-optimization.md)** - VPA auto-scaling
- **[docs/plans/2026-03-22-alloy-otel-honeycomb-design.md](docs/plans/2026-03-22-alloy-otel-honeycomb-design.md)** - OTEL + Honeycomb observability design
