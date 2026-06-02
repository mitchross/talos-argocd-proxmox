# pvc-plumber v4 Cutover Reference

The v4 cutover campaign is complete. pvc-plumber `v4.0.1` is the shipped and
proven operator. This page records the current contract for new PVCs and links
to the archived day-of campaign runbook.

## Current Contract

For a normal application PVC:

1. Add `pvc-plumber.io/managed-namespace: "true"` to the namespace.
2. Add `volsync.backube/privileged-movers: "true"` to the namespace.
3. Add PVC labels `pvc-plumber.io/enabled: "true"`,
   `pvc-plumber.io/manage-volsync: "true"`, and `pvc-plumber.io/tier`.
4. Keep a static `dataSourceRef` to `ReplicationDestination/<pvc-name>-dst`.
5. Verify pvc-plumber owns the RS/RD pair and `/audit` reports the PVC complete.

There is no per-namespace RoleBinding step. v4.0.1 uses the cluster-wide
`ClusterRoleBinding pvc-plumber:volsync-writer`.

## Exclusions

- CNPG uses native Barman/S3.
- Redis is backup-exempt and disposable.
- PostHog is backup-exempt and disposable.

## Related Docs

- [Talos ArgoCD pvc-plumber integration](talos-argocd-pvc-plumber-integration.md)
- [VolSync storage recovery](volsync-storage-recovery.md)
- [historical day-of cutover campaign](archive/pvc-plumber/migration-campaign/pvc-plumber-v4-cutover-campaign.md)
