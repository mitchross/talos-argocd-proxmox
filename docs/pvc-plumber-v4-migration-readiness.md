# pvc-plumber v4 Migration Readiness

The v4 migration campaign is closed.

## Final Verified State

| Item | State |
|---|---|
| Operator | pvc-plumber `v4.0.1`, permissive |
| Managed PVCs | `24` |
| Managed namespaces | `18` |
| DR completeness before full cluster nuke | `24/24 DR_COMPLETE` |
| Redis | backup-exempt and disposable |
| PostHog | backup-exempt and disposable |
| CNPG | native Barman/S3, never generic-migrate |
| Kyverno | removed from backup path, CRDs, policies, and webhooks |
| Longhorn before nuke | `0` faulted, `0` degraded, `0` rebuilding |
| Kopia maintenance | healthy; manual full maintenance not required |

## New PVCs

Use [Talos ArgoCD pvc-plumber integration](talos-argocd-pvc-plumber-integration.md)
for the current add-a-PVC checklist. Do not follow the historical migration
campaign prompts for new work.

## Historical Record

The final campaign snapshot is preserved at
[historical migration readiness](archive/pvc-plumber/migration-campaign/pvc-plumber-v4-migration-readiness-final.md).
