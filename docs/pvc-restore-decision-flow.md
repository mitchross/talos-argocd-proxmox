# GitOps PVC Restore Decision Flow

This is the cluster-level picture for backup-labeled PVCs in this repo.

The invariant:

> A PVC labeled `backup: hourly` or `backup: daily` must not be created empty when backup truth is unknown.

## First View

```mermaid
flowchart TD
    A[Git app manifest<br/>PVC has backup label] --> B[ArgoCD syncs app]
    B --> C[Kubernetes CREATE PVC]
    C --> D[Kyverno admission]
    D --> E[pvc-plumber /exists]
    E --> F[Kopia repository on NFS]

    F --> G{Decision}
    G -->|restore| H[Kyverno injects dataSourceRef]
    H --> I[VolSync ReplicationDestination]
    I --> J[Longhorn PVC populated from backup]
    J --> K[App pod starts with restored data]

    G -->|fresh| L[Kyverno allows PVC unchanged]
    L --> M[Longhorn provisions empty PVC]
    M --> N[New app starts fresh]

    G -->|unknown| O[Kyverno denies PVC admission]
    O --> P[ArgoCD retries]
    P --> Q[Fix Kopia/NFS/pvc-plumber]
    Q --> C

    classDef restore fill:#d9fbe5,stroke:#16803c,color:#0b3d1b;
    classDef fresh fill:#d9ecff,stroke:#1d5fa7,color:#0b2f57;
    classDef block fill:#ffe1df,stroke:#b42318,color:#5f130d;
    class H,I,J,K restore;
    class L,M,N fresh;
    class O,P,Q block;
```

## Swimlane

```mermaid
sequenceDiagram
    participant Git as Git
    participant Argo as ArgoCD
    participant API as Kubernetes API
    participant Kyverno as Kyverno
    participant Plumber as pvc-plumber
    participant Kopia as Kopia/NFS
    participant VolSync as VolSync
    participant Longhorn as Longhorn
    participant App as App

    Git->>Argo: backup-labeled PVC
    Argo->>API: apply PVC
    API->>Kyverno: admission review
    Kyverno->>Plumber: GET /readyz
    Plumber-->>Kyverno: status=ok
    Kyverno->>Plumber: GET /exists/ns/pvc
    Plumber->>Kopia: snapshot list source

    alt decision=restore
        Kopia-->>Plumber: snapshots exist
        Plumber-->>Kyverno: 200 restore authoritative=true
        Kyverno-->>API: add dataSourceRef
        API->>VolSync: populate PVC from ReplicationDestination
        VolSync->>Longhorn: create restored volume
        Longhorn-->>API: PVC Bound
        API-->>App: start pod
    else decision=fresh
        Kopia-->>Plumber: no snapshots
        Plumber-->>Kyverno: 200 fresh authoritative=true
        Kyverno-->>API: allow unchanged
        API->>Longhorn: provision empty volume
        Longhorn-->>API: PVC Bound
        API-->>App: start pod
    else decision=unknown
        Kopia-->>Plumber: error, timeout, invalid JSON
        Plumber-->>Kyverno: 503 unknown authoritative=false
        Kyverno-->>API: deny admission
        API-->>Argo: sync not healthy yet
    end
```

## What Changed

| Area | Before | Now |
|---|---|---|
| pvc-plumber API | `exists: true/false`; errors looked like `exists: false` | `decision: restore/fresh/unknown` plus `authoritative` |
| Unknown backup truth | Could look like "no backup" | HTTP 503 and `decision: unknown` |
| Kyverno validation | Policy-level `Audit` | Enforced deny for unavailable or non-authoritative checks |
| Kyverno mutation | Mutated on `exists == true` only | Mutates only on authoritative `restore` |
| App startup safety | `/readyz` could pass while `/exists` failed open | `/exists` is the source of per-PVC truth |
| Kopia maintenance | Daily full maintenance with `--safety=none` | Daily safe maintenance off the top of the hour |
| Monitoring | VolSync alerts, no pvc-plumber scrape | pvc-plumber ServiceMonitor and decision/error alerts |

## Design Tradeoffs For Review

| Design | Strengths | Weaknesses | Best use |
|---|---|---|---|
| Hardened Kyverno + pvc-plumber | Minimal app overhead, works with existing PVC labels, keeps restore decision at admission time, small code surface | Kyverno is still doing orchestration-like work; generated resource drift is not continuously reconciled; decision logic is split across policy and service | Good near-term platform hardening |
| Real controller + CRDs | One owner for admission, reconciliation, status, drift repair, metrics, schedule staggering, and cleanup | More code, CRD lifecycle to maintain, webhook certificates/RBAC/controller upgrades become platform responsibilities | Best long-term production shape |
| Manual Longhorn/VolSync restore | Uses existing tools directly, little custom code | Does not scale to many apps, requires human timing, easy for apps to initialize empty state before restore | Emergency manual repair only |
| Per-app restore manifests | Fully declarative per app, no admission oracle | High repetition, easy to forget, hard to know whether a backup exists for first install versus rebuild | Special apps with custom recovery contracts |

Reviewer prompt:

> Judge whether the current hardened design is an acceptable bridge to the controller. The key question is whether the split between Kyverno admission and pvc-plumber decision logic is safe enough now that unknown backup truth fails closed.

## Decision Table

| pvc-plumber response | Kyverno action | Result |
|---|---|---|
| HTTP 200, `decision=restore`, `authoritative=true`, `exists=true` | Allow and mutate `dataSourceRef` | VolSync restore |
| HTTP 200, `decision=fresh`, `authoritative=true`, `exists=false` | Allow unchanged | New empty PVC |
| HTTP 503, `decision=unknown`, `authoritative=false` | Deny | ArgoCD retries |
| pvc-plumber down | Deny | ArgoCD retries |
| Kopia/NFS query error | Deny | ArgoCD retries |

The Kyverno policy also sets an explicit `apiCall.default` for pvc-plumber failures. If the HTTP call itself fails, Kyverno treats the response as `decision=unknown`, `authoritative=false`, and denies the PVC.

## Files In This Repo

| Purpose | File |
|---|---|
| pvc-plumber deployment | `infrastructure/controllers/pvc-plumber/deployment.yaml` |
| Kyverno backup/restore admission and generation | `infrastructure/controllers/kyverno/policies/volsync-pvc-backup-restore.yaml` |
| Kopia maintenance | `infrastructure/storage/volsync/kopia-maintenance-cronjob.yaml` |
| Prometheus scrape config | `monitoring/prometheus-stack/custom-servicemonitors.yaml` |
| Prometheus alerts | `monitoring/prometheus-stack/volsync-alerts.yaml` |

## How To Read A Failure

```mermaid
flowchart LR
    A[ArgoCD app stuck syncing] --> B{PVC admission denied?}
    B -->|yes| C[Check Kyverno policy report/events]
    C --> D{pvc-plumber unknown?}
    D -->|yes| E[Check pvc-plumber logs and metrics]
    E --> F{Kopia/NFS healthy?}
    F -->|no| G[Fix repository access]
    G --> H[ArgoCD retries PVC create]
    F -->|yes| I[Inspect /exists response for namespace/pvc]
    B -->|no| J[Check VolSync ReplicationDestination]

    classDef action fill:#fff7cc,stroke:#8a6d00,color:#453500;
    class C,E,G,H,I,J action;
```

The desired failure mode is visible waiting, not silent empty initialization.
