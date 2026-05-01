# Current PVC Restore Flow Hardening Plan

Date: 2026-04-28

Status: implemented hardening plan; live-cluster restore drills still required.

## Goal

Make the current Kyverno + pvc-plumber + VolSync + Kopia design production-grade before replacing it with a controller.

The goal is not "perfect" in the abstract. The goal is this concrete invariant:

> A backup-labeled PVC must never be created empty when backup truth is unknown.

## Current Risky Path

Today, the intended flow is correct, but one failure mode is unsafe.

```text
PVC CREATE
  |
  v
Kyverno validate checks /readyz
  |
  | /readyz is OK because repo path stat() works
  v
Kyverno mutate checks /exists/ns/pvc
  |
  | Kopia query fails, parse fails, or repo is inconsistent
  v
pvc-plumber returns HTTP 200:
  { "exists": false, "error": "failed to list snapshots" }
  |
  v
Kyverno sees exists != true
  |
  v
PVC is created without dataSourceRef
  |
  v
App starts on empty volume
```

That path violates the platform contract. It treats "I could not prove backup state" as "no backup exists."

## Target Safe Path

```text
PVC CREATE
  |
  v
Backup-labeled PVC?
  |
  +-- no --> normal Kubernetes PVC flow
  |
  +-- yes
       |
       v
     Check backup truth
       |
       +-- backup exists --------> mutate PVC with dataSourceRef -> restore
       |
       +-- no backup, check OK --> create normal PVC -> fresh app
       |
       +-- unknown/error -------> deny PVC admission -> Argo retries
```

## Admission Contract

| pvc-plumber result | HTTP result | Kyverno behavior | Outcome |
|---|---:|---|---|
| Backup exists | 200 | allow + mutate | VolSync restores before bind |
| No backup exists, check succeeded | 200 | allow unchanged | Longhorn creates fresh volume |
| pvc-plumber unavailable | no response / 5xx | deny | Argo retries |
| Kopia query error | 503 | deny | Argo retries |
| Kopia JSON parse error | 503 | deny | Argo retries |
| NFS/repository uncertain | 503 | deny | Argo retries |
| Invalid request path | 400 | deny for backup-labeled PVC | caller bug surfaced |

## Immediate Change Set

### 1. Make pvc-plumber tri-state

Current logical model:

```text
exists: true | false
error: string
```

Target logical model:

```text
decision: restore | fresh | unknown
authoritative: true | false
exists: true | false
error: string
```

Keep `exists` for backwards compatibility, but make `authoritative` and `decision` the real contract.

Suggested response examples:

```json
{
  "namespace": "karakeep",
  "pvc": "data-pvc",
  "backend": "kopia-fs",
  "decision": "restore",
  "authoritative": true,
  "exists": true,
  "source": "data-pvc-backup@karakeep:/data",
  "error": ""
}
```

```json
{
  "namespace": "new-app",
  "pvc": "data",
  "backend": "kopia-fs",
  "decision": "fresh",
  "authoritative": true,
  "exists": false,
  "source": "data-backup@new-app:/data",
  "error": ""
}
```

```json
{
  "namespace": "paperless-ngx",
  "pvc": "media",
  "backend": "kopia-fs",
  "decision": "unknown",
  "authoritative": false,
  "exists": false,
  "source": "media-backup@paperless-ngx:/data",
  "error": "failed to list snapshots: exit status 1"
}
```

Implementation notes:

- `/exists` should return 200 only for authoritative `restore` or `fresh`.
- `/exists` should return 503 for backend/query/parse uncertainty.
- Invalid path should stay 400.
- `HTTP_TIMEOUT` should wrap the per-request backend call. The existing Kopia executor already uses `exec.CommandContext`; it needs a request context with a deadline.
- Error results should never be cached.
- Fresh negative results may be cached briefly, but the default TTL should remain conservative.

### 2. Make Kyverno deny unknown backup truth

Keep the current legacy `ClusterPolicy` for the immediate fix, because it already owns resource generation. Do not partially switch to the newer CEL policies until the behavior is tested.

Required changes:

- Use rule-level `validate.failureAction: Enforce`, or change the policy-level fallback to `validationFailureAction: Enforce`.
- Add a validation rule that calls `/exists` for backup-labeled PVCs and denies when:
  - `authoritative != true`
  - `decision == "unknown"`
  - `error != ""`
  - the service call defaulted because pvc-plumber was unavailable
- Keep mutation only for authoritative restore:
  - `authoritative == true`
  - `decision == "restore"`
  - `exists == true`
  - no existing `dataSourceRef`

The important part is that the deny rule and mutate rule agree on the same decision model.

### 3. Keep `/readyz` cheap but stop trusting it as proof

The current `/readyz` behavior is fine as a liveness/readiness gate:

- startup Kopia connect succeeded
- repository path can be stat'ed

Do not make `/readyz` run expensive Kopia list commands on every kubelet probe. That caused false-negative readiness before.

Instead:

- `/readyz` means "service is ready to answer."
- `/exists` means "this specific PVC backup truth is authoritative."

### 4. Make Kopia maintenance safe

Current routine maintenance uses:

```text
kopia maintenance run --full --safety=none
```

That is not a safe routine platform default. Kopia docs warn that `--safety=none` disables safety checks and requires no concurrent operations.

Immediate target:

```text
kopia maintenance run
```

Optional weekly full maintenance with default safety:

```text
kopia maintenance run --full
```

Recommended schedule:

| Job | Schedule | Command |
|---|---|---|
| Daily quick/normal maintenance | off the top of the hour, for example `37 3 * * *` | `kopia maintenance run` |
| Weekly full maintenance | off the top of the hour, for example `17 4 * * 0` | `kopia maintenance run --full` |
| Emergency unsafe GC | manual only | `kopia maintenance run --full --safety=none` |

Do not encode unsafe GC in GitOps as a recurring job.

### 5. Add pvc-plumber monitoring

pvc-plumber is on the admission safety path. Treat it like control-plane software.

Minimum metrics:

| Metric | Type | Labels | Purpose |
|---|---|---|---|
| `pvc_plumber_backup_check_total` | counter | `decision`, `backend` | Restore/fresh/unknown counts |
| `pvc_plumber_backup_check_errors_total` | counter | `backend`, `error_class` | Alert on backend failures |
| `pvc_plumber_backup_check_duration_seconds` | histogram | `backend`, `decision` | Catch slow Kopia queries |
| `pvc_plumber_cache_hit_total` | counter | `result` | See cache effectiveness |
| `pvc_plumber_catalog_last_refresh_timestamp_seconds` | gauge | `backend` | Detect stale catalog |

Minimum alerts:

| Alert | Condition | Severity |
|---|---|---|
| `PVCPlumberDown` | `up{job="pvc-plumber"} == 0` for 2m | critical |
| `PVCPlumberBackupCheckErrors` | error rate above 0 for 5m during normal operation | warning |
| `PVCPlumberUnknownDecisions` | unknown decisions above 0 during app sync | critical |
| `PVCPlumberSlowChecks` | p95 check duration above Kyverno timeout budget | warning |

### 6. Add resource drift checks

Every backup-labeled PVC should have:

- ExternalSecret `volsync-{pvc}`
- Secret `volsync-{pvc}`
- ReplicationDestination `{pvc}-backup`
- ReplicationSource `{pvc}-backup` after PVC is Bound and old enough

Near term, this can be a PrometheusRule or a periodic report. Longer term, the controller should own this status directly.

### 7. Add explicit backup classification

The current `backup: hourly|daily` label is good, but there is no guard against forgetting it on a Longhorn RWO app-state PVC.

Recommended policy in phases:

| Phase | Behavior |
|---|---|
| Audit | Report Longhorn RWO PVCs with neither `backup` nor `backup-exempt` |
| Enforce for new apps | Require either `backup` or `backup-exempt` on app namespaces |
| Enforce broadly | Block ambiguous persistent app PVCs |

Suggested exemption label:

```yaml
metadata:
  labels:
    backup-exempt: "cache"
```

Allowed reasons:

- `cache`
- `external-source`
- `media-on-nas`
- `database-native`
- `test`
- `scratch`

### 8. Stagger later, not first

The top-of-hour backup herd is real, but it is not the first correctness problem.

Current generated schedules:

| Label | Schedule |
|---|---|
| `backup: hourly` | `0 * * * *` |
| `backup: daily` | `0 2 * * *` |

After correctness is fixed, add deterministic staggering:

```text
minute = stable_hash(namespace + "/" + pvc) % 60
```

This is awkward in Kyverno, but easy in the future controller.

## Implementation Order

1. Change pvc-plumber response semantics.
2. Add pvc-plumber tests for restore, fresh, and unknown.
3. Add request timeout use of `HTTP_TIMEOUT`.
4. Change Kyverno policy to enforce unknown/error denial.
5. Test with a disposable PVC and a mocked or intentionally broken backend.
6. Change Kopia maintenance to default safety.
7. Add ServiceMonitor and alerts.
8. Add audit-only backup classification policy.
9. Run destructive restore drills.

## Required Tests

| Test | Expected result |
|---|---|
| New app, no backup | PVC creates without `dataSourceRef` |
| Existing backup | PVC creates with `dataSourceRef` |
| pvc-plumber down | PVC admission denied |
| Kopia command error | PVC admission denied |
| Kopia invalid JSON | PVC admission denied |
| `/readyz` OK but `/exists` error | PVC admission denied |
| Restore PVC pending | App pod does not start until PVC binds |
| Remove backup label | generated resources are cleaned up |

## Rollback Plan

If the stricter policy blocks too much during rollout:

1. Scale affected apps down or pause affected Argo Applications.
2. Temporarily set the new unknown-deny rule to Audit only.
3. Keep the pvc-plumber response changes, because they are backwards compatible if `exists` remains.
4. Fix the backend issue.
5. Re-enable Enforce.

Do not roll back to treating backend errors as `exists:false` during an actual rebuild.

## Definition Of Done

- A backup-labeled PVC cannot be created when pvc-plumber is down.
- A backup-labeled PVC cannot be created when Kopia lookup errors.
- A new app with no backup still creates fresh.
- An app with an existing backup restores before bind.
- Kopia maintenance no longer runs recurring `--safety=none`.
- pvc-plumber is scraped and alerted.
- One small and one large restore drill are documented.

## Implementation Update

Applied in code/manifests:

- pvc-plumber tri-state response model.
- `/exists` HTTP 503 for unknown backend truth.
- per-request `HTTP_TIMEOUT`.
- `pvc_plumber_backup_check_total{backend,decision}` metrics.
- Kyverno Enforce denial for non-authoritative backup decisions.
- Kyverno restore mutation gated on authoritative `decision=restore`.
- Kopia recurring maintenance changed to default safety.
- pvc-plumber released as `v1.5.1` and Talos pinned to `ghcr.io/mitchross/pvc-plumber:1.5.1`.
- pvc-plumber ServiceMonitor and alerts.
- Restore pending alert changed to `ProtectedPVCPendingTooLong` keyed off `backup=hourly|daily` PVC labels instead of an unproven `volumeattributesclass` metric.
- Dead/unwired Kyverno CEL `ValidatingPolicy` and `MutatingPolicy` files deleted; the active bridge remains the combined `ClusterPolicy` until controller webhook migration.
- Infographic flow docs in both repos.

Still required before calling the platform fully proven:

- Live disposable PVC drill for `fresh`.
- Live disposable PVC drill for `restore`.
- Live pvc-plumber-down admission denial test.
- Live Kopia query error admission denial test.
