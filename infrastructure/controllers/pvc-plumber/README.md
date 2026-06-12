# pvc-plumber v4.0.1 Core Deployment

This directory deploys pvc-plumber `v4.0.1` in permissive mode at Wave `2`.

## Current Role

pvc-plumber watches opted-in application PVCs and owns their VolSync
`ReplicationSource` and `ReplicationDestination` resources. VolSync and Kopia
move bytes. pvc-plumber does not replace them.

The v4 write path is bounded by:

1. Namespace software gate: `pvc-plumber.io/managed-namespace: "true"`.
2. PVC fuse labels: `pvc-plumber.io/enabled: "true"` and
   `pvc-plumber.io/manage-volsync: "true"`.
3. RS/RD ownership checks.
4. A cluster-wide VolSync writer binding scoped to RS/RD resources.

v4 is permissive. It does not mutate PVCs, Secrets, ExternalSecrets, or ArgoCD
Applications. It has no admission webhook and no Kyverno dependency.

## Bootstrap Boundary

Core renders only the controller resources needed for bootstrap. Monitoring
resources are intentionally absent:

- no `ServiceMonitor`
- no `PrometheusRule`
- no monitoring CRD dependency
- no vestigial adoption or nginx-example RBAC

Observability belongs in later overlays after `kube-prometheus-stack` owns the
`monitoring.coreos.com` CRDs.

The Argo Application has automated sync disabled. A deliberate manual sync is
required after a full cluster rebuild because pvc-plumber holds cluster-wide
VolSync writer privileges.

## Current Proven State

- pvc-plumber `v4.0.1`
- `24` operator-managed PVCs
- `18` managed namespaces
- `24/24 DR_COMPLETE` before the full cluster nuke

Redis and PostHog are backup-exempt and disposable. CNPG uses native Barman/S3.

## Verify Render

```bash
kustomize build infrastructure/controllers/pvc-plumber
```

The core render must contain no `monitoring.coreos.com` resources.

## Related Docs

- [`docs/storage-architecture.md`](../../../docs/storage-architecture.md)
- [`docs/storage-architecture.md`](../../../docs/storage-architecture.md)
- [`docs/storage-architecture.md`](../../../docs/storage-architecture.md)
- [`docs/disaster-recovery.md`](../../../docs/disaster-recovery.md)
