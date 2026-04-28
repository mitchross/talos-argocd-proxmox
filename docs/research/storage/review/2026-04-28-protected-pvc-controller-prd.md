# Protected PVC Controller PRD

Date: 2026-04-28

Status: product requirements draft.

## Product Name

Working name: `protected-pvc-controller`

API group: `storage.vanillax.dev`

## Executive Summary

Build a Kubernetes controller plus admission webhook that turns a simple PVC backup label into a complete, safe backup and restore lifecycle.

The controller replaces the fragile parts of the current Kyverno + pvc-plumber arrangement while preserving the best part of the user experience:

```yaml
metadata:
  labels:
    backup: "hourly"
```

The controller must decide at PVC creation time whether to:

- restore from an existing backup,
- create a fresh PVC because no backup exists,
- or block creation because backup truth is unknown.

This keeps the zero-click GitOps restore model while moving the logic into a purpose-built control plane with status, metrics, drift correction, and safer scheduling.

## Problem Statement

Kubernetes can populate a PVC from a data source, but the PVC must know that source before it binds. Existing backup tools generally require an explicit restore object, selected backup, UI action, CLI action, or per-app restore manifest.

That breaks this desired workflow:

```text
Git declares app + PVC
  |
  v
Cluster decides if old backup exists
  |
  +-- yes --> restore before app initializes state
  |
  +-- no --> create fresh for first install
  |
  +-- unknown --> block to avoid silent data loss
```

The current platform solves this with Kyverno, pvc-plumber, VolSync, and Kopia. It works conceptually, but it spreads one product across several loosely coupled mechanisms:

- Kyverno handles admission mutation and resource generation.
- pvc-plumber answers backup existence.
- VolSync performs backup/restore.
- Kopia stores backup data.
- Cleanup and status are indirect.

The real product is missing a dedicated API and controller.

## Goals

- Preserve one-label app ergonomics for common PVCs.
- Make backup truth tri-state and fail closed.
- Keep app pods from starting on empty volumes when backups exist or backup truth is unknown.
- Generate and reconcile VolSync resources automatically.
- Provide first-class status per protected PVC.
- Replace recurring unsafe Kopia maintenance assumptions.
- Support GitOps rebuilds without GUI, scripts, or comment toggles.
- Support 100+ apps without per-app restore manifests.

## Non-Goals

- Replace Longhorn.
- Replace VolSync.
- Replace Kopia.
- Replace database-native backups such as CNPG/Barman.
- Build a generic enterprise backup product with RBAC portals and multi-tenant billing.
- Make NFS/SMB active storage for SQLite apps.
- Guarantee application-level consistency across unrelated database and filesystem restore points.

## Current Architecture

```text
                 Git
                  |
                  v
              ArgoCD sync
                  |
                  v
        +--------------------+
        | PVC with backup    |
        | label              |
        +---------+----------+
                  |
                  v
        +--------------------+
        | Kyverno admission  |
        | validate + mutate  |
        +----+----------+----+
             |          |
             |          v
             |    +-------------+
             |    | pvc-plumber |
             |    | /exists     |
             |    +------+------+ 
             |           |
             |           v
             |        Kopia on NFS
             |
             v
   +-----------------------+
   | Kyverno generate      |
   | ExternalSecret        |
   | ReplicationSource     |
   | ReplicationDestination|
   +-----------+-----------+
               |
               v
            VolSync
```

Pre-hardening weakness that Phase 0 fixed:

```text
/readyz OK + /exists error -> exists false -> empty PVC
```

## Target Architecture

```text
                 Git
                  |
                  v
              ArgoCD sync
                  |
                  v
        +--------------------+
        | PVC with backup    |
        | label              |
        +---------+----------+
                  |
                  v
     +---------------------------+
     | protected-pvc admission   |
     | webhook                   |
     +------+---------+----------+
            |         |
            |         v
            |  +----------------+
            |  | Backup catalog |
            |  | cache          |
            |  +-------+--------+
            |          |
            |          v
            |       Kopia
            |
            v
   +------------------------------+
   | PVC admission decision       |
   | restore | fresh | deny       |
   +---------------+--------------+
                   |
                   v
     +----------------------------+
     | protected-pvc reconciler   |
     | creates/repairs VolSync    |
     | resources and status       |
     +-------------+--------------+
                   |
                   v
                VolSync
```

## Boxes And Arrows: Restore Path

```text
+--------------------------+
| Argo applies PVC         |
| backup: hourly          |
+------------+-------------+
             |
             v
+--------------------------+
| Admission webhook        |
| asks local catalog       |
+------------+-------------+
             |
             v
+--------------------------+
| Catalog says backup      |
| exists for ns/pvc        |
+------------+-------------+
             |
             v
+--------------------------+
| Webhook mutates PVC      |
| spec.dataSourceRef       |
+------------+-------------+
             |
             v
+--------------------------+
| Reconciler ensures       |
| ReplicationDestination   |
+------------+-------------+
             |
             v
+--------------------------+
| VolSync populates PVC    |
| from Kopia backup        |
+------------+-------------+
             |
             v
+--------------------------+
| PVC Bound                |
| app pod starts           |
+------------+-------------+
             |
             v
+--------------------------+
| Reconciler creates       |
| ReplicationSource after  |
| protectAfter delay       |
+--------------------------+
```

## Boxes And Arrows: Fresh Path

```text
+--------------------------+
| Argo applies new app PVC |
| backup: daily           |
+------------+-------------+
             |
             v
+--------------------------+
| Admission webhook        |
| checks catalog           |
+------------+-------------+
             |
             v
+--------------------------+
| Catalog authoritative:   |
| no backup exists         |
+------------+-------------+
             |
             v
+--------------------------+
| Webhook allows PVC       |
| unchanged                |
+------------+-------------+
             |
             v
+--------------------------+
| Longhorn creates fresh   |
| volume                   |
+------------+-------------+
             |
             v
+--------------------------+
| Reconciler creates       |
| backup resources         |
+--------------------------+
```

## Boxes And Arrows: Unknown Path

```text
+--------------------------+
| Argo applies PVC         |
| backup: hourly          |
+------------+-------------+
             |
             v
+--------------------------+
| Admission webhook        |
| checks catalog           |
+------------+-------------+
             |
             v
+--------------------------+
| Catalog stale or Kopia   |
| unavailable              |
+------------+-------------+
             |
             v
+--------------------------+
| Webhook denies PVC       |
| creation                 |
+------------+-------------+
             |
             v
+--------------------------+
| Argo retries             |
| app waits                |
+--------------------------+
```

## Before / After

| Area | Current | Controller target |
|---|---|---|
| App interface | `backup: hourly|daily` label | Same label, plus optional advanced annotations |
| Backup decision | pvc-plumber HTTP call from Kyverno | In-process admission webhook backed by catalog |
| Unknown backup truth | Hardened Kyverno + pvc-plumber denies | Always deny in webhook |
| Resource generation | Kyverno generate rules | Controller reconciler |
| Drift repair | Indirect, limited | Continuous reconcile |
| Status | Spread across PVC, Kyverno, VolSync | `PVCProtection` status per PVC |
| Cleanup | Kyverno cleanup policy | Owner refs/finalizers |
| Backup schedule | Top-of-hour herd | Deterministic staggering |
| Kopia catalog | Per-request CLI and short cache | Periodic indexed catalog with freshness condition |
| Monitoring | VolSync and pvc-plumber decision/error alerts | Controller, webhook, catalog, VolSync metrics |
| Migration risk | Current live path | Shadow/adopt mode before enforcement |

## Compare And Contrast For Design Review

| Option | What It Solves Well | What It Does Poorly | Operational Cost | Recommendation |
|---|---|---|---|---|
| Keep hardened Kyverno + pvc-plumber | Preserves one-label app UX, fixes silent empty-PVC initialization, and needs the least new code | Splits decision logic across Kyverno and a service; generated resource drift is not continuously reconciled; no first-class per-PVC protection status | Low | Use as the immediate production bridge |
| Build `protected-pvc-controller` | Centralizes admission, restore decisions, generated resources, status, cleanup, schedule staggering, and metrics | Requires CRDs, webhook lifecycle, RBAC, controller testing, leader election, and upgrade discipline | Medium | Target long-term architecture |
| Use VolSync VolumePopulator directly | Keeps the upstream restore primitive and avoids custom decision code | Requires PVCs to know the restore source; does not answer "backup exists or fresh install?" | Medium per app | Keep as the restore mechanism, not the decision layer |
| Use Longhorn backup restore directly | Simple for one-off volume recovery | Manual/GUI-oriented at scale; restore timing can happen after app initialization | High during incidents | Emergency-only fallback |
| Use Velero/Kasten-style restore workflow | Broad DR ecosystem and namespace/app-level restore concepts | Restore is an explicit operation; per-PVC conditional GitOps semantics are weak for this requirement | Medium to high | Useful comparison, not a replacement |

Reviewer criteria:

- Preserve the low-overhead app interface.
- Prevent empty initialization when backup truth is unknown.
- Distinguish first install from rebuild without comment toggles or clickops.
- Provide a migration path from today's manifests to the controller without a flag day.
- Add enough reconciliation/status value to justify owning a CRD and webhook.

## User Experience

### Common Case

Users keep writing normal PVCs:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: data
  namespace: karakeep
  labels:
    backup: "hourly"
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: longhorn
  resources:
    requests:
      storage: 10Gi
```

### Explicit Exemption

```yaml
metadata:
  labels:
    backup-exempt: "cache"
```

Allowed exemption reasons:

- `cache`
- `scratch`
- `external-source`
- `media-on-nas`
- `database-native`
- `test`

### Advanced Optional Overrides

```yaml
metadata:
  annotations:
    storage.vanillax.dev/protect-after: "2h"
    storage.vanillax.dev/restore-policy: "IfBackupExists"
    storage.vanillax.dev/unknown-policy: "Deny"
```

The common case should not need annotations.

## Proposed CRDs

### `PVCProtectionClass`

Cluster-scoped policy for a class such as `hourly` or `daily`.

```yaml
apiVersion: storage.vanillax.dev/v1alpha1
kind: PVCProtectionClass
metadata:
  name: hourly
spec:
  selector:
    matchLabels:
      backup: hourly
  restore:
    policy: IfBackupExists
    unknownPolicy: Deny
  backup:
    schedule:
      type: HashedHourly
    protectAfter: 2h
    retention:
      hourly: 24
      daily: 7
      weekly: 4
      monthly: 2
  volsync:
    copyMethod: Snapshot
    volumeSnapshotClassName: longhorn-snapclass
    storageClassName: longhorn
    cacheCapacity: 2Gi
  repositoryRef:
    name: kopia-nfs
```

Daily class:

```yaml
apiVersion: storage.vanillax.dev/v1alpha1
kind: PVCProtectionClass
metadata:
  name: daily
spec:
  selector:
    matchLabels:
      backup: daily
  restore:
    policy: IfBackupExists
    unknownPolicy: Deny
  backup:
    schedule:
      type: HashedDaily
      hour: 2
    protectAfter: 2h
    retention:
      hourly: 24
      daily: 7
      weekly: 4
      monthly: 2
  volsync:
    copyMethod: Snapshot
    volumeSnapshotClassName: longhorn-snapclass
    storageClassName: longhorn
    cacheCapacity: 2Gi
  repositoryRef:
    name: kopia-nfs
```

### `PVCBackupRepository`

Cluster-scoped backend config.

```yaml
apiVersion: storage.vanillax.dev/v1alpha1
kind: PVCBackupRepository
metadata:
  name: kopia-nfs
spec:
  type: KopiaFilesystem
  identity:
    sourceFormat: "{pvc}-backup@{namespace}:/data"
  secret:
    externalSecretStoreRef:
      kind: ClusterSecretStore
      name: 1password
    remoteRef:
      key: rustfs
      property: kopia_password
  filesystem:
    mount:
      nfs:
        server: 192.168.10.133
        path: /mnt/BigTank/k8s/volsync-kopia-nfs
      mountPath: /repository
  catalog:
    refreshInterval: 2m
    maxStaleness: 10m
```

### `PVCProtection`

Namespaced status object for one protected PVC. The controller may generate this automatically for every matching PVC, or users may create it explicitly later for advanced cases.

```yaml
apiVersion: storage.vanillax.dev/v1alpha1
kind: PVCProtection
metadata:
  name: data
  namespace: karakeep
spec:
  pvcName: data
  className: hourly
status:
  phase: Protected
  decision: Restore
  backup:
    source: data-backup@karakeep:/data
    latestSnapshotTime: "2026-04-28T06:00:00Z"
  generated:
    externalSecret: volsync-data
    replicationSource: data-backup
    replicationDestination: data-backup
  conditions:
    - type: CatalogReady
      status: "True"
      reason: Fresh
    - type: RestoreDecisionMade
      status: "True"
      reason: BackupFound
    - type: ReplicationDestinationReady
      status: "True"
      reason: ReadyForRestore
    - type: ReplicationSourceReady
      status: "True"
      reason: ScheduleActive
```

## Controller Components

### 1. Admission Webhook

Responsibilities:

- Intercept PVC CREATE.
- Match PVCs to a `PVCProtectionClass`.
- Query backup catalog.
- Mutate PVC with `dataSourceRef` when decision is `Restore`.
- Allow unchanged PVC when decision is `Fresh`.
- Deny PVC when decision is `Unknown`.
- Emit audit events and metrics for every decision.

The webhook must not shell out to Kopia per request in the steady state. It should query an in-process catalog cache that has a freshness condition.

### 2. Backup Catalog Manager

Responsibilities:

- Connect to the Kopia repository.
- Periodically run `kopia snapshot list --all --json`.
- Build an index keyed by `namespace/pvc`.
- Record latest snapshot time and source identity.
- Expose freshness to webhook readiness.
- Mark catalog unknown when refresh fails or exceeds max staleness.

Catalog rule:

```text
fresh catalog + source exists      -> Restore
fresh catalog + source missing     -> Fresh
stale catalog or refresh failure   -> Unknown
```

### 3. Resource Reconciler

Responsibilities:

- Watch PVCs, `PVCProtectionClass`, `PVCBackupRepository`, `ReplicationSource`, `ReplicationDestination`, and ExternalSecret resources.
- Create or repair ExternalSecret for Kopia credentials.
- Create or repair ReplicationDestination before restore PVC creation when possible.
- Create ReplicationSource only after PVC is Bound and older than `protectAfter`.
- Apply deterministic backup schedule staggering.
- Maintain `PVCProtection` status.

### 4. Cleanup Reconciler

Responsibilities:

- Remove generated VolSync resources when backup labels are removed.
- Respect backup retention policy.
- Never delete Kopia snapshots unless a future explicit destructive policy exists.
- Handle orphaned generated resources with owner references and finalizers.

### 5. Maintenance Reconciler

Responsibilities:

- Replace the hand-written recurring Kopia maintenance job.
- Run safe maintenance with default safety.
- Never schedule recurring `--safety=none`.
- Surface maintenance status and failures.

## Decision Model

| Decision | Meaning | Admission result |
|---|---|---|
| `Restore` | Authoritative backup exists | allow + mutate |
| `Fresh` | Authoritative no-backup result | allow unchanged |
| `Unknown` | Catalog stale, backend error, bad config, or ambiguous response | deny |

## Schedule Staggering

The controller should avoid herd behavior by default.

For hourly backups:

```text
minute = stable_hash(namespace + "/" + pvcName) % 60
schedule = "{minute} * * * *"
```

For daily backups:

```text
minute = stable_hash(namespace + "/" + pvcName) % 60
schedule = "{minute} 2 * * *"
```

This keeps the user contract simple while spreading load.

## Status Phases

| Phase | Meaning |
|---|---|
| `PendingDecision` | PVC seen, catalog decision not ready |
| `Blocked` | PVC creation denied because decision is unknown |
| `CreatingFresh` | No backup exists, normal PVC allowed |
| `Restoring` | Backup exists, PVC created with `dataSourceRef` |
| `Bound` | PVC is bound |
| `Protected` | Backup schedule exists and is healthy |
| `Degraded` | Backup resources exist but one is unhealthy |
| `Disabled` | PVC is explicitly exempt or label removed |

## Failure Handling

| Failure | Behavior |
|---|---|
| Controller not ready | webhook denies matching PVCs by failurePolicy `Fail` |
| Catalog stale | deny matching PVC CREATE |
| Kopia unavailable | deny matching PVC CREATE |
| VolSync unavailable | PVC may be created with restore source but remain Pending; status Degraded |
| ExternalSecret missing | status Degraded; reconcile retries |
| Backup label removed | stop generating new backup jobs; preserve repository data |
| Class missing | deny matching PVC and report configuration error |

## Observability Requirements

Metrics:

- admission decisions by class and decision
- catalog refresh success/failure
- catalog age
- generated resource drift count
- restore duration
- backup duration
- unknown decision count
- maintenance success/failure

Events:

- `BackupFound`
- `NoBackupFound`
- `BackupTruthUnknown`
- `RestoreMutationApplied`
- `GeneratedResourceRepaired`
- `BackupScheduleCreated`
- `MaintenanceFailed`

Prometheus alerts:

| Alert | Condition |
|---|---|
| `ProtectedPVCWebhookDown` | webhook unavailable |
| `ProtectedPVCCatalogStale` | catalog older than max staleness |
| `ProtectedPVCUnknownDecisions` | unknown decisions above 0 |
| `ProtectedPVCResourceDrift` | generated resource drift persists |
| `ProtectedPVCRestoreStuck` | restore PVC pending beyond threshold |
| `ProtectedPVCMaintenanceFailed` | maintenance job failed |

## Security Requirements

- Controller runs with least privilege.
- Admission webhook only mutates PVC `dataSourceRef` and protection annotations.
- Controller owns only generated ExternalSecret, ReplicationSource, ReplicationDestination, and `PVCProtection` status.
- Kopia password remains sourced from External Secrets.
- No app namespace gets broad repository credentials beyond what VolSync already needs.
- Webhook failure policy is `Fail` for protected PVCs.

## Migration Plan

### Phase 0: Harden Current Flow

- Fix pvc-plumber tri-state. Status: implemented in the hardening pass.
- Enforce Kyverno unknown denial. Status: implemented in the hardening pass.
- Remove recurring `--safety=none`. Status: implemented in the hardening pass.
- Add monitoring. Status: implemented in the hardening pass.

The controller should treat Phase 0 behavior as the compatibility contract for
observe/shadow mode. If the controller disagrees with pvc-plumber on
`restore`, `fresh`, or `unknown`, the controller is wrong until proven
otherwise by a restore drill.

### Phase 1: Observe Mode

Install controller with webhooks disabled.

Controller watches PVCs and writes `PVCProtection` status only:

```text
Kyverno still performs current behavior.
Controller only reports what it would have done.
```

Success criteria:

- Controller decisions match pvc-plumber decisions.
- No generated resources are modified.
- Catalog stays fresh across normal backup load.

### Phase 2: Reconcile Mode

Enable controller resource reconciliation, but leave Kyverno mutation in place.

Controller creates/repairs:

- ExternalSecret
- ReplicationSource
- ReplicationDestination
- PVCProtection status

Kyverno generate rules are disabled only after parity is proven.

### Phase 3: Admission Shadow Mode

Enable webhook in audit/shadow mode if possible, or log-only mode:

- webhook computes decision
- Kyverno still mutates
- compare decisions

### Phase 4: Admission Enforce Mode

Controller webhook becomes the admission authority:

- Kyverno mutation disabled
- pvc-plumber no longer used for admission
- controller denies unknown backup truth

### Phase 5: Cleanup

- Remove old Kyverno backup/restore policy.
- Keep or replace NFS mover injection depending on VolSync support.
- Retire pvc-plumber.
- Keep docs and runbooks updated.

## Rollout Diagram

```text
Phase 0
  Current Kyverno + pvc-plumber, hardened
      |
      v
Phase 1
  Controller observes only
      |
      v
Phase 2
  Controller reconciles generated resources
      |
      v
Phase 3
  Controller webhook shadows Kyverno
      |
      v
Phase 4
  Controller webhook enforces decisions
      |
      v
Phase 5
  Kyverno backup policy and pvc-plumber retired
```

## Acceptance Criteria

P0:

- Existing `backup: hourly|daily` labels continue to work.
- No-backup first install still creates fresh PVCs.
- Existing-backup rebuild restores before app pod starts.
- Unknown backup truth denies PVC creation.
- Controller publishes per-PVC status.
- Generated VolSync resources are reconciled.
- Backup schedules are staggered.
- Kopia maintenance uses default safety.

P1:

- Audit policy reports ambiguous Longhorn RWO PVCs missing backup or exemption.
- Restore drills can be launched against disposable namespaces.
- Controller can adopt existing Kyverno-generated resources.
- Multiple controller replicas can serve admission safely.

P2:

- Optional explicit `PVCProtection` authoring for advanced apps.
- StatefulSet template helper for charts that do not expose PVC labels.
- Repository-server backend mode if VolSync Kopia support allows it cleanly.
- Backup age SLOs per class.

## Test Plan

| Test | Expected |
|---|---|
| Fresh app PVC | Admission allows unchanged PVC |
| Existing backup PVC | Admission adds `dataSourceRef` |
| Catalog stale | Admission denies |
| Kopia unavailable | Admission denies |
| Controller pod down | Kubernetes admission fails closed |
| Generated ExternalSecret deleted | Controller recreates it |
| ReplicationDestination deleted | Controller recreates it |
| PVC Bound for 2h | ReplicationSource created |
| Backup label removed | Generated resources cleaned up, snapshots retained |
| 50 protected PVCs applied | Schedules are distributed across minutes |
| Restore drill | App does not start until PVC is bound |

## Open Technical Questions

These should be answered during implementation design:

1. Should the first controller version keep Kyverno NFS mover injection, or replace it with controller-managed mutation?
2. Should `PVCProtection` be generated for every matching PVC, or only created explicitly for advanced cases?
3. Should the catalog be in-memory per replica, persisted in a CR status, or both?
4. Can the perfectra1n VolSync Kopia fork cleanly support a repository-server mode?
5. How should StatefulSet `volumeClaimTemplates` be handled for charts that do not expose labels?

## Recommendation

Build the controller, but do not jump straight to it.

The safest path is:

```text
Harden current flow first
  |
  v
Introduce controller in observe mode
  |
  v
Move reconciliation from Kyverno to controller
  |
  v
Move admission from Kyverno/pvc-plumber to controller
```

This preserves the working system while replacing the fragile parts one boundary at a time.
