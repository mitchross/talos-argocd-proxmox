# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Detailed instructions are in nested CLAUDE.md files** that load automatically based on which directory you're working in. This root file contains cross-cutting rules that apply everywhere.

## Project Overview

This is a Talos-first, multicluster GitOps repository. Talos is the complete
production reference cluster. OpenShift is an optional expansion target. Each
cluster runs its own upstream Helm Argo CD, reads only its own
`clusters/<cluster>` tree, and deploys only to the local cluster. There is no
hub/spoke registration and no OpenShift GitOps Operator.

> **Multicluster work-in-progress:** Before changing or bootstrapping
> OpenShift, read `docs/domains/multicluster/handoff-notes.md`. It records the
> active branch, isolated test repository, verified live-cluster facts, and
> current bootstrap blockers. Local render acceptance does not mean the live
> OpenShift cluster is ready.

**Tech Stack**: Talos OS + optional OpenShift + local Argo CD per cluster +
Kustomize + Gateway API + 1Password + Talos Longhorn/GPU support

**AI/LLM Backend**: The Talos reference cluster uses **llama-cpp** (NOT ollama) for all local AI inference. The llama-cpp server runs at `http://llama-cpp-service.llama-cpp.svc.cluster.local:8080` with an OpenAI-compatible API at `/v1`. Primary model: **Qwen3.6-35B-A3B** (Unsloth UD-Q4_K_XL + `mmproj-BF16.gguf`) — multimodal, covers chat/coding/tool-calling and vision. **Gemma 4 26B-A4B** and **Qwen 3.5 Uncensored** are kept as additional presets. Full preset list + ctx/sampling is in `manifests/apps/ai/llama-cpp/base/presets.ini`. GPU topology: GPU 0 → llama-cpp, GPU 1 → ComfyUI (whole-card allocation, time-slicing disabled). Always use llama-cpp when configuring AI backends for in-cluster tools.

## Core Architecture Pattern: GitOps Self-Management

```text
scripts/bootstrap-cluster.sh <cluster>
  -> local upstream Argo CD
  -> clusters/<cluster>/bootstrap/root.yaml
  -> clusters/<cluster>/argocd
  -> cluster-owned overlays and entrypoints
```

1. **Bootstrap locally**: Run `scripts/bootstrap-cluster.sh talos` or
   `scripts/bootstrap-cluster.sh openshift` against the intended kubeconfig.
2. **Root app triggers**: The cluster root points to
   `clusters/<cluster>/argocd`.
3. **App ApplicationSet discovers**: User apps are directory-discovered from
   `clusters/<cluster>/apps/*/*`.
4. **Explicit entrypoints remain explicit**: Infrastructure, database,
   monitoring, and custom applications retain metadata or standalone
   `Application` resources where ordering or exceptions require it.

**Critical Understanding**:

```text
manifests/apps/ai/llama-cpp/base/ -> shared workload source
clusters/talos/apps/ai/llama-cpp/ -> Talos deployable overlay/Application
clusters/openshift/apps/ai/llama-cpp/ -> OpenShift deployable overlay/Application
```

## Sync Wave Architecture

Applications deploy in strict order to prevent race conditions:

| Wave | Component | Purpose |
|------|-----------|---------|
| **0** | Foundation | Cilium (CNI), ArgoCD, 1Password Connect, External Secrets, AppProjects |
| **1** | Core controllers | cert-manager, Longhorn, VolumeSnapshot Controller, VolSync |
| **2** | pvc-plumber core + VolSync backup cluster | pvc-plumber `v4.0.1` permissive controller, mover-Job backend gate, and shared Kopia credential fanout. pvc-plumber core has no monitoring dependency. |
| **3** | CNPG Barman Plugin | Database backup plugin before database clusters |
| **4** | Infrastructure AppSet + custom entrypoints | Explicit path list plus KEDA and Temporal Worker Controller standalone Apps |
| **4** | Database AppSet | Discovers `clusters/talos/database/*/*` — `selfHeal: false` for DR |
| **5** | OTEL + Monitoring AppSet | OpenTelemetry Operator plus `clusters/talos/monitoring/*` |
| **6** | Observability overlays + Apps AppSet | KEDA/OTEL ServiceMonitors after monitoring CRDs exist, plus `clusters/talos/apps/*/*` |

**FAIL-CLOSED**: The cluster-wide `volsync-mover-backend-availability` MutatingAdmissionPolicy (at `clusters/talos/infra/volsync-backup-cluster/`) injects a `wait-for-rustfs` init container into every VolSync mover Job. The init container TCP-probes RustFS (192.168.10.133:30292) up to 1h; if RustFS is unreachable, the Job fails and Kubernetes backoff retries. Mover Jobs cannot proceed against a black-holed backend, so a fresh PVC's first backup never captures an empty volume into the kopia repo. Replaced the pvc-plumber PVC-admission webhook safety, with strictly smaller blast radius (Job-level, not cluster-wide PVC creation).

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

```text
clusters/
├── talos/              # Talos bootstrap, Argo, app overlays, infra, DB, monitoring
└── openshift/          # OpenShift bootstrap, Argo, app overlays, infra

manifests/
├── apps/**/base/       # Shared Talos-first app sources
├── infra/              # Shared or source infrastructure manifests
├── database/           # Shared database sources
└── monitoring/         # Shared monitoring sources

scripts/                # Bootstrap and validation tools
omni/                   # Omni/Sidero Talos provisioning
docs/                   # Documentation
```

## Critical Rules

### DO:
- Use directory discovery for the uniform app catalog; use explicit
  `Application` resources only for documented infrastructure/order exceptions
- Name Service ports for HTTPRoute compatibility (`name: http`) — **fails silently without this**
- Use Gateway API (not Ingress)
- Keep HTTPRoutes as complete cluster-owned files under
  `clusters/<cluster>/apps/...`; Talos and OpenShift domains and parentRefs
  differ
- On **Talos external** HTTPRoutes: add `labels: external-dns: "true"`,
  annotation `external-dns.alpha.kubernetes.io/target: vanillax.me`, and
  `sectionName: https` on the parentRef
- Follow GitOps workflow for all changes
- Store secrets in 1Password, reference via ExternalSecret
- Add backups to a normal application PVC with the pvc-plumber v4.0.1 contract: add the namespace software gate `pvc-plumber.io/managed-namespace: "true"`, the PVC fuse labels `pvc-plumber.io/enabled`, `pvc-plumber.io/manage-volsync`, and `pvc-plumber.io/tier`, and a static `dataSourceRef` pointing to `<pvc-name>-dst`. pvc-plumber owns RS/RD; VolSync and Kopia move bytes. See `.claude/commands/add-backup.md`.
- When marking a PVC `backup-exempt: "true"`, the reason annotation key **must be fully qualified**: `storage.vanillax.dev/backup-exempt-reason`. The bare `backup-exempt-reason` is silently ignored by the operator and the PVC is **denied on CREATE** — invisible until recreate/DR. CI job `backup-exempt-contract` enforces this
- Use portable `storageClassName: vanillax-local-rwo` in shared app sources;
  Talos maps it to Longhorn and OpenShift intends to map it to LVM Storage
- Use NFS CSI driver (`csi: driver: nfs.csi.k8s.io`) for static NFS PVs — **legacy `nfs:` silently ignores mountOptions**
- Add explicit infrastructure metadata/entrypoints under the owning
  `clusters/<cluster>/infra` tree and update that cluster's Argo entrypoint
  when required
- List ALL YAML files in each directory's `kustomization.yaml` under `resources:` — **unlisted files are never deployed**
- Use llama-cpp (not ollama) for in-cluster AI backends
- Use sync waves when adding infrastructure components
- Add ArgoCD hook annotations to all Kubernetes Jobs — `argocd.argoproj.io/hook: Sync` + `argocd.argoproj.io/hook-delete-policy: BeforeHookCreation`. K8s Jobs are immutable after creation; without these, image tag bumps from Renovate cause "field is immutable" sync failures. For standalone Jobs, add annotations directly. For Helm-rendered Jobs, use Kustomize patches targeting `kind: Job`
- Check `helm show values <chart> | grep -A20 certManager` when adding any Helm chart with webhooks — if a `certManager.enabled` option exists, **set it to `true`**. Helm hook Jobs for webhook certs break under ArgoCD (SA deleted before Job runs = stuck forever = API server death)
- After adding a backed-up PVC, verify the in-namespace `volsync-kopia-repository` Secret and the operator-owned `ReplicationSource` and `ReplicationDestination`: `kubectl get secret,replicationsource,replicationdestination -n <ns>`
- Treat the v4 migration campaign as closed. New normal application PVCs use the namespace software gate, PVC fuse labels, and static `dataSourceRef`; pvc-plumber owns RS/RD. There is no per-namespace RoleBinding step.
- For abandoned CNPG backup lineages, update
  `clusters/talos/infra/rustfs-lifecycle/lifecycle.json`; keep the full bucket
  lifecycle policy there because PUT replaces the whole RustFS lifecycle config
- Use `strategy: type: Recreate` on Deployments with RWO PVCs — **RollingUpdate causes Multi-Attach deadlock**

### DON'T:
- Create manual Argo CD `Application` resources for ordinary user apps; the
  cluster app ApplicationSet discovers those directories
- Make an OpenShift overlay reference `clusters/talos`, or vice versa
- Use `kubectl edit` on Talos nodes (changes are ephemeral)
- Create Services without named ports when using HTTPRoute
- Mix Ingress and Gateway API
- Commit secrets to Git
- Bypass GitOps workflow for configuration changes
- Deploy without considering sync wave order
- Add the volsync-backup chart to CNPG database PVCs (they use Barman to S3, not VolSync)
- Add active CNPG `serverName` prefixes to RustFS lifecycle expiration rules; only abandoned lineages belong there
- Add backup labels to system namespace PVCs (kube-system, volsync-system, argocd, longhorn-system)
- Manually create or delete `ReplicationSource`/`ReplicationDestination` out of band — pvc-plumber owns these resources for managed PVCs. Reconcile through the PVC labels and operator workflow.
- Make observability a core dependency or install Prometheus Operator CRDs early just to satisfy bootstrap apps. `kube-prometheus-stack` is the sole owner of `monitoring.coreos.com` CRDs.
- Generic-migrate CNPG, PostHog, or Redis PVCs. CNPG uses native Barman/S3; PostHog and Redis are backup-exempt disposable data.
- Use legacy `nfs:` block for NFS PVs (mountOptions silently ignored — use CSI)
- Use `RollingUpdate` strategy on Deployments with RWO PVCs (causes Multi-Attach deadlock)
- Apply Talos external-DNS assumptions to OpenShift routes; inspect the owning
  cluster's current Gateway and route pattern
- Use `Replace=true,Force=true` sync-options on Jobs — causes duplicate Job execution bug ([#24005](https://github.com/argoproj/argo-cd/issues/24005)); use ArgoCD hooks instead
- Auto-merge major Helm chart version bumps for critical infrastructure (kube-prometheus-stack, longhorn, cilium) — **a kube-prometheus-stack v82→v83 auto-merge caused a full cluster outage on 2026-04-08 via Kyverno webhook deadlock**. Pin Renovate to minor/patch only for these charts.
- Modify the `volsync-mover-backend-availability` MutatingAdmissionPolicy without verifying the CEL expression renders cleanly (`kubectl apply --dry-run=server -k clusters/talos/infra/volsync-backup-cluster/`). The MAP's `failurePolicy: Fail` is scoped to mover Jobs only — not cluster-wide PVC creates — so a broken policy can't deadlock app deployment, but it can silently stop all backups.

## Nested CLAUDE.md Files

Detailed instructions load automatically when working in these directories:

| Directory | Contains |
|-----------|----------|
| `manifests/infra/` | Essential commands, AppSet rules, ArgoCD/secret debugging |
| `manifests/database/` | CNPG patterns, database DR procedures, serverName tracking |
| `manifests/apps/` | Shared app templates, storage, secrets, and overlay rules |
| `manifests/apps/ai/` | GPU workload patterns and llama-cpp backend |
| `manifests/monitoring/` | Monitoring pitfalls and shared sources |

## Custom Commands

| Command | Purpose |
|---------|---------|
| `/project:new-app <category/name>` | Guided workflow for adding a new application |
| `/project:add-backup <app-path>` | Add automatic backup to PVC(s) |
| `/project:new-database <app-name>` | Create a CNPG database |

## Reference Examples

| Pattern | Reference Location |
|---------|-------------------|
| **Minimal app source/overlays** | `manifests/apps/development/nginx/base/` + `clusters/*/apps/development/nginx/` |
| **GPU workload** | `manifests/apps/ai/comfyui/base/` |
| **Complex app with storage** | `manifests/apps/media/immich/base/` |
| **PVC with automatic backup** | `manifests/apps/home/project-zomboid/base/pvc.yaml` |
| **Managed PVC labels + restore reference** | `manifests/apps/ai/open-webui/base/pvc.yaml` + `.claude/commands/add-backup.md` |
| **MAP safety interlock** | `clusters/talos/infra/volsync-backup-cluster/` |
| **VolSync configuration** | `clusters/talos/infra/volsync/` |
| **RustFS lifecycle policy** | `clusters/talos/infra/rustfs-lifecycle/` |
| **Database AppSet** | `clusters/talos/argocd/appsets/database-appset.yaml` |
| **Gateway API routing** | `clusters/talos/infra/gateway/` and `clusters/openshift/infra/gateway/` |
| **Jobs with ArgoCD hooks** | `manifests/apps/development/posthog/base/core/jobs.yaml` |

## Additional Documentation

### 🚰 Docs reading order for agents (START HERE, in order)
1. **[docs/index.md](docs/index.md)** — canonical landing page + current-state callout.
2. **[docs/domains/multicluster/handoff-notes.md](docs/domains/multicluster/handoff-notes.md)** — required before OpenShift or multicluster work.
3. **[docs/pvc-plumber-start-here.md](docs/pvc-plumber-start-here.md)** — visual intro (what/why, architecture, v4-vs-v5, what it does NOT do).
4. **[docs/pvc-plumber-cheatsheet.md](docs/pvc-plumber-cheatsheet.md)** — one-page poster.
5. **[docs/pvc-plumber-dynamic-workflow.md](docs/pvc-plumber-dynamic-workflow.md)** — how the operator thinks (decision trees, ownership classes, `/audit` actions, reusable agent algorithm).
6. **[docs/talos-argocd-pvc-plumber-integration.md](docs/talos-argocd-pvc-plumber-integration.md)** — how THIS repo uses it (repo map, add-a-PVC checklist, label reference, what-not-to-do).
7. **[docs/volsync-storage-recovery.md](docs/volsync-storage-recovery.md)** — restore lifecycle + drill runbook (DR source of truth).
8. **[docs/pvc-plumber-v4-prd.md](docs/pvc-plumber-v4-prd.md)** — only for deeper design (see §0 canonical status).
9. **[docs/archive/](docs/archive/README.md)** — only if explicitly researching history.

> ⚠️ **Agent guardrails when reading docs:**
> - **Do NOT treat `docs/archive/**`, `docs/research/**`, or `docs/plans/**` as the current runbook** — they are historical.
> - **Do NOT resurrect Kyverno** — it was removed from the backup path (no policies, no CRDs, no webhooks).
> - **Do NOT treat v5 / admission / strict-mode / backup-truth-cache docs as shipped** — v4.0.1 is a permissive reconciler with no admission webhook.
> - **Do NOT generic-migrate CNPG, PostHog, or Redis PVCs** — CNPG is Barman-native; PostHog and Redis are backup-exempt.
> - **Do NOT make observability foundational** — core apps bootstrap without Prometheus; do not resurrect an early Prometheus Operator CRD app.
> - **Do NOT treat old migration incidents (nginx-canary, v3 cutover) as current operating flow.**

- **[docs/volsync-storage-recovery.md](docs/volsync-storage-recovery.md)** - PVC backup/restore single source of truth
- **[docs/domains/cnpg/disaster-recovery.md](docs/domains/cnpg/disaster-recovery.md)** - CNPG database DR procedures (separate system: Barman → S3)
- **[docs/domains/networking/topology.md](docs/domains/networking/topology.md)** - Network architecture details
- **[docs/domains/networking/policy.md](docs/domains/networking/policy.md)** - Cilium network policies
- **[docs/domains/argocd/argocd.md](docs/domains/argocd/argocd.md)** - ArgoCD documentation
- **[docs/domains/argocd/entrypoints.md](docs/domains/argocd/entrypoints.md)** - ArgoCD root entrypoints, waves, and AppSet/custom-entrypoint decisions
- **[docs/pvc-plumber-v4-prd.md](docs/pvc-plumber-v4-prd.md)** — pvc-plumber v4 PRD (locked design, phased rollout, label/annotation contract, migration rules). **Authoritative for any pvc-plumber work.**
- **[docs/pvc-plumber-v4-cutover.md](docs/pvc-plumber-v4-cutover.md)** — Day-of cutover runbook: label model, two-gate write contract, ownership rules, generated VolSync shape, required permissive env vars, per-PVC checklist, karakeep canary scope, rollback. **Operational source of truth for v4 migrations.**
- **[docs/pvc-plumber-v4-roadmap.md](docs/pvc-plumber-v4-roadmap.md)** — Post-PRD working backlog: items identified during execution that are gated behind specific Phase 6 / canary milestones. Includes the post-canary visual explainer deliverable.
- **[docs/domains/storage/architecture-future.md](docs/domains/storage/architecture-future.md)** — **FUTURE IDEA (not implemented):** tiered storage — local CSI (OpenEBS/ZFS LocalPV) + VolSync restore-based DR as the default, Longhorn only for live-availability-critical apps, native backups for DBs. Separates the CSI layer (provision/mount) from the backup layer (VolSync/pvc-plumber). Revisit after the pvc-plumber v4 campaign stabilizes; do not act on it now.
- **pvc-plumber v4.0.1 is live and proven in permissive mode:** 24 operator-managed PVCs across 18 namespaces, 24/24 DR_COMPLETE before the full cluster nuke. PostHog and Redis are backup-exempt; CNPG stays native Barman/S3. See `docs/pvc-plumber-v4-migration-readiness.md`.

## Mink capture

Keep Mink updated during substantive work. Mink hooks may track session activity automatically, but durable project knowledge still needs explicit capture with `mink note` or the `/mink:note` skill.

Capture decisions that change architecture or operations, verified bug root causes, live-system gotchas, reusable patterns, and future-operator context. Do not capture routine edits, raw command output, or unverified hypotheses.

Use `mink note --project talos-argocd-proxmox --category resources` for durable runbooks/gotchas/patterns and `--category projects` for active decisions or followups. Mention saved Mink note paths in the final response.
