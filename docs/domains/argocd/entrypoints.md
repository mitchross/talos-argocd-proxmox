# Entrypoints and sync waves

An entrypoint is a file that the root Application renders directly from `infrastructure/controllers/argocd/apps/`.
This page lists every entrypoint, its sync wave, and the rules for changing one.
Read it before you add an infrastructure component, move an app folder, or retire an app.

`root.yaml` is the manual seed, and Argo CD does not manage it.
After the seed exists, Argo CD manages the whole entrypoint tree.
That includes file moves inside `apps/`, ApplicationSet edits, and AppProject edits.

[How Argo CD deploys this repo](argocd.md) explains the concepts. This page is the reference.

## Layout

| Folder | Purpose |
|--------|---------|
| `bootstrap/` | Wave 0 foundation apps required before the rest of GitOps can converge |
| `core-dependencies/` | Storage, restore, and bootstrap services that later apps depend on |
| `custom-entrypoints/` | Intentional standalone apps kept out of ApplicationSets for ordering or render behavior |
| `appsets/` | Broad directory discovery for infrastructure, databases, monitoring, and user apps |

## Entrypoint table

| Entrypoint | Type | Wave | Reason | Can move to an ApplicationSet? |
|------------|------|------|--------|---------------------|
| `projects.yaml` | AppProjects | 0 | Project grouping and homelab trust boundary | No, foundational Argo CD config |
| `bootstrap/argocd.yaml` | Application | 0 | Self-manages the Argo CD Helm chart and values | No, self-management entrypoint |
| `bootstrap/cilium-app.yaml` | Application | 0 | CNI and Gateway API foundation | No, must be healthy before pods and routes |
| `bootstrap/1passwordconnect.yaml` | Application | 0 | Secret backend for External Secrets | No, secret dependency for later waves |
| `bootstrap/external-secrets.yaml` | Application | 0 | ExternalSecret CRDs and controller | No, CRDs are required by downstream apps |
| `core-dependencies/cert-manager-app.yaml` | Application | 1 | Certificate controller required before webhook-cert consumers in later waves | No, required before cert-dependent apps |
| `core-dependencies/longhorn-app.yaml` | Application | 1 | Storage foundation before PVC consumers | No, required before restore/app PVC flows |
| `core-dependencies/snapshot-controller-app.yaml` | Application | 1 | VolumeSnapshot CRDs and controller | No, required by backup/restore flows |
| `core-dependencies/kopiur-operator-app.yaml` | Application | 2 | kopiur operator (Kopia-native backup): CRDs + controller + webhook + volume populator; no monitoring dependency | No, required before managed app PVCs |
| `core-dependencies/kopiur-config-app.yaml` | Application | 3 | kopiur repo config: `ClusterRepository cluster-kopia` + credential fanout + `VolumeSnapshotClass longhorn-snapclass` | No, required before managed app PVCs |
| `custom-entrypoints/keda-app.yaml` | Application | 4 | Standalone to isolate its render from the ApplicationSet generator | Maybe, if the ApplicationSet render stays stable |
| `custom-entrypoints/vertical-pod-autoscaler-app.yaml` | Application | 4 | VPA controller (recommender/updater/admission) | Maybe, if the ApplicationSet render stays stable |
| `custom-entrypoints/vpa-system-policies-app.yaml` | Application | 4 | VPA policies for the small set of bootstrap/system workloads without a co-located owner. The Application is named `vpa-recommendations` | No, ownership exception is explicit |
| `custom-entrypoints/temporal-worker-controller-app.yaml` | Application | 4 | Standalone to isolate its render from the ApplicationSet generator | Maybe, if the ApplicationSet render stays stable |
| `custom-entrypoints/vertical-pod-autoscaler-observability-app.yaml` | Application | 6 | Optional VPA PodMonitor and alerts after monitoring CRDs exist | No, keeps observability out of core |
| `custom-entrypoints/opentelemetry-operator-app.yaml` | Application | 6 | Optional telemetry alongside workloads; health cannot gate workload discovery | Maybe; preserve its bootstrap independence |
| `custom-entrypoints/keda-observability-app.yaml` | Application | 6 | Optional KEDA ServiceMonitor resources after monitoring CRDs exist | No, keeps observability out of core |
| `custom-entrypoints/opentelemetry-operator-observability-app.yaml` | Application | 6 | Optional OpenTelemetry ServiceMonitor after monitoring CRDs exist | No, keeps observability out of core |
| `appsets/infrastructure-appset.yaml` | ApplicationSet | 4 | Explicit list of core infrastructure directories | N/A |
| `appsets/database-appset.yaml` | ApplicationSet | 4 | Discovers `infrastructure/database/*/*` (Redis + shared DB support); sync is automated | N/A |
| `appsets/monitoring-appset.yaml` | ApplicationSet | 5 | Discovers `monitoring/*/*` (`metrics/`, `logs/`, `tracing/`, `ai-ops/`) after core infra, excluding `monitoring/*/_archive` | N/A |
| `appsets/my-apps-appset.yaml` | ApplicationSet | 6 | Discovers `my-apps/*/*`, excluding Components and `my-apps/*/_archive`; all automated + self-healing | N/A |

`rustfs-lifecycle` is not a standalone entrypoint.
`appsets/infrastructure-appset.yaml` generates it from `infrastructure/backup/rustfs-lifecycle` at wave 4.

## What an ApplicationSet wave does and does not order

The wave on an ApplicationSet orders when Argo CD creates the generator object.
It does not order the health of the Applications that the generator creates. Those Applications reconcile independently.
Read [how sync waves and waiting work](argocd.md#how-argo-cd-sync-waves-and-waiting-work) before you treat an ApplicationSet wave as a dependency barrier.

## How names and namespaces are generated

Each ApplicationSet adds a domain prefix to the Application name:
`infrastructure-<component>`, `database-<database>`, `monitoring-<component>`, and `my-apps-<app>`.
The namespace uses the last folder name with no prefix.
The prefix keeps the UI unambiguous. Without it, the Temporal database Application could look like the Temporal server Application.

Category folders are for people only. The Application name and the namespace come from the last folder.
A move between categories, for example `my-apps/media/x` to `my-apps/utility/x`, changes only the source path.
A rename of the last folder creates a new Application and a new namespace.

A changed Application name replaces the Application object.
Never merge an identity rename into a running cluster without a staged finalizer migration.

### Template syntax

All four ApplicationSets use strict Go templates (`missingkey=error`).
In Go-template mode, the Git generator's directory fields are objects.
The leading `.` means "the current generator result". `path` is the directory object, and the remaining names select fields from it.
Use `{{ .path.path }}` and `{{ .path.basename }}`. Do not use the deprecated fasttemplate forms `{{ path }}` and `{{ path.basename }}`.

Strict missing-key handling fails generation on purpose.
Without it, a wrong field name produces an Application with an empty name, source path, or namespace.
The render CI also rejects any non-Component kustomization that produces zero Kubernetes objects.

### Components are excluded from discovery

`my-apps/common/*` is excluded from the my-apps generator.
Those directories are shared Kustomize Components (`kind: Component`), and kustomize builds a Component alone as an empty render.
Without the exclude, the ApplicationSet generates an Application with zero resources.
`validate-argocd-apps.sh` Check 8 fails CI if a Component directory becomes discoverable again.

## Rules for changing entrypoints

### Move folders and change ApplicationSet paths in separate PRs

**Never move app folders and change the ApplicationSet paths that match them in one commit.**
The controller can read the new folders with the old ApplicationSet spec.
The old paths then match nothing, and the ApplicationSet deletes its Applications.
For an ApplicationSet that keeps the resources finalizer, that deletes the workloads and their PVCs.

Use three PRs:

1. List the new paths alongside the old paths.
2. Move the folders.
3. Drop the old paths.

Wait for each step to be live, not only merged.
The root Application walks the sync waves and can take about 20 minutes to apply an ApplicationSet change.
Use the [live prerequisite check](live-prerequisite-gate.md) before each next step. It is read-only.

The check must show all of the following:

- `operationState.phase: Succeeded`, with `operationState.syncResult.revision` at the merged commit.
- The exact live ApplicationSet fields.
- The ownership and finalizers of the generated Applications.
- The UIDs of the resources that must survive.

`status.sync.revision` alone is comparison evidence. It does not prove that the safety change applied.
The user must explicitly authorize each specific PR merge.

### What happens when a path stops matching

The infrastructure and monitoring ApplicationSets set `preserveResourcesOnDeletion: true`.
Their generated Applications carry no `resources-finalizer`.
A path can stop matching for a short time, through a folder move, a typo, or an ApplicationSet spec and repo that update out of order.
Argo CD then removes only the Application object and recreates it on the next generation.
Workloads, namespaces, and PVCs keep running.

The cost is that removing an infrastructure or monitoring component from Git leaves its resources on the cluster.
Delete them by hand after the Application is gone.
They still carry the `argocd.argoproj.io/tracking-id: <app>:…` annotation.
`kubectl delete -k` against the path at the previous commit removes them.

Do not add the finalizer back to those Applications by hand. The ApplicationSet controller rewrites finalizers on every update.

The my-apps and database ApplicationSets keep the finalizer, because `_archive/` relies on the cascade delete.

### Where ignore rules live

Global ignore rules for HTTPRoute, ExternalSecret, and PVC restore fields are in `infrastructure/controllers/argocd/values.yaml`.
An ApplicationSet carries only app-specific ignore rules.

### AppProjects are permissive

AppProjects are permissive on purpose for a single-operator homelab.
They are labels and UI grouping, not hard tenant guardrails.

### Hook Jobs

A hook Job is acceptable when it is idempotent, bounded, and documented.
The RustFS lifecycle Job is a PostSync hook, because S3 lifecycle PUTs are idempotent and Kubernetes Jobs are immutable.

## Bootstrap guardrail: observability is not a core dependency

**A bootstrap-critical app must render successfully without `monitoring.coreos.com` CRDs.**

Those CRDs do not exist until kube-prometheus-stack arrives through the wave 5 ApplicationSet.
An earlier-wave app that ships a ServiceMonitor or PrometheusRule fails its dry-run.
The root Application then cannot pass that wave, and nothing after it deploys.

Follow these rules:

- Put observability CRs in a separate optional Application that syncs after wave 5. For example, `keda-observability` is at wave 6, and the KEDA core is at wave 4.
- **Do not install Prometheus Operator CRDs early.**
- Use `SkipDryRunOnMissingResource` only on an observability Application. It is not a fix for a core app.
- Keep `cert-manager` at wave 1, not 4, so that cert-dependent apps in early waves can start.

The Argo CD Helm chart follows this rule by itself. It renders its monitors only when the cluster has the monitoring API.

The [disaster recovery runbook](../../disaster-recovery.md) has the full detail.

## Bootstrap guardrail: Application health does not prove webhook reachability

Waves wait for Argo CD Application health.
For a webhook Deployment, healthy means that ready replicas equal desired replicas.
The kubelet decides readiness with a probe on the pod's own node.
Neither signal involves the API server.

A webhook pod can therefore be `Running` and `Ready`, with its Application `Healthy`, while the API server cannot reach it across the pod network.
Every later wave then proceeds and calls a webhook that does not answer.

`failurePolicy` sets how much breaks. The size of the component does not.
A cluster-scoped `failurePolicy: Fail` webhook rejects **every** matching write in the cluster while it is unreachable.
A sync can fail after it applies only part of its resources.
Unrelated apps can stall while they wait for Secrets or other objects that admission rejects.

Two rules follow.

**Pin fail-closed cluster-scoped webhooks to the control plane.**
Use `nodeSelector: node-role.kubernetes.io/control-plane` plus the matching `NoSchedule` toleration.
The API server then calls the webhook on its own node, so a pod-network fault on another node cannot break admission.
This rule applies to `cert-manager`.
Webhook availability then follows the API server's availability. If the control plane is down, admission does not matter.

**Do not add a custom Lua health check to probe webhook reachability.**
Keep the Argo CD configuration simple.
The reachability signal belongs in alerting, not in the wave gate.
`monitoring/metrics/prometheus-stack/admission-webhook-alerts.yaml` reads the API server's own `apiserver_admission_webhook_*` metrics.

## Archived apps

A retired app moves into its category's `_archive/` folder, for example
`my-apps/ai/_archive/ninfer/` or `monitoring/ai-ops/_archive/holmesgpt/`.
The my-apps and monitoring ApplicationSets exclude `*/_archive`, so nothing there is deployed.

### Archive an app

1. Confirm that the latest backup succeeded: `kubectl -n <ns> get snapshot`.
2. Run `git mv my-apps/<category>/<app> my-apps/<category>/_archive/<app>` and merge the PR.

Expected result for my-apps: Argo CD deletes the Application, its namespace, and its PVCs through the resources finalizer.

Expected result for monitoring: Argo CD removes the Application, but its resources remain, because that ApplicationSet preserves resources.
Manual cleanup requires explicit destructive authorization.

The backups stay in the Kopia repository, because the `ClusterRepository` uses `onNamespaceDelete: Orphan`.
That value is the current CRD default. Do not change it, or archiving an app deletes its backup history.

### Bring an app back

Run `git mv` to move the folder back up one level, and merge the PR.
Argo CD recreates the Application.
Restore-before-bind fills each PVC from its latest backup. A disaster-recovery rebuild uses the same path.

### Leave archived files unchanged

Archived files sit one folder deeper, so their `../../common/kopiur-backup` link does not resolve there.
CI skips `_archive/` when it renders. The link works again after the folder moves back.
