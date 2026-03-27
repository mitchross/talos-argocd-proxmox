# ArgoCD & GitOps Architecture

This document details the "App of Apps" GitOps architecture used in this cluster, focusing on the **Sync Wave** strategy, **Diff Strategy**, and **Health Check Customizations** that enable a fully self-managing cluster.

## The "App of Apps" Pattern

We use a hierarchical "App of Apps" pattern to manage the entire cluster state.

```
                    ┌─────────────────┐
                    │  Root Application│  ← Only manual step (bootstrap)
                    │  root.yaml       │
                    └────────┬────────┘
                             │ manages
                ┌────────────┼────────────────┐
                ▼            ▼                ▼
        ┌──────────┐  ┌───────────┐   ┌──────────────┐
        │Standalone│  │Application│   │  AppProject   │
        │   Apps   │  │   Sets    │   │  Definitions  │
        └────┬─────┘  └─────┬─────┘   └──────────────┘
             │              │ auto-discovers directories
     ┌───────┼───────┐      │
     ▼       ▼       ▼      ▼
  cilium  longhorn kyverno  ┌──────────────────────────┐
  (wave0) (wave1) (wave3)   │ Generated Applications   │
                            │ cert-manager, gpu-op, ... │
                            └──────────────────────────┘
```

### The Root Application
The entry point is `infrastructure/controllers/argocd/root.yaml`. This application:
1. Points to `infrastructure/controllers/argocd/apps/`
2. Deploys the `ApplicationSet` definitions found there.
3. Is the *only* thing applied manually (during bootstrap).

### ApplicationSets
We use four ApplicationSets to categorize workloads:
1. **Infrastructure** (`infrastructure-appset.yaml`): Core system components (Cert-Manager, GPU operators, Gateway, etc.).
2. **Database** (`database-appset.yaml`): Database operators and instances via glob discovery (`infrastructure/database/*/*`). Uses `selfHeal: false` to preserve `skip-reconcile` annotations during DR.
3. **Monitoring** (`monitoring-appset.yaml`): Observability stack (Prometheus, Grafana).
4. **My Apps** (`my-apps-appset.yaml`): User workloads.

### Standalone Applications

Some components need **guaranteed ordering** that ApplicationSets cannot provide (AppSets report "healthy" immediately on creation). These are deployed as standalone `Application` resources with explicit sync waves:

| App | Wave | Why standalone? |
|-----|------|-----------------|
| `cilium` | 0 | CNI must exist before any pod |
| `argocd` | 0 | Self-management |
| `1password-connect` | 0 | Secret backend for all ExternalSecrets |
| `external-secrets` | 0 | CRDs needed by downstream apps |
| `longhorn` | 1 | Storage must exist before PVCs |
| `snapshot-controller` | 1 | VolumeSnapshot CRDs for backups |
| `volsync` | 1 | Backup/restore engine |
| `pvc-plumber` | 2 | Must be healthy before Kyverno calls its API |
| `kyverno` | 3 | Webhooks must register before app PVCs are created |
| `opentelemetry-operator` | 5 | Needs cert-manager (Wave 4) for webhook certificates |

## Sync Waves & Dependency Management

To solve the "chicken-and-egg" problem of bootstrapping a cluster (e.g., needing storage for apps, but networking for storage), we use **ArgoCD Sync Waves**.

### The Wave Strategy

```
 Wave 0        Wave 1         Wave 2        Wave 3       Wave 4          Wave 5           Wave 6
┌─────────┐  ┌───────────┐  ┌──────────┐  ┌─────────┐  ┌─────────────┐  ┌─────────────┐  ┌──────────┐
│ Cilium   │  │ Longhorn   │  │ PVC      │  │ Kyverno │  │ Infra AppSet│  │ OTEL Operator│  │ My Apps  │
│ ArgoCD   │→│ Snapshot   │→│ Plumber  │→│         │→│ DB AppSet   │→│ Mon. AppSet  │→│ AppSet   │
│ 1Pass    │  │ VolSync    │  │          │  │         │  │             │  │              │  │          │
│ ExtSec   │  │            │  │          │  │         │  │             │  │              │  │          │
└─────────┘  └───────────┘  └──────────┘  └─────────┘  └─────────────┘  └─────────────┘  └──────────┘
 Networking    Persistence    Backup gate   Policies     Core services    Observability    User apps
 + Secrets                                  + Webhooks   + Databases
```

| Wave | Phase | Components | Description |
|------|-------|------------|-------------|
| **0** | **Foundation** | `cilium`, `argocd`, `1password-connect`, `external-secrets`, `projects` | **Networking & Secrets**. The absolute minimum required for other pods to start and pull credentials. |
| **1** | **Storage** | `longhorn`, `snapshot-controller`, `volsync` | **Persistence**. Depends on Wave 0 for Pod-to-Pod communication and secrets. |
| **2** | **PVC Plumber** | `pvc-plumber` | **Backup checker**. Must be running before Kyverno policies in Wave 3 call its API. |
| **3** | **Kyverno** | `kyverno` | **Policy engine**. Standalone Application (not in AppSet) so webhooks register before any app PVCs are created. |
| **4** | **Infrastructure** | `cert-manager`, `gpu-operator`, `gateway`, etc. | **Core Services** via Infrastructure ApplicationSet (explicit path list). |
| **4** | **Database** | `cloudnative-pg/*/*` | **Databases** via Database ApplicationSet (glob discovery). Uses `selfHeal: false` for DR. |
| **5** | **OTEL + Monitoring** | `opentelemetry-operator`, `prometheus-stack`, `loki-stack` | **Observability**. OTEL is standalone (needs cert-manager from Wave 4). |
| **6** | **User** | `my-apps/*/*` | **Workloads** via My-Apps ApplicationSet (discovers `my-apps/*/*`). |

### How It Works
Each `Application` resource in `infrastructure/controllers/argocd/apps/` is annotated with a sync wave:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: cilium
  annotations:
    argocd.argoproj.io/sync-wave: "0"
```

ArgoCD processes these waves sequentially. **Wave 1 will NOT start until Wave 0 is healthy.**

## Health Check Customizations

Standard ArgoCD behavior is to mark a parent Application as "Healthy" as soon as the child Application resource is created, *even if the child app is still syncing or degraded*. This breaks the Sync Wave logic for App-of-Apps.

To fix this, we inject custom Lua health checks in `infrastructure/controllers/argocd/values.yaml`.

### The "Wait for Child" Script

```lua
resource.customizations.health.argoproj.io_Application: |
  hs = {}
  hs.status = "Progressing"
  hs.message = ""
  if obj.status ~= nil then
    if obj.status.health ~= nil then
      hs.status = obj.status.health.status
      if obj.status.health.message ~= nil then
        hs.message = obj.status.health.message
      end
    end
  end
  return hs
```

**What this does:**
1. It overrides the health assessment of `Application` resources.
2. It forces the parent (Root App) to report the *actual status* of the child Application.
3. If `cilium` (Wave 0) is "Progressing", the Root App sees it as "Progressing".
4. The Root App **pauses** processing Wave 1 until all Wave 0 apps report "Healthy".

### Additional Health Checks

| Resource | Purpose |
|----------|---------|
| `ClusterPolicy` | Waits for Kyverno's `Ready` condition before advancing past Wave 3 |
| `ReplicationSource` | Reports "Healthy" after first successful sync (prevents false "Progressing") |
| `ReplicationDestination` | Reports "Healthy" when `latestImage` is available for restore |

## Self-Management Loop

1. **Bootstrap**: You apply `root.yaml`.
2. **Adoption**: ArgoCD sees `cilium` defined in Git (Wave 0). It adopts the running Cilium instance.
3. **Expansion**: ArgoCD deploys `external-secrets` (Wave 0).
4. **Wait**: ArgoCD waits for Cilium and External Secrets to be green.
5. **Storage**: ArgoCD deploys `longhorn` (Wave 1).
6. **Completion**: The process continues until all waves are healthy.

This ensures a deterministic, reliable boot sequence every time.

## Server-Side Diff & Apply Strategy

This cluster uses **Server-Side Diff** paired with **Server-Side Apply**. These must be aligned — using one without the other causes silent sync failures.

### How Diff Strategies Work

```
                    Client-Side Diff (legacy)           Server-Side Diff (modern)
                    ─────────────────────────           ─────────────────────────
Git manifest ──────► ArgoCD compares locally  ──►       Git manifest ──────► K8s API dry-run apply ──►
                     against live resource               returns predicted result
                           │                                      │
                     String comparison                   Semantic comparison
                     (doesn't understand                 (understands quantities,
                      quantities, defaults,               defaults, field ownership,
                      field ownership)                    schema types)
                           │                                      │
                     "1000m" != "1" ← FALSE DIFF         "1000m" == "1" ← CORRECT
```

### Client-Side Diff (legacy, DO NOT USE with SSA)

ArgoCD downloads the live resource from the cluster, then compares it against the Git manifest **locally in the ArgoCD controller**. It's essentially doing `diff manifest.yaml live-resource.yaml` on its own.

**Problem**: ArgoCD doesn't know what Kubernetes would actually do with the manifest. Kubernetes adds defaults, mutating webhooks modify fields, and SSA has field ownership rules. ArgoCD is guessing — and sometimes guesses wrong (thinks it's "in-sync" when it's not).

### Server-Side Diff (modern, REQUIRED with SSA)

ArgoCD sends the Git manifest to the Kubernetes API as a **dry-run server-side apply** and gets back what the result *would* look like. Then it compares *that* against the live resource.

**Why it's better**: Kubernetes itself tells ArgoCD "here's what would change if you applied this" — accounting for defaults, field ownership, webhooks, everything. No guessing.

### What Server-Side Diff Does NOT Handle

Even with server-side diff enabled, some cases still require `ignoreDifferences`:

```
Server-Side Diff handles:                    Still needs ignoreDifferences:
───────────────────────                       ──────────────────────────────
 ✓ Resource quantity normalization             ✗ Mutation webhook fields (caBundle,
   (1000m vs "1", 1Gi vs 1073741824)             skipBackgroundRequests, etc.)
                                               ✗ StatefulSet volumeClaimTemplates
 ✓ .status fields (ArgoCD 3.0+                   apiVersion/kind stripping
   ignores all status by default)              ✗ CRD labels added by controllers
                                               ✗ PVC immutable fields (dataSourceRef,
 ✓ Server-side defaulting                        volumeName, storage)
   (fields K8s adds during apply)              ✗ Controller-managed annotations
```

**Why mutation webhooks are excluded**: By default, server-side diff strips mutation webhook changes from the dry-run result. There is an `IncludeMutationWebhook=true` option, but ArgoCD maintainers recommend against it — it causes any webhook-added field to show as OutOfSync unless you also have it in Git.

> "enabling that option means that any changes made by a mutating webhook will cause your app to be out of sync. That seems like generally undesirable behavior."
> — Michael Crenshaw, ArgoCD maintainer ([#19800](https://github.com/argoproj/argo-cd/issues/19800))

### The ConfigMap Sync Failure (Why SSA + SSD Must Be Paired)

Without Server-Side Diff, using Server-Side Apply + `ApplyOutOfSyncOnly`:

```
Git: configmap data = NEW content
                ↓
Client-side diff: "managed fields metadata looks the same..." → IN SYNC (wrong!)
                ↓
ApplyOutOfSyncOnly: "it's in-sync, skip it"
                ↓
Result: configmap never applied, ArgoCD says "Synced" ✓ (LIE)
```

With Server-Side Diff:

```
Git: configmap data = NEW content
                ↓
K8s API dry-run: "this would change .data.presets.ini" → OUT OF SYNC
                ↓
Sync: applies the configmap
                ↓
Result: configmap actually updated ✓
```

### Configuration

Enabled globally in `infrastructure/controllers/argocd/values.yaml`:

```yaml
configs:
  cm:
    resource.server-side-diff: "true"
```

## Dealing with Operator Mutations (ignoreDifferences)

Many Kubernetes operators and controllers mutate resources after creation. This creates a loop: ArgoCD applies the Git state, the operator mutates it, ArgoCD detects the diff, re-applies, and the cycle repeats.

### Strategy: Match the Canonical Form

The preferred approach is to write the **normalized value** in Git so there's no diff to fight about:

```yaml
# BAD — operator normalizes 1000m to "1", causing perpetual OutOfSync
resources:
  limits:
    cpu: 1000m    # ← ArgoCD sees "1000m" vs live "1" → diff!

# GOOD — matches what K8s/operator will normalize to
resources:
  limits:
    cpu: "1"      # ← ArgoCD sees "1" vs live "1" → no diff
```

This works for:
- Resource quantities (`1000m` → `"1"`, `1024Mi` → `1Gi`)
- Kyverno policy defaults (`skipBackgroundRequests: true`, `allowExistingViolations: true`, `method: GET`)
- Any field where the operator adds a default you can predict

### Strategy: ignoreDifferences

When you can't control the source (Helm charts, CRDs, controller mutations), use `ignoreDifferences`:

```yaml
# Per-Application or per-ApplicationSet
ignoreDifferences:
  # Kyverno injects caBundle into webhooks after creation
  - group: admissionregistration.k8s.io
    kind: MutatingWebhookConfiguration
    jqPathExpressions:
    - .webhooks[].clientConfig.caBundle

  # StatefulSet volumeClaimTemplates — K8s strips apiVersion/kind
  # (known ArgoCD bug #11143, unresolved)
  - group: apps
    kind: StatefulSet
    jqPathExpressions:
    - .spec.volumeClaimTemplates[].apiVersion
    - .spec.volumeClaimTemplates[].kind

  # CRD fields added by controllers
  - group: apiextensions.k8s.io
    kind: CustomResourceDefinition
    jqPathExpressions:
    - .metadata.labels
    - .spec.conversion
```

### ArgoCD 3.0+ Status Ignoring

ArgoCD 3.0 expanded status ignoring from CRD-only to **all resources** ([PR #22230](https://github.com/argoproj/argo-cd/pull/22230)). You no longer need `.status` in `ignoreDifferences` — it's handled globally. We removed all `.status` entries from our configs as part of the 3.x cleanup.

### Global vs Per-App ignoreDifferences

| Scope | Where | Use for |
|-------|-------|---------|
| **Global** | `values.yaml` → `resource.customizations.ignoreDifferences.*` | CRDs, resource types that always need ignoring cluster-wide |
| **Per-AppSet** | `template.spec.ignoreDifferences` | HTTPRoute, ExternalSecret, PVC fields for all apps in that AppSet |
| **Per-App** | `spec.ignoreDifferences` | Operator-specific mutations (Kyverno webhooks, OTEL collector) |

### Current ignoreDifferences Map

```
Global (values.yaml):
├── CRDs: .metadata.generation, .spec.conversion
├── OpenTelemetryCollector: .metadata.generation, .metadata.annotations
└── All resources: managedFieldsManagers (kube-controller-manager, kube-scheduler)

Kyverno App:
├── ClusterPolicy/ClusterCleanupPolicy/Policy: .metadata.generation
├── Webhook configs: .webhooks[].clientConfig.caBundle
└── CRDs: .metadata.generation, .metadata.labels, .spec.conversion

Infrastructure/My-Apps/Monitoring AppSets:
├── HTTPRoute: backendRefs group/kind/weight
├── ExternalSecret: .metadata.generation/finalizers, remoteRef defaults
└── PVC: dataSourceRef, dataSource, volumeName, storage

My-Apps AppSet (additional):
└── StatefulSet: imagePullPolicy, volumeClaimTemplates apiVersion/kind

Database AppSet:
├── CNPG Cluster: .metadata.generation
├── ExternalSecret: (same as above)
└── PVC: (same as above)

OTEL Operator App:
└── OpenTelemetryCollector: .metadata.generation, .metadata.annotations
```

## Performance Tuning

### Reconciliation Settings

```yaml
configs:
  cm:
    # How often ArgoCD checks for drift (plus random jitter)
    timeout.reconciliation: "60s"
    timeout.reconciliation.jitter: "30s"
    # Hard reconciliation (full git re-fetch + cache invalidation)
    # Set to "0" (disabled) — use "Hard Refresh" button for manual re-fetch
    # WARNING: Setting this to "60s" makes EVERY reconcile a hard reconcile,
    # hammering the repo server and GitHub API
    timeout.hard.reconciliation: "0"
```

### Controller Performance

```yaml
configs:
  params:
    # Parallel status processors (default 20, ~1 per 20 apps)
    controller.status.processors: "50"
    # Concurrent sync operations (default 10)
    controller.operation.processors: "25"
    # Limit concurrent manifest generations to prevent OOM
    reposerver.parallelism.limit: "5"
    # Increase timeout for large Helm charts (prometheus-stack)
    controller.repo.server.timeout.seconds: "300"

controller:
  env:
    # K8s API client throughput
    - name: ARGOCD_K8S_CLIENT_QPS
      value: "50"
    - name: ARGOCD_K8S_CLIENT_BURST
      value: "100"
    # Split large app trees across Redis keys
    - name: ARGOCD_APPLICATION_TREE_SHARD_SIZE
      value: "100"
```

### Server-Side Diff Performance Impact

Server-side diff adds ~5-10x overhead per reconciliation (dry-run API calls to the K8s API server). Mitigations in this cluster:
- **Reconciliation jitter** (30s) prevents all 60+ apps from reconciling simultaneously
- **Hard reconciliation disabled** (`"0"`) — avoids redundant git re-fetches
- **Caching** — dry-run results are cached; new API calls only trigger on refresh, new git revision, or app spec change
- **Status processors increased** (50) to handle the higher per-app reconciliation time

## Retry Policy

All Applications and ApplicationSets use **infinite retries** (`limit: -1`) with exponential backoff:

```yaml
retry:
  limit: -1           # Never permanently die
  backoff:
    duration: 10s     # First retry after 10s
    factor: 2         # Exponential: 10s, 20s, 40s, 80s, ...
    maxDuration: 10m  # Cap at 10 minutes between retries
```

**Why infinite**: During bootstrap, Kyverno's mutating webhook (`mutate.kyverno.svc-fail`, failurePolicy: Fail) takes time to warm up after pods start. ArgoCD marks Kyverno "Healthy" when pods are Running, but the webhook isn't responsive yet. Wave 4+ apps that sync during this window get `context deadline exceeded` rejections. With a fixed retry limit, apps permanently die and require manual re-sync. Infinite retries with backoff cap ensures all apps eventually converge without manual intervention.

## Sync Options (CRITICAL)

Standard sync options for all ApplicationSets:

```yaml
syncOptions:
- CreateNamespace=true
- ServerSideApply=true          # Server-side apply for better conflict resolution
- RespectIgnoreDifferences=true # Honor ignoreDifferences for PVC, HTTPRoute, etc.
- Replace=false                 # Use patch, not full replace
```

**DO NOT add these options:**
- `ApplyOutOfSyncOnly=true` — Even with ServerSideDiff, has [known edge cases with key removal](https://github.com/argoproj/argo-cd/issues/24882). Not worth the risk for a homelab-scale cluster.
- `IgnoreMissingTemplate=true` — Can mask real template errors in ApplicationSets.

## Known ArgoCD Issues

| Issue | Impact | Our Workaround |
|-------|--------|----------------|
| [#11143](https://github.com/argoproj/argo-cd/issues/11143) StatefulSet VCT stripping | K8s strips `apiVersion`/`kind` from volumeClaimTemplates | `ignoreDifferences` on StatefulSet |
| [#18344](https://github.com/argoproj/argo-cd/issues/18344) SSD performance | ~10x reconciliation overhead | Jitter + disabled hard reconciliation |
| [#19800](https://github.com/argoproj/argo-cd/issues/19800) IncludeMutationWebhook | Maintainers deny global toggle | Match canonical forms in Git instead |
| [#22230](https://github.com/argoproj/argo-cd/pull/22230) Status ignoring | 3.0+ ignores all `.status` | Removed redundant `.status` ignores |
| [#24134](https://github.com/argoproj/argo-cd/issues/24134) SSD not default | Must opt-in even in 3.3 | Explicit `resource.server-side-diff: "true"` |
| [#24882](https://github.com/argoproj/argo-cd/issues/24882) Key removal detection | `ApplyOutOfSyncOnly` misses deletes | Don't use `ApplyOutOfSyncOnly` |

## References
- [ArgoCD Diff Strategies](https://argo-cd.readthedocs.io/en/stable/user-guide/diff-strategies/)
- [ArgoCD Sync Options](https://argo-cd.readthedocs.io/en/latest/user-guide/sync-options/)
- [ArgoCD SSA ConfigMap sync failure (#22687)](https://github.com/argoproj/argo-cd/issues/22687)
- [Kyverno Platform Notes — ArgoCD Integration](https://kyverno.io/docs/installation/platform-notes/)
- [CNCF Blog — GitOps and Mutating Policies](https://www.cncf.io/blog/2024/01/18/gitops-and-mutating-policies-the-tale-of-two-loops/)
