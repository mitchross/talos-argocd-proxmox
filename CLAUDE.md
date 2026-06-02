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
| **2** | VolSync MAP + ClusterES | `MutatingAdmissionPolicy/volsync-mover-backend-availability` (mover-Job backend gate, fail-closed scoped to Jobs only) + `ClusterExternalSecret/volsync-kopia-repository` (per-namespace credential fanout). **pvc-plumber v4 (`v4.0.1`, permissive) is deployed here at Wave 2 — see `docs/pvc-plumber-v4-migration-readiness.md` for live status and `docs/pvc-plumber-v4-prd.md` for design. v4.0.1 adds the namespace software write-gate (`pvc-plumber.io/managed-namespace: "true"`) backed by a single cluster-wide `ClusterRoleBinding pvc-plumber:volsync-writer` (no per-namespace RoleBindings).** |
| **3** | CNPG Barman Plugin | Database backup plugin before database clusters |
| **4** | Infrastructure AppSet + custom entrypoints | Explicit path list plus KEDA and Temporal Worker Controller standalone Apps |
| **4** | Database AppSet | Discovers `infrastructure/database/*/*` — `selfHeal: false` for DR |
| **5** | OTEL + Monitoring AppSet | OpenTelemetry Operator plus `monitoring/*` |
| **6** | My-Apps AppSet | Discovers `my-apps/*/*` |

**FAIL-CLOSED**: The cluster-wide `volsync-mover-backend-availability` MutatingAdmissionPolicy (at `infrastructure/storage/volsync-backup-cluster/`) injects a `wait-for-rustfs` init container into every VolSync mover Job. The init container TCP-probes RustFS (192.168.10.133:30292) up to 1h; if RustFS is unreachable, the Job fails and Kubernetes backoff retries. Mover Jobs cannot proceed against a black-holed backend, so a fresh PVC's first backup never captures an empty volume into the kopia repo. Replaced the pvc-plumber PVC-admission webhook safety, with strictly smaller blast radius (Job-level, not cluster-wide PVC creation).

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
- Add backups to a new PVC by **inlining `ReplicationSource` + `ReplicationDestination`** as additional documents in the app's `pvc.yaml`. The PVC carries `restore-policy: "strict"` (or `"best-effort"`), `argocd.argoproj.io/compare-options: ServerSideDiff=false`, and a static `dataSourceRef` pointing at `ReplicationDestination/<pvc-name>-dst`. The app's namespace must carry `volsync.backube/privileged-movers: "true"` so `ClusterExternalSecret/volsync-kopia-repository` materializes the shared kopia Secret there. Canonical template: `my-apps/CLAUDE.md`. Reference example: `my-apps/ai/open-webui/pvc.yaml`. Workflow: `.claude/commands/add-backup.md`. **No chart, no operator, no `helmCharts:` entry.** The legacy `backup: "hourly|daily"` label is dead. pvc-plumber v4 (`v4.0.1`, image `4.0.1@sha256:721d770…`) is **live in permissive mode** and **24 PVCs across 18 namespaces** are operator-managed (`managed-by=pvc-plumber`) with verified backups: `nginx-example/storage`, `homepage-dashboard/config`, `karakeep/{data-pvc,meilisearch-pvc}`, `fizzy/data`, `frigate/frigate-config`, `project-nomad/{flatnotes-data,qdrant-data,nomad-storage,mysql-data}`, `tubesync/config-pvc`, `copyparty/copyparty-data`, `jellyfin/config`, `open-webui/storage`, `perplexica/perplexica-data`, `project-zomboid/zomboid-data`, `swarmui/{swarmui-data,swarmui-output}`, `n8n/data`, `home-assistant/config`, `gitea/gitea-shared-storage`, `paperless-ngx/{data,media}`, `immich/library` (SAVE_FOR_END migrations 2026-05-31; n8n/gitea movers normalized 1000→568, validated; gitea is the Helm `extraDeploy` special case; gitea/HA/posthog DBs stay native CNPG/Barman — never generic-migrated). **paperless-ngx/{data,media} and immich/library were reset EMPTY (disposable data, user-authorized) and recreated with NO `dataSourceRef`. UPDATE 2026-05-31: ALL THREE later had their `dataSourceRef → <pvc>-dst` ADDED during restore drills and validated byte-identically (sha256 match): `paperless-ngx/data` (`b7052c30`), `paperless-ngx/media` (`6d5c9051`), `immich/library` (`ecd6009e`). **DR-completeness campaign COMPLETE — 24/24 operator-managed PVCs are DR_COMPLETE (Git `dataSourceRef` → matching managed RD).** immich's CNPG DB still references pre-reset assets so the UI shows broken/missing assets (pre-existing/accepted — the library restore proves the CURRENT working set recreates, it does NOT fix the prior DB-to-asset mismatch; immich originals remain on exempt NFS `nfs-photos`, untouched; CNPG stays native). A PVC with no `dataSourceRef` recreates EMPTY (no restore) — to make any managed PVC DR-complete, Git must carry `dataSourceRef → <pvc>-dst`. See `docs/volsync-storage-recovery.md` "Restore drill runbook" for the stale-render-race mitigation (after adding a dsr: hard-refresh + wait until `application.status.sync.revision == dsr commit` before deleting the PVC; be ready for a double-recreate) and the scale-back-up stale-cache gotcha.** (Several migrated after an immutable-`dataSourceRef` repair / Option-R reset; some old pre-repair PVs are retained as rollback — do not delete until approved. **Currently-present retained rollback PVs (verified 2026-05-31 fleet audit, 7):** Karakeep `pvc-4cb90a74`, home-assistant `pvc-52fd99ba`, gitea `pvc-5f52c07b`, swarmui-data `pvc-47c2ae80`, copyparty `pvc-a157ad5f`, open-webui `pvc-be2c62e1`, project-zomboid `pvc-d71b929e`. The earlier-documented tubesync `pvc-3f4378d9` and n8n `pvc-1608bca4` rollback PVs are **no longer present** — reclaimed/removed before the audit, not by it; their apps are healthy and live PVCs operator-backed-up.) For all other (not-yet-migrated) PVCs, inline RS/RD in the app's `pvc.yaml` remains the correct pattern. **RBAC is no longer a per-namespace gate:** v4.0.1 uses a single cluster-wide `ClusterRoleBinding pvc-plumber:volsync-writer` (SA `pvc-plumber/pvc-plumber`, RS/RD verbs) that already covers every namespace — there are no per-namespace `RoleBinding`s and none are needed. Per-PVC migration to operator ownership follows the proven order in `docs/pvc-plumber-v4-migration-readiness.md`: **add namespace gate label `pvc-plumber.io/managed-namespace: "true"` + PVC fuse labels (`pvc-plumber.io/enabled`, `manage-volsync`, `tier`) → remove inline RS/RD → operator recreates managed RS/RD → verify backup.**
- When marking a PVC `backup-exempt: "true"`, the reason annotation key **must be fully qualified**: `storage.vanillax.dev/backup-exempt-reason`. The bare `backup-exempt-reason` is silently ignored by the operator and the PVC is **denied on CREATE** — invisible until recreate/DR. CI job `backup-exempt-contract` enforces this
- Use `storageClassName: longhorn` for PVCs that need backups (volumesnapshot required)
- Use NFS CSI driver (`csi: driver: nfs.csi.k8s.io`) for static NFS PVs — **legacy `nfs:` silently ignores mountOptions**
- Add new infrastructure component paths to `infrastructure/controllers/argocd/apps/appsets/infrastructure-appset.yaml` explicitly (not glob-discovered)
- List ALL YAML files in each directory's `kustomization.yaml` under `resources:` — **unlisted files are never deployed**
- Use llama-cpp (not ollama) for in-cluster AI backends
- Use sync waves when adding infrastructure components
- Add ArgoCD hook annotations to all Kubernetes Jobs — `argocd.argoproj.io/hook: Sync` + `argocd.argoproj.io/hook-delete-policy: BeforeHookCreation`. K8s Jobs are immutable after creation; without these, image tag bumps from Renovate cause "field is immutable" sync failures. For standalone Jobs, add annotations directly. For Helm-rendered Jobs, use Kustomize patches targeting `kind: Job`
- Check `helm show values <chart> | grep -A20 certManager` when adding any Helm chart with webhooks — if a `certManager.enabled` option exists, **set it to `true`**. Helm hook Jobs for webhook certs break under ArgoCD (SA deleted before Job runs = stuck forever = API server death)
- After adding a backed-up PVC, verify the in-namespace `volsync-kopia-repository` Secret (materialized by `ClusterExternalSecret`), the inline `ReplicationSource`, and the inline `ReplicationDestination` all exist: `kubectl get secret,replicationsource,replicationdestination -n <ns>`
- Before removing inline `ReplicationSource`/`ReplicationDestination` from any PVC's `pvc.yaml` as part of v4 migration, the operator's write permission is already satisfied cluster-wide by `ClusterRoleBinding pvc-plumber:volsync-writer` (`kubectl get clusterrolebinding pvc-plumber:volsync-writer`) — **no per-namespace RoleBinding is required** (the old per-namespace `RoleBinding` model is retired). The real per-namespace gate is the **software write-gate**: the namespace must carry `pvc-plumber.io/managed-namespace: "true"` and the PVC must carry the fuse labels, or the operator will skip it (`skipped-namespace-not-managed` / `skipped-not-opted-in` in `/audit`). Land the namespace label + PVC fuse labels first; remove inline RS/RD last. Reversing strands the PVC without a backup chain because Argo prunes the inline RS/RD before the operator is allowed to recreate them. Full preflight checklist + managed-namespace contract in `docs/pvc-plumber-v4-cutover.md`. Historical driving incident (under the old RBAC model): `nginx-example/storage`, 2026-05-27.
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
- Add the volsync-backup chart to CNPG database PVCs (they use Barman to S3, not VolSync)
- Add active CNPG `serverName` prefixes to RustFS lifecycle expiration rules; only abandoned lineages belong there
- Add backup labels to system namespace PVCs (kube-system, volsync-system, argocd, longhorn-system)
- Manually create or delete `ReplicationSource`/`ReplicationDestination` out of band — these resources are inlined with their PVC in Git and Argo-managed. Any drift must be reconciled in the app's `pvc.yaml`, not via `kubectl edit`. (Exception during pvc-plumber v4 rollout: orphan RS/RD adopted by the operator — those will carry `app.kubernetes.io/managed-by: pvc-plumber` and live outside Git by design.)
- Use legacy `nfs:` block for NFS PVs (mountOptions silently ignored — use CSI)
- Use `RollingUpdate` strategy on Deployments with RWO PVCs (causes Multi-Attach deadlock)
- Create external HTTPRoutes without the three required pieces: `external-dns: "true"` label, `external-dns.alpha.kubernetes.io/target: vanillax.me` annotation, and `sectionName: https` — **DNS won't be created and Cloudflare tunnel routing fails silently**
- Use `Replace=true,Force=true` sync-options on Jobs — causes duplicate Job execution bug ([#24005](https://github.com/argoproj/argo-cd/issues/24005)); use ArgoCD hooks instead
- Auto-merge major Helm chart version bumps for critical infrastructure (kube-prometheus-stack, longhorn, cilium) — **a kube-prometheus-stack v82→v83 auto-merge caused a full cluster outage on 2026-04-08 via Kyverno webhook deadlock**. Pin Renovate to minor/patch only for these charts.
- Modify the `volsync-mover-backend-availability` MutatingAdmissionPolicy without verifying the CEL expression renders cleanly (`kubectl apply --dry-run=server -k infrastructure/storage/volsync-backup-cluster/`). The MAP's `failurePolicy: Fail` is scoped to mover Jobs only — not cluster-wide PVC creates — so a broken policy can't deadlock app deployment, but it can silently stop all backups.

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
| **Inline RS/RD per PVC (current pattern)** | `my-apps/ai/open-webui/pvc.yaml` + `my-apps/CLAUDE.md` |
| **MAP safety interlock (cluster-wide)** | `infrastructure/storage/volsync-backup-cluster/` |
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

### 🚰 Docs reading order for agents (START HERE, in order)
1. **[docs/index.md](docs/index.md)** — canonical landing page + current-state callout.
2. **[docs/pvc-plumber-start-here.md](docs/pvc-plumber-start-here.md)** — visual intro (what/why, architecture, v4-vs-v5, what it does NOT do).
3. **[docs/pvc-plumber-cheatsheet.md](docs/pvc-plumber-cheatsheet.md)** — one-page poster.
4. **[docs/pvc-plumber-dynamic-workflow.md](docs/pvc-plumber-dynamic-workflow.md)** — how the operator thinks (decision trees, ownership classes, `/audit` actions, reusable agent algorithm).
5. **[docs/talos-argocd-pvc-plumber-integration.md](docs/talos-argocd-pvc-plumber-integration.md)** — how THIS repo uses it (repo map, add-a-PVC checklist, label reference, what-not-to-do).
6. **[docs/volsync-storage-recovery.md](docs/volsync-storage-recovery.md)** — restore lifecycle + drill runbook (DR source of truth).
7. **[docs/pvc-plumber-v4-prd.md](docs/pvc-plumber-v4-prd.md)** — only for deeper design (see §0 canonical status).
8. **[docs/archive/](docs/archive/README.md)** — only if explicitly researching history.

> ⚠️ **Agent guardrails when reading docs:**
> - **Do NOT treat `docs/archive/**`, `docs/research/**`, or `docs/plans/**` as the current runbook** — they are historical.
> - **Do NOT resurrect Kyverno** — it was removed from the backup path (no policies, no CRDs, no webhooks).
> - **Do NOT treat v5 / admission / strict-mode / backup-truth-cache docs as shipped** — v4.0.1 is a permissive reconciler with no admission webhook.
> - **Do NOT generic-migrate CNPG or PostHog PVCs** — CNPG is Barman-native; PostHog is backup-exempt.
> - **Do NOT treat old migration incidents (nginx-canary, v3 cutover) as current operating flow.**

- **[docs/volsync-storage-recovery.md](docs/volsync-storage-recovery.md)** - PVC backup/restore single source of truth (architecture, sync waves, admission flow, scenarios, troubleshooting)
- **[docs/domains/cnpg/disaster-recovery.md](docs/domains/cnpg/disaster-recovery.md)** - CNPG database DR procedures (separate system: Barman → S3)
- **[docs/domains/networking/topology.md](docs/domains/networking/topology.md)** - Network architecture details
- **[docs/domains/networking/policy.md](docs/domains/networking/policy.md)** - Cilium network policies
- **[docs/domains/argocd/argocd.md](docs/domains/argocd/argocd.md)** - ArgoCD documentation
- **[docs/domains/argocd/entrypoints.md](docs/domains/argocd/entrypoints.md)** - ArgoCD root entrypoints, waves, and AppSet/custom-entrypoint decisions
- **[docs/pvc-plumber-v4-prd.md](docs/pvc-plumber-v4-prd.md)** — pvc-plumber v4 PRD (locked design, phased rollout, label/annotation contract, migration rules). **Authoritative for any pvc-plumber work.**
- **[docs/pvc-plumber-v4-cutover.md](docs/pvc-plumber-v4-cutover.md)** — Day-of cutover runbook: label model, two-gate write contract, ownership rules, generated VolSync shape, required permissive env vars, per-PVC checklist, karakeep canary scope, rollback. **Operational source of truth for v4 migrations.**
- **[docs/pvc-plumber-v4-roadmap.md](docs/pvc-plumber-v4-roadmap.md)** — Post-PRD working backlog: items identified during execution that are gated behind specific Phase 6 / canary milestones. Includes the post-canary visual explainer deliverable.
- **[docs/domains/storage/architecture-future.md](docs/domains/storage/architecture-future.md)** — **FUTURE IDEA (not implemented):** tiered storage — local CSI (OpenEBS/ZFS LocalPV) + VolSync restore-based DR as the default, Longhorn only for live-availability-critical apps, native backups for DBs. Separates the CSI layer (provision/mount) from the backup layer (VolSync/pvc-plumber). Revisit after the pvc-plumber v4 campaign stabilizes; do not act on it now.
- **pvc-plumber was decommissioned 2026-05-21; v4 re-adopted and now live (`v4.0.1`, permissive mode; 24 PVCs operator-managed across 18 namespaces — SAVE_FOR_END migrations n8n/home-assistant/gitea done; paperless-ngx/{data,media} + immich/library reset-EMPTY-then-migrated 2026-05-31; posthog backup-exempt; redis-instance/redis-master-0 **backup-exempt 2026-06-01** (was deferred — paperless Celery broker, disposable; inline RS/RD removed, dsr removed, ComparisonError cleared); CNPG never-migrate).** Current migration status + remaining SAVE_FOR_END classification: `docs/pvc-plumber-v4-migration-readiness.md`. Historical decommission analysis under `docs/research/pvc-backup-simplification/`. `scripts/emergency-webhook-cleanup.sh` retained as historical reference for any future `failurePolicy: Fail` webhook deadlock pattern.

## Mink capture

Keep Mink updated during substantive work. Mink hooks may track session activity automatically, but durable project knowledge still needs explicit capture with `mink note` or the `/mink:note` skill.

Capture decisions that change architecture or operations, verified bug root causes, live-system gotchas, reusable patterns, and future-operator context. Do not capture routine edits, raw command output, or unverified hypotheses.

Use `mink note --project talos-argocd-proxmox --category resources` for durable runbooks/gotchas/patterns and `--category projects` for active decisions or followups. Mention saved Mink note paths in the final response.
