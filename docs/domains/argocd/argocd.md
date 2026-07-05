# ArgoCD GitOps Architecture

The ArgoCD bootstrap and sync-wave reference for this cluster.

## Bootstrap Rule

Apply resources in this order:

```text
CRDs first, controllers/apps second, CRs third.
```

Observability is not a core dependency. Core apps must bootstrap without Prometheus.

Do not install Prometheus Operator CRDs early to satisfy bootstrap apps. ServiceMonitor and PrometheusRule resources belong in later observability overlays. `kube-prometheus-stack` is the sole owner and provider of `monitoring.coreos.com` CRDs.

## Entry Point Layers

ArgoCD starts from the manually seeded root application:

```text
infrastructure/controllers/argocd/root.yaml
```

The root application renders three layers:

1. `core-dependencies`: foundational controllers and storage dependencies.
2. `custom-entrypoints`: repository-specific applications with explicit wave ordering.
3. `applicationsets`: infrastructure, database, monitoring, and workload generators.

See [ArgoCD entrypoints](entrypoints.md) for the concrete files.

## Current Wave Ordering

| Wave | Applications |
|---|---|
| `0` | ArgoCD projects/bootstrap, Cilium, 1Password Connect, External Secrets |
| `1` | cert-manager, Longhorn, snapshot-controller |
| `2` | kopiur operator (CRDs + controller + webhook; volume populator) |
| `3` | CNPG Barman plugin, kopiur config (ClusterRepository `cluster-kopia` + credential fanout + VolumeSnapshotClass) |
| `4` | KEDA core, Temporal worker, infrastructure and database AppSets |
| `5` | OpenTelemetry operator core, monitoring AppSet including `kube-prometheus-stack` |
| `6` | KEDA observability, OpenTelemetry operator observability, workload AppSet |

cert-manager is Wave `1` because the CNPG Barman plugin depends on it. The kopiur operator is Wave `2` (CRDs + controller + webhook), with its repo/credential config at Wave `3`. KEDA and OpenTelemetry ServiceMonitor resources render from Wave `6` observability overlays.

CNPG `enablePodMonitor: true` is an accepted runtime soft-coupling. It can log transient errors before monitoring exists, but it is not an ArgoCD dry-run blocker.

## How Argo CD Sync Waves and Waiting Work

Argo CD uses **Sync Waves** to orchestrate deployment order. The `argocd.argoproj.io/sync-wave` annotation on resources (or applications) defines a sequence from Wave `0` to Wave `6`.

Argo CD's gating logic:
1. It applies all resources belonging to Wave `N`.
2. It monitors their status and **refuses to apply Wave `N+1` until every resource in Wave `N` reaches a `Healthy` state**.
3. If a resource fails, hangs, or stays `Progressing` indefinitely, Argo CD halts progression. This prevents cascade failures (e.g. deploying databases before cert-manager is ready).

### The Restore Gating Loop

During a disaster recovery (DR) rebuild, sync wave gating interacts with Kopiur's **restore-before-bind** populator:

```text
Sync-wave gating (Argo waits until all Healthy before the next wave):

  Wave 0  Foundation ........ Cilium CNI, 1Password Connect, External Secrets
     |  (all Healthy)
     v
  Wave 1  Core Controllers .. cert-manager, Longhorn, Snapshot Controller
     |  (all Healthy)
     v
  Wave 2  Backup Engine ..... Kopiur Operator
     |  (all Healthy)
     v
  Wave 3  Backup Config ..... Kopiur ClusterRepository + Credential Fanout
     |  (all Healthy)
     v
  Waves 4-6  Apps & Databases

Restore-before-bind inside Waves 4-6:

  PVC created (dataSourceRef -> Restore)  ->  binding withheld, PVC Pending
  Kopiur Mover Job  --(1. hydrates volume)-->  PVC
  PVC  --(2. binds)-->  App Pod
  App Pod  --(3. reaches Ready)-->  Argo CD marks App Healthy
```

*   **Argo CD waits on Wave 6**: When Wave 6 (user workloads) is applied, the PVC is created with a `dataSourceRef` pointing to Kopiur. Kubernetes withholds volume binding, keeping the PVC `Pending`.
*   The application Pod sits in `ContainerCreating` or `Pending` because it lacks its volume. Argo CD flags the Application as **Progressing**.
*   In the background, Kopiur's volume populator spawns the mover Job, hydrates the Longhorn volume from S3, and binds the PVC.
*   Once bound, the Pod boots and reaches `Ready`. Argo CD detects the app transition from `Progressing` to `Healthy` and completes the Sync loop.

---

## What a Kustomize Component Is (Concept & Usage)

Traditional Kustomize uses a rigid **base-overlay** pattern: an overlay inherits everything from a single base and applies environment-specific patches. This model breaks down when you need to share multiple independent, cross-cutting features (backups, ingress models, observability) across many apps.

A **Kustomize Component** acts like a **mixin or trait**:
*   It is a reusable bundle of patches loaded alongside base resources.
*   An application can mix in multiple components in its `kustomization.yaml` (e.g. `components: [ ../../common/kopiur-backup, ../../common/observability ]`).
*   The component targets resources by `kind` and `group` and injects uniform properties at build time.

### How the `kopiur-backup` Component works

The shared component `my-apps/common/kopiur-backup` defines no backups itself. It looks for any `SnapshotPolicy`, `SnapshotSchedule`, or `Restore` resources defined locally in your application's folder and injects the uniform cluster configs:

```yaml
# What the developer writes in the app folder (the stub)
apiVersion: kopiur.home-operations.com/v1alpha1
kind: SnapshotPolicy
metadata:
  name: storage
spec:
  sources:
    - pvc:
        name: storage
  identity:
    username: storage
    hostname: open-webui
  mover:
    securityContext:
      runAsUser: 568 # Varies per app (data owner UID)
```

At build time, the component injects the cluster-wide fields:
*   `/spec/copyMethod` ➔ `Snapshot`
*   `/spec/volumeSnapshotClassName` ➔ `longhorn-snapclass`
*   `/spec/repository` ➔ `ClusterRepository/cluster-kopia`

Per-PVC backup configs stay tiny (storing only what varies: cron schedules and the exact data owner UID) while the cluster's backup infrastructure properties live in one shared file.

---

## Related Docs

- [ArgoCD entrypoints](entrypoints.md)
- [cluster DR nuke restore runbook](../../disaster-recovery.md)
- [docs index](../../index.md)
