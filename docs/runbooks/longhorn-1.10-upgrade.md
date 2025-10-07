# Longhorn 1.10 Upgrade Runbook

This runbook captures the exact prechecks and commands required to safely upgrade Longhorn to v1.10.x in this cluster.

Important highlights from the v1.10.0 release notes:
- Kubernetes must be >= 1.25
- The Longhorn v1beta1 API was removed. If your cluster ever stored Longhorn CRs in v1beta1 (likely if you originally installed < v1.3.0), you MUST migrate CR storage to v1beta2 before upgrading.
- Some defaultSettings support per-engine JSON. A known 1.10.0 bug can affect boolean DataEngineSpecific values when sourced via Helm values. We keep these as simple scalars unless we actively use V2.

## Pre-checks
- Ensure Kubernetes >= 1.25 across the cluster.
- Confirm ArgoCD will install CRDs during Helm upgrade (kustomization includesCRDs: true).
- Optionally snapshot/backup critical workloads.

## Mandatory: CRD storage version migration (before upgrading)
Before the migration, fix legacy CRD conversion blocks that can break CRD applies during upgrade.

1) Fix CRD conversion blocks (older installs sometimes leave webhookClientConfig while strategy isn't Webhook):

```
./scripts/longhorn-fix-crd-conversion.sh
```

2) Run the helper script to migrate any Longhorn CRDs that still have v1beta1 storedVersions to v1beta2.

Steps (requires kubectl + jq):
1) Pause Longhorn syncs in ArgoCD (optional but recommended during migration window).
2) Run the script:

```
./scripts/longhorn-v110-crd-migration.sh
```

3) Verify all Longhorn CRDs show only v1beta2 in storedVersions:

```
kubectl get crd -l app.kubernetes.io/name=longhorn -o=jsonpath='{range .items[*]}{.metadata.name}{": "}{.status.storedVersions}{"\n"}{end}'
```
Expected: every line shows ["v1beta2"]. If any show v1beta1, re-run the script or investigate.

## Upgrade via ArgoCD
- Chart version is pinned to 1.10.0 in `infrastructure/storage/longhorn/kustomization.yaml`.
- Values are managed in `infrastructure/storage/longhorn/values.yaml`.
- Pre-upgrade checker job is disabled to avoid GitOps drift (`preUpgradeChecker.jobEnabled: false`).

Sync the Longhorn app in ArgoCD. Wait for all pods in `longhorn-system` to become Ready.

## Post-upgrade checks
- Pods healthy:
  - longhorn-manager, longhorn-ui, longhorn-csi-plugin, csi-* sidecars, instance-manager, engine-image, share-manager
- Longhorn UI reachable (via existing Gateway/HTTPRoute)
- Create a test PVC, attach to a test pod, write small data, and verify persistence.
- Recurring jobs present (from `recurring-jobs.yaml`).
- Backup target is detected (S3/MinIO) and can list/create a small backup.

## Rollback guidance (only if upgrade fails early)
If you skipped the migration and upgraded, managers may fail with CRD storedVersions errors. Follow the v1.10 release notes to temporarily patch the webhook and downgrade to the exact previous 1.9.x, then perform the migration script above and retry the upgrade.

Reference:
- Release notes: https://github.com/longhorn/longhorn/releases/tag/v1.10.0
- Install with Helm Controller (context for K3s/RKE2): https://longhorn.io/docs/1.10.0/deploy/install/install-with-helm-controller/
