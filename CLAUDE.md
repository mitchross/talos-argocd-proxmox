# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Detailed instructions are in nested CLAUDE.md files** that load automatically based on which directory you're working in. This root file contains cross-cutting rules that apply everywhere.

## Project Overview

This is a production-grade GitOps Kubernetes cluster running on **Talos OS** with **self-managing ArgoCD**. The key differentiator is that ArgoCD manages its own configuration and automatically discovers applications through directory structure - no manual Application manifests needed.

**Tech Stack**: Talos OS + ArgoCD + Cilium (Gateway API) + Longhorn + 1Password + GPU support

**AI/LLM Backend**: Two OpenAI-compatible local backends, both NOT ollama:

- **vLLM** (`http://vllm-service.vllm.svc.cluster.local:8080/v1`, served model `qwen3.6-27b` — Qwen3.6-27B dense AWQ, multimodal/vision) is the **default for app inference**. OpenWebUI, Perplexica, Project NOMAD, and Karakeep all point here. Use vLLM / `qwen3.6-27b` when wiring an in-cluster app to chat/vision inference.
- **llama-cpp** (`http://llama-cpp-service.llama-cpp.svc.cluster.local:8080/v1`) serves the **Qwen3.6-35B-A3B** MoE (Unsloth UD-Q4_K_XL + `mmproj-BF16.gguf`) plus Gemma 4 and Qwen 3.5 Uncensored as selectable presets (aliases `qwen3.6` / `qwen3.6-nothink` / `qwen3.6-longctx` / `gemma4*` / `uncensored`; see `my-apps/ai/llama-cpp/presets.ini`). Kept for ComfyUI's vision→image workflow and manual/interactive multi-preset use.

GPU topology: the GPU workloads are **mutually exclusive whole-card** (`type: Recreate`, time-slicing disabled — never two pods on the cards at once). They scale-swap: bringing one up means scaling the others to `replicas: 0`. Current state is vLLM `replicas: 1` with llama-cpp and ComfyUI at `0` (so the external `llama.vanillax.me` route reads "no healthy upstream" until llama-cpp is scaled back up). App→backend wiring is tabulated in `docs/domains/ai-gpu/model-catalog.md`; the swap procedure + card truth table live in `docs/domains/ai-gpu/gpu-scale-swap.md`.

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
| **1** | Core controllers | cert-manager, Longhorn, VolumeSnapshot Controller |
| **2** | kopiur operator | Kopia-native backup operator (8 CRDs + controller + webhook), rendered from the OCI chart `oci://ghcr.io/home-operations/charts/kopiur`. Serves the volume populator for restore-before-bind. |
| **3** | CNPG Barman Plugin + kopiur config | Database backup plugin before DB clusters; kopiur `ClusterRepository cluster-kopia` + `ClusterExternalSecret` cred fanout + `VolumeSnapshotClass longhorn-snapclass` |
| **4** | Infrastructure AppSet + custom entrypoints | Explicit path list plus KEDA and Temporal Worker Controller standalone Apps |
| **4** | Database AppSet | Discovers `infrastructure/database/*/*` — `selfHeal: false` for DR |
| **5** | OTEL + Monitoring AppSet | OpenTelemetry Operator plus `monitoring/*` |
| **6** | Observability overlays + My-Apps AppSet | KEDA/OTEL ServiceMonitors after monitoring CRDs exist, plus `my-apps/*/*` |

**Backend-down safety** (kopiur, replacing the retired `wait-for-rustfs` MAP): a backup against an unreachable repo errors — the Snapshot Job fails and retries, nothing garbage is written. A **restore against an unreachable repo leaves the PVC `Pending`**: kopiur raises the backend error *before* the `onMissingSnapshot` decision, so an outage can never bind an empty volume. This preserves the exact guarantee the MAP gave VolSync, with no admission policy. (Source-verified: `crates/controller/src/restore/mod.rs` `resolve_snapshot`; a brand-new PVC with a *reachable* repo but no snapshot still binds empty and backs up forward — `onMissingSnapshot: Continue` = deploy-or-restore.)

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
- Add backups to a normal application PVC with **kopiur**: label the namespace `kopiur.home-operations.com/repo: cluster-kopia`, add a per-PVC stub (`SnapshotPolicy`+`SnapshotSchedule`+`Restore` in `kopiur/<pvc>.yaml`) with the **mover `securityContext` set to the data owner uid:gid**, pull in the `../../common/kopiur-backup` component, and point the PVC `dataSourceRef` at `<pvc>-restore`. See `.claude/commands/add-backup.md` and `docs/domains/storage/kopiur-backup-architecture.md`.
- When marking a PVC `backup-exempt: "true"`, pair it with the fully-qualified reason annotation `storage.vanillax.dev/backup-exempt-reason`. There is **no runtime admission gate anymore** (pvc-plumber is gone) — the bare `backup-exempt-reason` key simply fails to record the reason; the kopiur backup-coverage CI check warns on missing/unqualified keys (it does not block)
- Use `storageClassName: longhorn` for PVCs that need backups (volumesnapshot required)
- Use NFS CSI driver (`csi: driver: nfs.csi.k8s.io`) for static NFS PVs — **legacy `nfs:` silently ignores mountOptions**
- Add new infrastructure component paths to `infrastructure/controllers/argocd/apps/appsets/infrastructure-appset.yaml` explicitly (not glob-discovered)
- List ALL YAML files in each directory's `kustomization.yaml` under `resources:` — **unlisted files are never deployed**
- Use **vLLM** (`qwen3.6-27b`, the default for app inference) or llama-cpp for in-cluster AI backends — **never ollama**
- Use sync waves when adding infrastructure components
- Add ArgoCD hook annotations to all Kubernetes Jobs — `argocd.argoproj.io/hook: Sync` + `argocd.argoproj.io/hook-delete-policy: BeforeHookCreation`. K8s Jobs are immutable after creation; without these, image tag bumps from Renovate cause "field is immutable" sync failures. For standalone Jobs, add annotations directly. For Helm-rendered Jobs, use Kustomize patches targeting `kind: Job`
- Check `helm show values <chart> | grep -A20 certManager` when adding any Helm chart with webhooks — if a `certManager.enabled` option exists, **set it to `true`**. Helm hook Jobs for webhook certs break under ArgoCD (SA deleted before Job runs = stuck forever = API server death)
- After adding a backed-up PVC, verify the in-namespace `kopiur-rustfs` Secret (fanned in by the ClusterExternalSecret) and the kopiur CRs: `kubectl -n <ns> get secret kopiur-rustfs; kubectl -n <ns> get snapshotpolicy,snapshotschedule,restore,snapshot` (the `Snapshot` should reach `Succeeded` with non-zero files)
- The pvc-plumber→kopiur migration is **closed** (2026-06-27): all PVCs use the kopiur component pattern; pvc-plumber + VolSync are removed. The mover runs as the PVC's data owner uid:gid (baseline PSS gives the mover no read capabilities). See `docs/domains/storage/kopiur-mover-permissions.md`.
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
- Add kopiur backup CRs to CNPG database PVCs (they use Barman to S3, not kopiur)
- Add active CNPG `serverName` prefixes to RustFS lifecycle expiration rules; only abandoned lineages belong there
- Add backup CRs to system namespace PVCs (kube-system, argocd, longhorn-system, kopiur-system)
- Manually create or delete kopiur `SnapshotPolicy`/`SnapshotSchedule`/`Restore` (or `ReplicationSource`/`ReplicationDestination` — those CRDs are gone) out of band. Manage backups through the per-PVC stub + the `kopiur-backup` component in git.
- Make observability a core dependency or install Prometheus Operator CRDs early just to satisfy bootstrap apps. `kube-prometheus-stack` is the sole owner of `monitoring.coreos.com` CRDs.
- Generic-migrate CNPG, PostHog, or Redis PVCs. CNPG uses native Barman/S3; PostHog and Redis are backup-exempt disposable data.
- Use legacy `nfs:` block for NFS PVs (mountOptions silently ignored — use CSI)
- Use `RollingUpdate` strategy on Deployments with RWO PVCs (causes Multi-Attach deadlock)
- Create external HTTPRoutes without the three required pieces: `external-dns: "true"` label, `external-dns.alpha.kubernetes.io/target: vanillax.me` annotation, and `sectionName: https` — **DNS won't be created and Cloudflare tunnel routing fails silently**
- Use `Replace=true,Force=true` sync-options on Jobs — causes duplicate Job execution bug ([#24005](https://github.com/argoproj/argo-cd/issues/24005)); use ArgoCD hooks instead
- Auto-merge major Helm chart version bumps for critical infrastructure (kube-prometheus-stack, longhorn, cilium) — **a kube-prometheus-stack v82→v83 auto-merge caused a full cluster outage on 2026-04-08 via Kyverno webhook deadlock**. Pin Renovate to minor/patch only for these charts.
- Run a kopiur mover as plain `root` to "fix" a permission error. Under baseline Pod Security the mover has no read capabilities, so root can't read non-root data — set the mover `securityContext` to the **data owner uid:gid** instead (`docs/domains/storage/kopiur-mover-permissions.md`). Only use `runAsUser: 0` + the `privileged-movers` namespace annotation when the data is genuinely root-owned.

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
| `/project:new-database <app-name>` | Create a database (plain Postgres + kopiur by default; CNPG only when PITR is required) |

## Reference Examples

| Pattern | Reference Location |
|---------|-------------------|
| **Minimal app** | template in `my-apps/CLAUDE.md` § "Minimal Application" (no live example is truly minimal) |
| **Backup with root-uid mover** | `my-apps/development/nginx/` (root-owned data: `runAsUser: 0` stub + `privileged-movers` namespace annotation) |
| **GPU workload** | `my-apps/ai/comfyui/` |
| **Complex app with storage** | `my-apps/media/immich/` |
| **PVC with automatic backup (kopiur)** | `my-apps/ai/open-webui/` (component + `kopiur/storage.yaml` stub + PVC `dataSourceRef`) |
| **kopiur backup component (shared)** | `my-apps/common/kopiur-backup/` |
| **kopiur repo + cred fanout + snapclass** | `infrastructure/controllers/kopiur/` |
| **Daemon-drop mover uid (999:568)** | `my-apps/home/project-nomad/mysql/kopiur-backup.yaml` |
| **Multi-PVC + backup-exempt mix** | `my-apps/home/project-zomboid/` (backs up `zomboid-data`, exempts `zomboid-server-files`) |
| **RustFS lifecycle policy** | `infrastructure/storage/rustfs-lifecycle/` |
| **Helm + Kustomize** | `infrastructure/controllers/1passwordconnect/` |
| **Plain Postgres + kopiur (new-DB default)** | `my-apps/development/gitea/postgres/` (pinned image, env-declared DB, hourly kopiur tier; runbook `docs/domains/cnpg/plain-postgres-migration.md`) |
| **Database with CNPG** | `infrastructure/database/cloudnative-pg/immich/` |
| **Database AppSet** | `infrastructure/controllers/argocd/apps/appsets/database-appset.yaml` |
| **Gateway API routing** | `infrastructure/networking/gateway/` |
| **OTEL Operator + Collectors** | `infrastructure/controllers/opentelemetry-operator/` |
| **OTEL auto-instrumentation** | `infrastructure/controllers/opentelemetry-operator/instrumentation.yaml` |
| **Jobs with ArgoCD hooks** | `my-apps/development/posthog/core/jobs.yaml` |
| **Helm Job Kustomize patch** | `my-apps/development/temporal/kustomization.yaml` |

## Additional Documentation

### 🚰 Docs reading order for agents (START HERE, in order)
1. **[docs/index.md](docs/index.md)** — canonical landing page + doc map.
2. **[docs/easy-guide.md](docs/easy-guide.md)** — zero-to-hero explainer of the whole stack (GitOps → waves → kopiur → restore-before-bind) with the adoption ladder for porting the pattern elsewhere. **Best first read for humans and new operators.**
3. **[docs/domains/storage/kopiur-backup-architecture.md](docs/domains/storage/kopiur-backup-architecture.md)** — the kopiur backup/restore architecture: the pieces, the Kustomize-component pattern, backup + restore flows (diagrams), add-a-backup checklist. **Start here for backups.**
4. **[docs/domains/storage/kopiur-mover-permissions.md](docs/domains/storage/kopiur-mover-permissions.md)** — why the mover runs as the data owner (the #1 backup gotcha). Plus **[docs/storage-architecture.md](docs/storage-architecture.md)** for the Longhorn/NFS/CNPG storage source-of-truth.
5. **[docs/disaster-recovery.md](docs/disaster-recovery.md)** — full-cluster destroy/rebuild runbook, pre-nuke checklist, restore-wave expectations, restore canary. **DR source of truth.**
6. **[docs/domains/](docs/index.md)** — per-domain docs (CNPG, ArgoCD, networking, storage deep-dives).

> ⚠️ **Agent guardrails when reading docs:**
> - **Do NOT resurrect Kyverno** — it was removed from the backup path (no policies, no CRDs, no webhooks).
> - **Do NOT add pvc-plumber/VolSync labels, `ReplicationSource`/`ReplicationDestination`, the `wait-for-rustfs` MAP, or `/audit` calls** — that whole stack was retired 2026-06-27. Backups are kopiur (per-PVC stub + `kopiur-backup` component); see `docs/domains/storage/kopiur-backup-architecture.md`.
> - **Do NOT generic-migrate CNPG, PostHog, or Redis PVCs** — CNPG is Barman-native; PostHog and Redis are backup-exempt.
> - **Do NOT make observability foundational** — core apps bootstrap without Prometheus; do not resurrect an early Prometheus Operator CRD app.
> - **Do NOT re-enable the Longhorn V2 engine** — tried and retired 2026-06-12 (open Longhorn bugs #13315/#13314: interrupted rebuilds corrupt replica metadata). Forensics in git history; the DR doc carries the short version.
> - Historical campaign/incident docs were pruned 2026-06-13 (git history retains them) — do not hunt for `docs/archive/`, `docs/research/`, `docs/plans/`, or `pvc-plumber-v4-*`/`v5-*` files.

- **[docs/domains/cnpg/disaster-recovery.md](docs/domains/cnpg/disaster-recovery.md)** - CNPG database DR procedures (separate system: Barman → S3)
- **[docs/domains/networking/topology.md](docs/domains/networking/topology.md)** - Network architecture details
- **[docs/domains/networking/policy.md](docs/domains/networking/policy.md)** - Cilium network policies
- **[docs/domains/argocd/argocd.md](docs/domains/argocd/argocd.md)** - ArgoCD documentation
- **[docs/domains/argocd/entrypoints.md](docs/domains/argocd/entrypoints.md)** - ArgoCD root entrypoints, waves, and AppSet/custom-entrypoint decisions
- **[docs/domains/storage/architecture-future.md](docs/domains/storage/architecture-future.md)** — **FUTURE IDEA (not implemented):** tiered storage (local CSI + kopiur restore-based DR default, Longhorn for availability-critical apps). Do not act on it now.
- **kopiur is the backup system (since 2026-06-27):** 22 PVCs across 18 namespaces on the `kopiur-backup` component (count verified 2026-07-01; gitea-postgres-data pending as #23); restore-before-bind proven by the karakeep full-namespace DR drill (2026-06-27). pvc-plumber + VolSync removed. PostHog, Redis, and `project-nomad/nomad-storage` are backup-exempt; swarmui is unused/exempt; CNPG stays native Barman/S3.
- **Database direction (since 2026-07-09):** new databases default to **plain Postgres + kopiur** (reference: `my-apps/development/gitea/postgres/`); the four CNPG databases migrate one at a time per `docs/domains/cnpg/plain-postgres-migration.md`. Crunchy PGO removed (was idle). ALL CNPG rules in this file stay in force until that doc's retirement checklist is fully ticked — do not relax them early.

## Mink capture

Keep Mink updated during substantive work. Mink hooks may track session activity automatically, but durable project knowledge still needs explicit capture with `mink note` or the `/mink:note` skill.

Capture decisions that change architecture or operations, verified bug root causes, live-system gotchas, reusable patterns, and future-operator context. Do not capture routine edits, raw command output, or unverified hypotheses.

Use `mink note --project talos-argocd-proxmox --category resources` for durable runbooks/gotchas/patterns and `--category projects` for active decisions or followups. Mention saved Mink note paths in the final response.
