# VolSync Storage Recovery

This is the current storage recovery reference for application PVCs managed by pvc-plumber v4.

## Current State

- pvc-plumber `v4.0.1` is the shipped and proven operator.
- `24` operator-managed PVCs across `18` namespaces reached `DR_COMPLETE` before the full cluster nuke.
- Redis and PostHog are backup-exempt and disposable.
- CNPG uses its native Barman/S3 path. Do not generic-migrate CNPG PVCs.
- Kyverno is not part of the backup path.

## Responsibility Boundaries

pvc-plumber owns the VolSync wiring: `ReplicationSource` and `ReplicationDestination` resources, restore intent, and `/audit` status. VolSync and Kopia move bytes. Longhorn provides live storage. RustFS/S3 stores backup data.

pvc-plumber core has no Prometheus dependency. Monitoring resources belong in later observability overlays.

## Protected PVC Contract

A normal application PVC is managed only when all of these are true:

- The namespace opts in with `pvc-plumber.io/managed-namespace: "true"`.
- The PVC opts in with `pvc-plumber.io/enabled: "true"`.
- The PVC enables operator wiring with `pvc-plumber.io/manage-volsync: "true"`.
- The PVC declares a supported tier with `pvc-plumber.io/tier`.
- The PVC has a static `dataSourceRef` whose name matches `<pvc-name>-dst`.
- The namespace has the shared VolSync/Kopia credentials expected by the operator.

The operator is permissive in v4: unmanaged PVCs continue to work. There is no admission webhook and no Kyverno mutation path.

## Bootstrap Boundary

The restore order is:

1. Install storage and VolSync controllers.
2. Install pvc-plumber core at Wave `2`.
3. Allow pvc-plumber to reconcile `ReplicationSource` and `ReplicationDestination` resources.
4. Add observability later. ServiceMonitor and PrometheusRule resources are not core dependencies.

Follow the complete sequence in [cluster DR nuke restore runbook](cluster-dr-nuke-restore-runbook.md).

## Restore Drill

Before recreating a protected PVC:

1. Confirm the latest backup is successful and recent enough for the application.
2. Confirm the expected `ReplicationDestination` exists.
3. Quiesce the workload.
4. Recreate the PVC through GitOps with its static `dataSourceRef`.
5. Verify the PVC binds and the workload returns with expected data.
6. Verify pvc-plumber `/audit` reports the PVC as complete.

Do not use this generic path for CNPG, Redis, or PostHog.

## External Dependency Check

Before a destructive rebuild, verify RustFS/S3 reachability, the registered S3 access key, and Kopia repository authentication. A full cluster nuke proved that an unregistered external credential blocks recovery even when the Git state is correct.

## Related Docs

- [pvc-plumber start here](pvc-plumber-start-here.md)
- [pvc-plumber cheatsheet](pvc-plumber-cheatsheet.md)
- [pvc-plumber dynamic workflow](pvc-plumber-dynamic-workflow.md)
- [Talos ArgoCD pvc-plumber integration](talos-argocd-pvc-plumber-integration.md)
- [CNPG disaster recovery](domains/cnpg/disaster-recovery.md)
