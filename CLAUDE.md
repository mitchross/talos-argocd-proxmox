# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Detailed instructions are in nested CLAUDE.md files** that load automatically based on which directory you're working in. This root file contains cross-cutting rules that apply everywhere.

## Project Overview

This is a production-grade GitOps Kubernetes cluster running on **Talos OS** with **self-managing ArgoCD**. The key differentiator is that ArgoCD manages its own configuration and automatically discovers applications through directory structure - no manual Application manifests needed.

**Tech Stack**: Talos OS + ArgoCD + Cilium (Gateway API) + Longhorn + 1Password + GPU support

**AI/LLM Backend**: This cluster uses **llama-cpp** (NOT ollama) for all local AI inference. The llama-cpp server runs at `http://llama-cpp-service.llama-cpp.svc.cluster.local:8080` with an OpenAI-compatible API at `/v1`. Primary model: **Qwen3.6-35B-A3B** (Unsloth UD-Q4_K_XL + `mmproj-BF16.gguf`) — multimodal, covers chat/coding/tool-calling and vision. **Gemma 4 26B-A4B** and **Qwen 3.5 Uncensored** are kept as additional presets. Full preset list + ctx/sampling is in `my-apps/ai/llama-cpp/configmap.yaml`. GPU topology: GPU 0 → llama-cpp, GPU 1 → ComfyUI (whole-card allocation, time-slicing disabled). Always use llama-cpp when configuring AI backends for in-cluster tools.

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
my-apps/ai/llama-cpp/           → ArgoCD Application "llama-cpp"
infrastructure/storage/longhorn/ → ArgoCD Application "longhorn"
monitoring/prometheus-stack/     → ArgoCD Application "prometheus-stack"
```

## Sync Wave Architecture

Applications deploy in strict order to prevent race conditions:

| Wave | Component | Purpose |
|------|-----------|---------|
| **0** | Foundation | Cilium (CNI), ArgoCD, 1Password Connect, External Secrets, AppProjects |
| **1** | Storage | Longhorn, VolumeSnapshot Controller, VolSync |
| **2** | PVC Plumber | Backup existence checker (FAIL-CLOSED gate) |
| **3** | CNPG Barman Plugin | Database backup plugin before database clusters |
| **4** | Infrastructure AppSet + custom entrypoints | Explicit path list plus KEDA and Temporal Worker Controller standalone Apps |
| **4** | Database AppSet | Discovers `infrastructure/database/*/*` — `selfHeal: false` for DR |
| **5** | OTEL + Monitoring AppSet | OpenTelemetry Operator plus `monitoring/*` |
| **6** | My-Apps AppSet | Discovers `my-apps/*/*` |

**FAIL-CLOSED**: If pvc-plumber operator's validating webhook is down (failurePolicy: Fail), backup-labeled PVC creation is denied via Kubernetes admission. Apps retry via ArgoCD backoff. This prevents data loss during disaster recovery.

**Databases** use a separate AppSet with `selfHeal: false` so `skip-reconcile` annotations stick during DR recovery. The infrastructure AppSet uses `selfHeal: true` which would strip manual annotations.

**AppProjects** are intentionally permissive for this single-operator homelab.
They provide UI grouping and policy intent, not multi-tenant security. Tighten
`destinations` and `clusterResourceWhitelist` before allowing untrusted authors
or external automation to write application manifests.

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
- Add `backup: "hourly"` or `backup: "daily"` labels to critical PVCs for automatic pvc-plumber backup
- When marking a PVC `backup-exempt: "true"`, the reason annotation key **must be fully qualified**: `storage.vanillax.dev/backup-exempt-reason`. The bare `backup-exempt-reason` is silently ignored by the operator and the PVC is **denied on CREATE** — invisible until recreate/DR. CI job `backup-exempt-contract` enforces this
- Use `storageClassName: longhorn` for PVCs that need backups (volumesnapshot required)
- Use NFS CSI driver (`csi: driver: nfs.csi.k8s.io`) for static NFS PVs — **legacy `nfs:` silently ignores mountOptions**
- Add new infrastructure component paths to `infrastructure/controllers/argocd/apps/appsets/infrastructure-appset.yaml` explicitly (not glob-discovered)
- List ALL YAML files in each directory's `kustomization.yaml` under `resources:` — **unlisted files are never deployed**
- Use llama-cpp (not ollama) for in-cluster AI backends
- Use sync waves when adding infrastructure components
- Add ArgoCD hook annotations to all Kubernetes Jobs — `argocd.argoproj.io/hook: Sync` + `argocd.argoproj.io/hook-delete-policy: BeforeHookCreation`. K8s Jobs are immutable after creation; without these, image tag bumps from Renovate cause "field is immutable" sync failures. For standalone Jobs, add annotations directly. For Helm-rendered Jobs, use Kustomize patches targeting `kind: Job`
- Check `helm show values <chart> | grep -A20 certManager` when adding any Helm chart with webhooks — if a `certManager.enabled` option exists, **set it to `true`**. Helm hook Jobs for webhook certs break under ArgoCD (SA deleted before Job runs = stuck forever = API server death)
- Verify pvc-plumber generated backup resources after creating PVCs with backup labels
- For abandoned CNPG backup lineages, update `infrastructure/storage/rustfs-lifecycle/postgres-backups-lifecycle-cm.yaml`; keep the full bucket lifecycle policy there because PUT replaces the whole RustFS lifecycle config
- Use `strategy: type: Recreate` on Deployments with RWO PVCs — **RollingUpdate causes Multi-Attach deadlock**

### DON'T:
- Create manual ArgoCD `Application` resources (use directory discovery)
- Use `kubectl edit` on Talos nodes (changes are ephemeral)
- Create Services without named ports when using HTTPRoute
- Mix Ingress and Gateway API
- Commit secrets to Git
- Bypass GitOps workflow for configuration changes
- Deploy without considering sync wave order
- Add backup labels to CNPG database PVCs (they use Barman to S3, not pvc-plumber/VolSync)
- Add active CNPG `serverName` prefixes to RustFS lifecycle expiration rules; only abandoned lineages belong there
- Add backup labels to system namespace PVCs (kube-system, volsync-system, argocd, longhorn-system)
- Manually create or delete ReplicationSource/ReplicationDestination (pvc-plumber manages these)
- Use legacy `nfs:` block for NFS PVs (mountOptions silently ignored — use CSI)
- Use `RollingUpdate` strategy on Deployments with RWO PVCs (causes Multi-Attach deadlock)
- Create external HTTPRoutes without the three required pieces: `external-dns: "true"` label, `external-dns.alpha.kubernetes.io/target: vanillax.me` annotation, and `sectionName: https` — **DNS won't be created and Cloudflare tunnel routing fails silently**
- Use `Replace=true,Force=true` sync-options on Jobs — causes duplicate Job execution bug ([#24005](https://github.com/argoproj/argo-cd/issues/24005)); use ArgoCD hooks instead
- Auto-merge major Helm chart version bumps for critical infrastructure (kube-prometheus-stack, longhorn, cilium) — **a kube-prometheus-stack v82→v83 auto-merge caused a full cluster outage on 2026-04-08 via Kyverno webhook deadlock**. Pin Renovate to minor/patch only for these charts.
- Remove infrastructure namespaces from pvc-plumber webhook exclusions in `infrastructure/controllers/pvc-plumber/webhooks.yaml` — longhorn-system, argocd, volsync-system, etc. MUST stay in the `NotIn` list or a pvc-plumber crash causes full cluster deadlock on backup-labeled PVC creates.

## Nested CLAUDE.md Files

Detailed instructions load automatically when working in these directories:

| Directory | Contains |
|-----------|----------|
| `infrastructure/` | Essential commands, AppSet rules, ArgoCD/secret debugging |
| `infrastructure/storage/` | Storage classes, NFS CSI patterns, 10G performance tuning |
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
| **PVC with automatic backup** | `my-apps/home/project-zomboid/pvc.yaml` (backup on `zomboid-data`, unlabeled `zomboid-server-files`) |
| **pvc-plumber operator manifests** | `infrastructure/controllers/pvc-plumber/` |
| **VolSync configuration** | `infrastructure/storage/volsync/` |
| **RustFS lifecycle policy** | `infrastructure/storage/rustfs-lifecycle/` |
| **Helm + Kustomize** | `infrastructure/controllers/1passwordconnect/` |
| **Database with CNPG** | `infrastructure/database/cloudnative-pg/immich/` |
| **Database AppSet** | `infrastructure/controllers/argocd/apps/appsets/database-appset.yaml` |
| **Gateway API routing** | `infrastructure/networking/gateway/` |
| **OTEL Operator + Collectors** | `infrastructure/controllers/opentelemetry-operator/` |
| **OTEL auto-instrumentation** | `infrastructure/controllers/opentelemetry-operator/instrumentation.yaml` |
| **Jobs with ArgoCD hooks** | `my-apps/development/posthog/core/jobs.yaml` |
| **Helm Job Kustomize patch** | `my-apps/development/temporal/kustomization.yaml` |

## Additional Documentation

- **[docs/volsync-storage-recovery.md](docs/volsync-storage-recovery.md)** - PVC backup/restore single source of truth (architecture, sync waves, admission flow, scenarios, troubleshooting)
- **[docs/cnpg-disaster-recovery.md](docs/cnpg-disaster-recovery.md)** - CNPG database DR procedures (separate system: Barman → S3)
- **[docs/network-topology.md](docs/network-topology.md)** - Network architecture details
- **[docs/network-policy.md](docs/network-policy.md)** - Cilium network policies
- **[docs/argocd.md](docs/argocd.md)** - ArgoCD documentation
- **[docs/argocd-entrypoints.md](docs/argocd-entrypoints.md)** - ArgoCD root entrypoints, waves, and AppSet/custom-entrypoint decisions
- **[scripts/emergency-webhook-cleanup.sh](scripts/emergency-webhook-cleanup.sh)** - Emergency recovery from pvc-plumber webhook deadlock (or any future webhook with failurePolicy: Fail in volsync-system/argocd/longhorn-system path)

## Mink capture

Keep Mink updated during substantive work. Mink hooks may track session activity automatically, but durable project knowledge still needs explicit capture with `mink note` or the `/mink:note` skill.

Capture decisions that change architecture or operations, verified bug root causes, live-system gotchas, reusable patterns, and future-operator context. Do not capture routine edits, raw command output, or unverified hypotheses.

Use `mink note --project talos-argocd-proxmox --category resources` for durable runbooks/gotchas/patterns and `--category projects` for active decisions or followups. Mention saved Mink note paths in the final response.
