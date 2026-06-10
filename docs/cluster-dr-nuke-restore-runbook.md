# Cluster Nuke / Rebuild / Restore Runbook

> [!CAUTION]
> Do not execute destructive steps without explicit operator authorization.
> This runbook records the verified post-nuke rebuild path; it is not an instruction to rebuild during routine maintenance.

The full cluster nuke and rebuild on `2026-06-01` exposed bootstrap ordering bugs that were hidden by an already-running cluster. This runbook captures the corrected path for pvc-plumber `v4.0.1`, VolSync/Kopia, CNPG native Barman/S3, and optional observability.

## Non-Negotiable Bootstrap Rules

```text
CRDs first, controllers/apps second, CRs third.
```

```text
Observability is not a core dependency.
Core apps must not render monitoring.coreos.com resources.
If deleting Prometheus breaks restore/bootstrap, the repo is wrong.
```

Do not install Prometheus Operator CRDs early just to satisfy bootstrap apps. Split `ServiceMonitor`, `PrometheusRule`, and related resources into later observability overlays instead. `kube-prometheus-stack` remains the sole owner and provider of `monitoring.coreos.com` CRDs.

## Full-Nuke Findings

The rebuild proved and corrected these ordering problems:

- pvc-plumber Wave `2` now renders bootstrap-core only. ServiceMonitor, PrometheusRule, vestigial adopt RBAC, nginx-example RBAC, stale comments, and vestigial `SkipDryRunOnMissingResource` guidance were removed from core.
- cert-manager moved to Wave `1`, before the Wave `3` CNPG Barman plugin.
- KEDA core no longer renders ServiceMonitor resources. `keda-observability` owns them at Wave `6`.
- OpenTelemetry operator core no longer renders a ServiceMonitor. `opentelemetry-operator-observability` owns it at Wave `6`.
- CNPG `enablePodMonitor: true` is accepted runtime soft-coupling. The CNPG operator may log transient errors before monitoring exists, but this is not an ArgoCD dry-run blocker.
- RustFS/S3 external credential registration and Kopia repository authentication must be validated before a nuke.
- Temporal's post-nuke bootstrap deadlock is **fixed and applied** (do not re-plan it): the `temporal-db-secret` ExternalSecret/shims carry sync-wave `-2`, the Helm-rendered schema Jobs are ArgoCD Sync hooks at wave `-1` (`my-apps/development/temporal/`). The hook Job can now mount its dependencies before it runs.
- The `volsync-mover-backend-availability` **MutatingAdmissionPolicy** (Wave `2`, `infrastructure/storage/volsync-backup-cluster/`) is the backup-path admission gate: it injects a `wait-for-rustfs` init container into every VolSync mover Job, `failurePolicy: Fail`, scoped to mover Jobs only. It is **cluster infrastructure, separate from pvc-plumber** — the v4 operator ships no admission webhook. Failure mode to respect: a broken policy silently stops **all backups** (not deploys); dry-run it after every Kubernetes upgrade and watch `VolSyncMissedScheduledBackup`.

An early Prometheus Operator CRD application was considered and explicitly rejected. Do not resurrect it.

## Acceptance Result (2026-06-02) — PASS

The full nuke/rebuild/restore was executed end-to-end and **passed**. pvc-plumber `v4.0.1` survived a full Omni/Talos cluster destroy+recreate and restored every protected PVC from Git + VolSync/Kopia.

- **24/24 operator-managed PVCs** (18 namespaces) recreated, `Bound`, with `dataSourceRef → <pvc>-dst`, and RS+RD `managed-by=pvc-plumber`.
- **24/24 post-restore backups `result=Successful`.** The final 3 (`immich/library`, `project-nomad/qdrant-data`, `swarmui/swarmui-output`) initially wedged on a degraded VolSync snapshot-clone (`OfflineRebuildingInProgress`) and were recovered by the clone-bounce procedure (pause RS → delete wedged mover + ephemeral `volsync-*-src` clone → Longhorn GCs the degraded volume → unpause → manual sync → restore cron). Real app PVCs/UIDs were never touched. See [VolSync storage recovery](volsync-storage-recovery.md).
- `/audit`: `already-matches=24`, `managed-by-pvc-plumber=24`, `would-adopt/create/update/delete=0`, `write-gate-missing=0`, `stale=false`. *(This acceptance quoted only the managed-contract counters — see "Audit acceptance semantics" below; future acceptance runs must also quote `needs-human-review`.)*
- CNPG native clusters (gitea/immich/paperless/temporal) healthy `1/1` (Barman/S3, never generic-migrated). Redis + PostHog backup-exempt and unmanaged.
- Longhorn healthy (4/4 nodes schedulable), RustFS external on TrueNAS survived, `root` Synced/Healthy.
- **No early empty backup overwrote good data** — every backup ran after its restore.

This proves the contract end-to-end: Git/Argo recreate apps → PVCs recreate with `dataSourceRef` → VolSync populator restores from the matching RD → pvc-plumber recreates/verifies RS/RD ownership → apps return on restored data → backups resume.

### Audit acceptance semantics

"`/audit` clean" is two distinct claims; acceptance must state both:

1. **Managed restore contract clean** — every operator-managed PVC is
   `already-matches` with `managed-by=pvc-plumber`, and
   `would-create/update/delete=0`, `write-gate-missing=0`, `stale=false`.
   This is the DR-critical criterion: it proves managed PVCs restore on
   recreate.
2. **Global audit hygiene clean** — `needs-human-review=0` across ALL
   PVCs the report covers, including unmanaged ones. A non-zero count is
   not a restore failure, but it is unresolved operator findings (label
   contract violations, ambiguous ownership) that mask real problems and
   must be quoted, triaged, and either fixed or explained.

History: the 2026-06-02 managed-PVC acceptance passed for 24/24. The
2026-06-09 independent review then found 2 **unmanaged** monitoring PVCs
(`prometheus-stack` Prometheus + Alertmanager) sitting in
`needs-human-review` because their exemption reason used the bare
`backup-exempt-reason` key instead of the fully-qualified
`storage.vanillax.dev/backup-exempt-reason`. That was audit hygiene, not
a managed restore failure — but it went unnoticed precisely because
acceptance only quoted the managed-contract counters. Fixed in
`monitoring/prometheus-stack/values.yaml` the same day.

### Continuous proof layer — scheduled restore canary

The 2026-06-02 acceptance was a point-in-time proof. The
[scheduled restore canary](restore-canary.md) (`my-apps/system/restore-canary/`
+ `scripts/restore-canary-drill.sh`) keeps re-proving the restore path
between nukes: sentinel → forced backup → RD `latestImage` refresh → delete
only the canary PVC → Git/Argo recreate with `dataSourceRef` → populator
restore → byte-correct sha256 verification. Drill results land as
`restore-canary.vanillax.dev/last-drill-*` annotations on the
`restore-canary` namespace.

## Verified Pre-Nuke State

Before the rebuild:

- pvc-plumber `v4.0.1` was the shipped and proven operator.
- `24` operator-managed PVCs across `18` namespaces reached `DR_COMPLETE`.
- Redis and PostHog were accepted backup-exempt, disposable data.
- CNPG used native Barman/S3 and was excluded from generic pvc-plumber migration.
- Kyverno was removed from the backup path, CRDs, policies, and webhooks.
- Longhorn reached `0` faulted, `0` degraded, and `0` rebuilding volumes.
- Kopia maintenance was healthy. Manual full maintenance was not required.

## Pre-Nuke External Dependency Checklist

Block the nuke until all external dependencies are verified:

- [ ] GitHub is reachable.
- [ ] GHCR image pulls work.
- [ ] 1Password is reachable.
- [ ] The 1Password Connect token is valid and recoverable off-cluster.
- [ ] The Cloudflare token is valid and recoverable off-cluster.
- [ ] The RustFS/S3 endpoint is reachable.
- [ ] The RustFS/S3 access key is registered and valid on the external RustFS server.
- [ ] Kopia repository authentication works.
- [ ] Talos secrets and machine configs are available off-cluster.
- [ ] Proxmox, Omni, and infrastructure-as-code inputs are available.
- [ ] The restore canary is green: `scripts/restore-canary-drill.sh` passes its
      gates and the `restore-canary` namespace shows a recent
      `last-drill-result=pass` (see [restore canary](restore-canary.md)).

Also record the Git revision to rebuild from and verify that the latest pvc-plumber audit is fully `DR_COMPLETE` for every managed PVC **and** `needs-human-review=0` (see "Audit acceptance semantics" above — counts are dynamic; verify against the live `/audit`, not a remembered number).

## What Survives

Outside the cluster:

- GitHub repository state.
- GHCR images.
- 1Password vault data.
- Cloudflare configuration.
- RustFS/S3 Kopia repository.
- CNPG Barman/S3 backup objects.
- Proxmox, Omni, Talos secrets, and machine configuration inputs.

Inside the cluster and expected to be lost:

- Longhorn working volumes.
- Kubernetes objects recreated by GitOps and operators.
- Redis data.
- PostHog data.

## Current Restore Waves

| Wave | Applications | Restore role |
|---|---|---|
| `0` | ArgoCD projects/bootstrap, Cilium, 1Password Connect, External Secrets | Networking, GitOps, and secret foundation |
| `1` | cert-manager, Longhorn, snapshot-controller, VolSync | CRDs and controllers needed before storage consumers |
| `2` | pvc-plumber core, VolSync backup-cluster wiring | Operator-managed RS/RD wiring and shared Kopia credentials |
| `3` | CNPG Barman plugin | Native database backup plugin before CNPG clusters |
| `4` | KEDA core, Temporal worker, infrastructure and database AppSets | Core infrastructure and databases |
| `5` | OpenTelemetry operator core, monitoring AppSet including `kube-prometheus-stack` | Monitoring CRD owner arrives after core bootstrap |
| `6` | KEDA observability, OpenTelemetry operator observability, workload AppSet | Optional monitoring CRs and application workloads |

cert-manager is deliberately Wave `1`. pvc-plumber Wave `2` is deliberately core-only. KEDA and OpenTelemetry observability overlays are deliberately Wave `6`.

## Rebuild Procedure

### 1. Recreate Talos

Use the normal Omni, Proxmox, and infrastructure-as-code path. Confirm nodes are `Ready` and the Kubernetes API is reachable before installing cluster applications.

### 2. Seed Networking And ArgoCD

Install the bootstrap CNI path, seed 1Password credentials, run:

```bash
./scripts/bootstrap-argocd.sh
```

Then apply the root application:

```bash
kubectl apply -f infrastructure/controllers/argocd/root.yaml
```

### 3. Watch Wave 0

Confirm Cilium, ArgoCD, 1Password Connect, and External Secrets converge. Validate the 1Password-backed secret store before allowing later waves to depend on it.

### 4. Watch Wave 1

Confirm cert-manager, Longhorn, snapshot-controller, and VolSync are healthy. This is the controller layer required by storage consumers and the CNPG Barman plugin.

### 5. Sync pvc-plumber Wave 2

pvc-plumber remains manual-sync by design because it owns cluster-wide VolSync writer privileges. Sync it once after a nuke, then confirm pvc-plumber core and VolSync backup-cluster wiring converge.

Do not add monitoring resources to make this step green. pvc-plumber core must bootstrap without Prometheus.

### 6. Watch CNPG And Core Infrastructure

Confirm the Wave `3` CNPG Barman plugin and Wave `4` infrastructure/database applications converge. CNPG restores follow [CNPG disaster recovery](domains/cnpg/disaster-recovery.md), not the generic pvc-plumber path.

### 7. Add Monitoring Later

At Wave `5`, `kube-prometheus-stack` installs and owns `monitoring.coreos.com` CRDs. At Wave `6`, KEDA and OpenTelemetry observability overlays may install their monitoring resources.

Core applications must remain healthy if monitoring is absent.

### 8. Validate Application Restores

For pvc-plumber-managed application storage:

1. Confirm the namespace and PVC opt-in labels are present.
2. Confirm pvc-plumber owns the expected `ReplicationSource` and `ReplicationDestination`.
3. Confirm the PVC restores through its static `dataSourceRef`.
4. Confirm the workload returns with expected data.
5. Confirm `/audit` reports the PVC as complete.

Use [VolSync storage recovery](volsync-storage-recovery.md) for the application PVC workflow.

## App Restore Validation

Before declaring the rebuild complete:

- [ ] pvc-plumber reports `24` managed PVCs across `18` namespaces.
- [ ] pvc-plumber reports `24/24 DR_COMPLETE`.
- [ ] Redis is present only as backup-exempt disposable data.
- [ ] PostHog is present only as backup-exempt disposable data.
- [ ] CNPG restores use native Barman/S3 only.
- [ ] No Kyverno CRDs, policies, or webhooks are required by the backup path.
- [ ] Core apps bootstrap without Prometheus.
- [ ] `kube-prometheus-stack` remains the sole provider of `monitoring.coreos.com` CRDs.
- [ ] KEDA and OpenTelemetry monitoring resources live only in later observability overlays.

## Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| Early ArgoCD dry-run failure for `monitoring.coreos.com` | A core app renders observability CRs | Move those resources to a later observability overlay |
| CNPG Barman plugin blocked before Wave `3` | cert-manager is not healthy at Wave `1` | Fix cert-manager; do not move it later |
| VolSync/Kopia mover authentication failure | RustFS/S3 key not registered or Kopia auth invalid | Validate the external RustFS key and Kopia repository credentials |
| CNPG PodMonitor reconciliation errors before monitoring | Accepted runtime soft-coupling | Allow monitoring CRDs to arrive at Wave `5`; do not add early CRDs |
| pvc-plumber workload restores blocked after Wave `2` | pvc-plumber manual sync not approved or shared credentials missing | Sync pvc-plumber and verify backup-cluster wiring |

## Related Docs

- [docs index](index.md)
- [ArgoCD entrypoints](domains/argocd/entrypoints.md)
- [ArgoCD architecture](domains/argocd/argocd.md)
- [VolSync storage recovery](volsync-storage-recovery.md)
- [pvc-plumber start here](pvc-plumber-start-here.md)
- [CNPG disaster recovery](domains/cnpg/disaster-recovery.md)
