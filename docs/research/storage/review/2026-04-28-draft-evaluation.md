# Draft Storage Architecture Evaluation

Date: 2026-04-28

Status: draft for review with post-hardening updates noted.

## Executive Verdict

The core architecture is justified.

This repo is not reinventing storage, backup, or restore. It is adding a missing restore-intent layer on top of normal Kubernetes primitives:

- Longhorn provisions and snapshots app-private block PVCs.
- VolSync + Kopia performs backup and restore.
- Kyverno turns a PVC label into the required VolSync resources.
- pvc-plumber answers the one question existing tools do not answer at PVC admission time: "does this PVC already have a backup?"
- ArgoCD sync waves make sure the restore decision layer exists before application PVCs are admitted.

I did not find a current free/open tool that provides the full behavior you want:

> PVC appears declaratively from Git, backup existence is checked before binding, restore happens if data exists, empty provisioning happens if no backup exists, and unknown state fails closed.

That is the important gap. VolSync, KubeStash, Velero, K8up, Longhorn, Kasten, OADP, and Portworx solve adjacent backup/restore problems, but they do not remove the restore-intent decision in the exact way this repo does.

The initial implementation was close, but two things needed to be fixed before calling it production-like:

1. Admission must fail closed when pvc-plumber cannot prove backup truth.
2. Routine Kopia maintenance must stop using `--safety=none` unless the platform also guarantees no concurrent repository operations.

Post-hardening update:

- pvc-plumber now publishes tri-state `restore|fresh|unknown` decisions and returns HTTP 503 for unknown backend truth.
- The active Kyverno bridge now denies backup-labeled PVC creation when pvc-plumber cannot make an authoritative decision.
- Routine Kopia maintenance no longer runs recurring `--safety=none`.
- pvc-plumber has ServiceMonitor and alert coverage.
- The dead, unwired CEL Kyverno policies were removed.
- The restore-pending alert now matches protected PVCs by the real `backup` label instead of an unproven `volumeattributesclass` metric label.

## Platform Bar

The right target is not "homelab clever." The right target is "managed-platform boring":

- safe default behavior
- declarative operation
- repeatable rebuilds
- no GUI restore ritual
- no per-app snowflake scripts
- visible failure instead of silent empty-state boot
- enough observability that the custom layer does not become folklore

Under that bar, the architecture should keep fail-closed semantics. If backup truth is unknown, PVC creation should be denied. A denied PVC is noisy and recoverable. An app initializing a fresh SQLite database over a missed restore is quiet data loss.

## What Is Strong

The backup label interface is the right abstraction. It keeps app manifests simple while making backup/restore behavior declarative.

The admission-time decision is correctly placed. `dataSourceRef` has to exist before the PVC binds; an init container or post-start restore would be too late for apps that initialize state on first boot.

VolSync VolumePopulator is the right restore primitive. It holds the PVC pending until data is populated, so pods do not start against partially restored data.

The ArgoCD waves are load-bearing and mostly well modeled. Storage, VolSync, pvc-plumber, and Kyverno are intentionally before user workloads. Custom Argo health checks support that sequencing.

The Kyverno performance guardrails are important and should stay:

- `background: false`
- `mutateExistingOnPolicyUpdate: false`
- `generate.synchronize: false`

The previous Kyverno outage is already accounted for with infrastructure namespace exclusions and an emergency webhook cleanup script.

The actual PVC estate mostly matches the design. I found 48 explicit PVC manifests outside vendored Helm charts, 25 of them backup-labeled, plus 2 backup-labeled StatefulSet volume claim templates. The unlabeled PVCs are mostly caches, media, model storage, or static NFS/SMB claims, with a few app-state candidates that should be explicitly classified.

## Main Risks

### 1. Fail-Closed Semantics Were Weaker Than The Docs Claim

Initial finding: the included policy was the old combined `ClusterPolicy`, not the newer `ValidatingPolicy` and `MutatingPolicy`.

The included `ClusterPolicy` set `validationFailureAction: Audit`, while the docs described a deny gate. Current Kyverno docs say Audit records the violation but allows the resource.

pvc-plumber also returned HTTP 200 with `exists:false` on Kopia command and JSON parse errors. Kyverno only mutated when `exists == true`; it did not deny when the response contained an error.

This is now hardened. The platform rule is:

> `exists=true` means restore, `exists=false` with no error means create fresh, and any error/unknown/unreachable state means deny PVC admission.

### 2. pvc-plumber Readiness Is Cheap, Not Fully Authoritative

`/readyz` verifies that startup Kopia connect succeeded and the repository path still `stat()`s. That is better than process-only health, but it does not prove the next Kopia query can list snapshots.

This is acceptable only if per-PVC `/exists` errors are treated as admission failures. If `/exists` errors continue to become `exists:false`, the system still has a fail-open path.

### 3. The Current VolSync Kopia Stack Uses A Fork

The repo uses `ghcr.io/perfectra1n/volsync:v0.17.11` for Kopia support. Upstream Backube VolSync still has Kopia support as an open PR at the time of review.

That does not mean the fork is wrong. It does mean this is not a boring upstream dependency yet. Pinning, upgrade caution, and restore drills matter.

### 4. Kopia Maintenance Currently Uses An Unsafe Routine Mode

The maintenance CronJob runs `kopia maintenance run --full --safety=none`. Kopia's own maintenance docs warn that this disables safety features and requires no concurrent repository operations.

The repo does not currently encode that guarantee. Kyverno generates hourly backup schedules at `0 * * * *`, and the maintenance CronJob runs at `0 3 * * *`, so it can overlap with hourly backup writers at 03:00 UTC.

This should be changed before focusing on prettier architecture:

- stop using `--safety=none` for routine maintenance
- stop forcing daily full maintenance unless there is measured need
- let Kopia's normal safety windows do their job
- optionally schedule maintenance away from the biggest backup window, but do not depend on scheduling alone for safety

### 5. Backup Schedules Create A Small Thundering Herd

The current Kyverno policy maps all `hourly` PVCs to `0 * * * *` and all `daily` PVCs to `0 2 * * *`. With the current inventory, that means 7 hourly explicit PVCs and 18 daily explicit PVCs can bunch up, plus chart/StatefulSet claims.

This is not fatal at today's scale, but enterprise-like behavior would eventually add deterministic staggering or a low-overhead opt-in label for heavy PVCs.

### 6. Observability Is Incomplete Around The Custom Decision Layer

pvc-plumber exposes `/metrics`, but I did not find a ServiceMonitor or alert for it.

VolSync alerts exist. The restore-pending rule was changed to alert on protected PVCs using `kube_persistentvolumeclaim_labels{label_backup=~"hourly|daily"}` because that label is part of the platform contract.

For a managed-platform feel, the custom admission oracle should have first-class health signals:

- pvc-plumber unavailable
- pvc-plumber backup-check errors
- sudden rise in `exists:false` during rebuild
- Kyverno policy not ready
- ReplicationSource missing for labeled PVC
- ReplicationDestination missing for labeled PVC

### 7. Database/PVC Temporal Skew Remains Application-Specific

The split between CNPG/Barman for Postgres and VolSync/Kopia for PVCs is correct. But apps using both can restore database and filesystem state from different times.

That is not solved generically by any storage tool. It needs per-app classification: some apps tolerate skew, some need one tier treated as canonical, and some need app-specific backup hooks or recovery notes.

## Alternatives Considered

### Portworx

Portworx is the closest enterprise mental model: storage, backup, mobility, DR, policy, support. Current public pages present Enterprise and Backup as free trials, not a permanent free/community path. It is a useful benchmark, not a replacement for this repo's constraints.

### Longhorn Native Backup

Good for explicit backup/restore. It does not provide admission-time conditional restore intent.

### Velero / OADP

Good for explicit cluster or namespace restore workflows. Still restore-object driven, not plain-PVC conditional create-time behavior.

### KubeStash

Has a Kubernetes-native VolumePopulator restore path, but the PVC explicitly references a specific KubeStash `Snapshot`. It still does not provide "backup exists? decide automatically."

### K8up

Useful operator-driven Restic backups and restore jobs. Restore remains explicit.

### Plain VolSync VolumePopulator

Closest upstream primitive, but it needs `dataSourceRef` up front. If no snapshot/latest image exists, the PVC waits. That breaks the new-app first-deploy case unless you add a decision layer.

## Recommended Direction

Keep the architecture. Harden the boundary where the custom decision layer meets admission control.

Priority order:

1. Make backup truth tri-state: `exists`, `not_found`, `unknown_error`.
2. Ensure `unknown_error` denies PVC admission.
3. Change Kopia maintenance to default safety; do not use `--safety=none` as routine maintenance.
4. Move from legacy `ClusterPolicy` toward the newer Kyverno CEL policy types where practical, or at minimum set rule-level enforce semantics on the legacy policy.
5. Add pvc-plumber ServiceMonitor and alerts.
6. Add a reconciliation/drift check that finds labeled PVCs missing generated ExternalSecret, ReplicationSource, or ReplicationDestination.
7. Stagger backup schedules if restore/backup drills show concentrated load.
8. Run and document one destructive restore drill for a small app and one larger PVC.
9. Keep Portworx/Kasten/Velero/OADP as comparison points, not replacement candidates.

## Suggested End-State Policy Contract

The admission contract should be explicit:

| pvc-plumber result | Admission result | PVC result |
|---|---|---|
| backup exists | allow + mutate | VolSync restores before bind |
| no backup exists, check succeeded | allow unchanged | Longhorn creates fresh volume |
| pvc-plumber unreachable | deny | ArgoCD retries |
| Kopia/NFS/query error | deny | ArgoCD retries |
| malformed response | deny | ArgoCD retries |

This gives the enterprise-like behavior you want: a rebuild may pause, but it should not silently choose the unsafe path.

The maintenance contract should also be explicit:

| Repository state | Maintenance behavior |
|---|---|
| routine daily/weekly maintenance | use Kopia default safety |
| emergency compaction with `--safety=none` | only manual/exception path with verified no writers |
| hourly/daily backups may be running | never run unsafe GC |

## Draft Bottom Line

Your custom system is defensible because the missing piece is not backup mechanics; it is restore intent. The Kubernetes ecosystem has backup engines and restore engines, but it still does not have a free, mainstream, declarative conditional PVC restore primitive.

The best simplification is not replacing pvc-plumber. The best simplification is making pvc-plumber's contract sharper, making Kyverno enforce that contract more directly, and removing unsafe Kopia maintenance assumptions.

## Sources Checked

- Kyverno policy types overview: <https://kyverno.io/docs/policy-types/overview/>
- Kyverno validate failure action semantics: <https://kyverno.io/docs/policy-types/cluster-policy/validate/>
- Kyverno CEL HTTP library: <https://kyverno.io/docs/policy-types/cel-libraries/>
- ArgoCD sync waves: <https://argo-cd.readthedocs.io/en/latest/user-guide/sync-waves/>
- VolSync VolumePopulator: <https://volsync.readthedocs.io/en/stable/usage/volume-populator/index.html>
- Backube VolSync Kopia PR: <https://github.com/backube/volsync/pull/1723>
- perfectra1n VolSync Kopia docs: <https://perfectra1n.github.io/volsync/usage/kopia/index.html>
- Kopia repositories: <https://kopia.io/docs/repositories/>
- Kopia repository server: <https://kopia.io/docs/repository-server/>
- Kopia maintenance safety: <https://kopia.io/docs/advanced/maintenance/>
- Longhorn restore from backup: <https://longhorn.io/docs/1.10.1/snapshots-and-backups/backup-and-restore/restore-from-a-backup/>
- Velero restore reference: <https://velero.io/docs/v1.18/restore-reference/>
- KubeStash volume populator PVC restore: <https://kubestash.com/docs/v2025.7.31/guides/volume-populator/pvc/>
- K8up restore docs: <https://docs.k8up.io/k8up/2.15/how-tos/restore.html>
- CloudNativePG recovery: <https://cloudnative-pg.io/docs/1.26/recovery/>
- Portworx pricing/features: <https://portworx.com/pricing-and-features/>
