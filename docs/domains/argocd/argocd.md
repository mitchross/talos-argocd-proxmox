# ArgoCD GitOps Architecture

This is the current ArgoCD bootstrap reference after the full cluster nuke and rebuild.

## Bootstrap Rule

Apply resources in this order:

```text
CRDs first, controllers/apps second, CRs third.
```

Observability is not a core dependency. Core apps must bootstrap without Prometheus.

Do not install Prometheus Operator CRDs early just to satisfy bootstrap apps. ServiceMonitor and PrometheusRule resources belong in later observability overlays. `kube-prometheus-stack` remains the sole owner and provider of `monitoring.coreos.com` CRDs.

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

cert-manager is intentionally Wave `1`: the CNPG Barman plugin depends on it. The kopiur operator is Wave `2` (CRDs + controller + webhook), with its repo/credential config at Wave `3`. KEDA and OpenTelemetry ServiceMonitor resources render from Wave `6` observability overlays.

CNPG `enablePodMonitor: true` remains an accepted runtime soft-coupling. It can log transient errors before monitoring exists, but it is not an ArgoCD dry-run blocker.

## Full Nuke Finding

The rebuild validated a design rule: deleting Prometheus must not prevent the core cluster from bootstrapping. An early Prometheus Operator CRD application was considered and explicitly rejected because it would make observability foundational.

## How Argo CD Sync Waves and Waiting Work

Argo CD uses **Sync Waves** to orchestrate deployment order. By adding the `argocd.argoproj.io/sync-wave` annotation to resources (or applications), we define a sequence from Wave `0` to Wave `6`. 

Argo CD's gating logic works as follows:
1. It applies all resources belonging to Wave `N`.
2. It monitors their status and **refuses to apply Wave `N+1` until every resource in Wave `N` reaches a `Healthy` state**.
3. If a resource fails, hangs, or stays `Progressing` indefinitely, Argo CD halts progression. This prevents cascade failures (e.g., deploying databases before cert-manager is ready).

### The Restore Gating Loop

During a disaster recovery (DR) rebuild, this sync wave gating interacts with Kopiur's **restore-before-bind** populator:

```mermaid
flowchart TD
    subgraph Wave0["Wave 0: Foundation (CNI, Secrets)"]
        Cilium["Cilium CNI"]
        OP["1Password Connect"]
        ES["External Secrets"]
    end

    subgraph Wave1["Wave 1: Core Controllers (Storage)"]
        CM["cert-manager"]
        LH["Longhorn Storage"]
        SC["Snapshot Controller"]
    end

    subgraph Wave2["Wave 2: Backup Engine"]
        KOp["Kopiur Operator"]
    end

    subgraph Wave3["Wave 3: Backup Config"]
        KConf["Kopiur ClusterRepository<br/>& Credential Fanout"]
    end

    subgraph Wave4_6["Waves 4-6: Apps & Databases"]
        App["App Pod"]
        PVC["PVC (Restore Populator)"]
    end

    %% Sync Gating logic
    Wave0 -->|"Argo waits until all Healthy"| Wave1
    Wave1 -->|"Argo waits until all Healthy"| Wave2
    Wave2 -->|"Argo waits until all Healthy"| Wave3
    Wave3 -->|"Argo waits until all Healthy"| Wave4_6

    PVC -.-->|"Withholds binding (PVC Pending)"| App
    PopJob["Kopiur Mover Job"] -->|"1. Hydrates volume"| PVC
    PVC -->|"2. Binds"| App
    App -->|"3. Reaches Ready"| ArgoHealth["Argo CD marks App Healthy"]
```

*   **Argo CD is kept waiting on Wave 6**: When Wave 6 (user workloads) is applied, the PVC is created with a `dataSourceRef` pointing to Kopiur. K8s withholds volume binding, keeping the PVC `Pending`.
*   The application Pod sits in `ContainerCreating` or `Pending` because it lacks its volume. Argo CD flags the Application as **Progressing**.
*   In the background, Kopiur's volume populator spawns the mover Job, hydrates the Longhorn volume from S3, and binds the PVC.
*   Once bound, the Pod boots and reaches `Ready` status. Argo CD detects the app has transitioned from `Progressing` to `Healthy` and completes the Sync loop.

---

## What a Kustomize Component Is (Concept & Usage)

In traditional Kustomize, you have a rigid **base-overlay** pattern: an overlay inherits everything from a single base and applies environment-specific patches. This model breaks down when you need to share multiple independent, cross-cutting features (like backups, ingress models, or observability configurations) across various apps.

A **Kustomize Component** acts like a **mixin or trait** (analogous to object-oriented programming):
*   It is a reusable bundle of patches that can be loaded alongside base resources.
*   An application can mix in multiple components in its `kustomization.yaml` (e.g. `components: [ ../../common/kopiur-backup, ../../common/observability ]`).
*   The component targets resources by `kind` and `group` and injects uniform properties at build time.

### How the `kopiur-backup` Component works:

The shared component `my-apps/common/kopiur-backup` doesn't define any backups itself. Instead, it looks for any `SnapshotPolicy`, `SnapshotSchedule`, or `Restore` resources defined locally in your application's folder and dynamically injects the uniform cluster configs:

```yaml
# What the developer writes in the app folder (The Stub)
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

At build time, the component applies patches to inject the cluster-wide fields:
*   `/spec/copyMethod` ➔ `Snapshot`
*   `/spec/volumeSnapshotClassName` ➔ `longhorn-snapclass`
*   `/spec/repository` ➔ `ClusterRepository/cluster-kopia`

This design allows the per-PVC backup configs to remain tiny (storing only what varies: cron schedules and the exact data owner UID) while centralizing the cluster's backup infrastructure properties in one shared file.

---

## Related Docs

- [ArgoCD entrypoints](entrypoints.md)
- [cluster DR nuke restore runbook](../../disaster-recovery.md)
- [docs index](../../index.md)
