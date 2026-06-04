Create a new CNPG (CloudNativePG) database for `$ARGUMENTS`.

## Steps

1. Create or update the shared source under
   `manifests/database/cloudnative-pg/<app-name>/`.
2. Create the Talos deploy target under
   `clusters/talos/database/cloudnative-pg/<app-name>/`, following an existing
   database such as `immich`.
3. Create `kustomization.yaml` files that list every resource.
4. Add the deploy target's `.argocd/config.json` so the Talos database AppSet
   discovers it through `clusters/talos/database/*/*/.argocd/config.json`.
5. Validate the native Barman/S3 configuration and credentials.

## Critical Rules

- CNPG uses native Barman/S3. Do not generic-migrate CNPG PVCs to pvc-plumber.
- Do not add pvc-plumber fuse labels or generic VolSync RS/RD resources to CNPG PVCs.
- Keep the CNPG Barman plugin dependency after cert-manager: cert-manager is Wave `1`, plugin is Wave `3`.
- Bump `serverName` after DR recovery when the CNPG runbook requires a new lineage.
- Follow [`docs/domains/cnpg/disaster-recovery.md`](../../docs/domains/cnpg/disaster-recovery.md) for recovery.

## Reference

- Existing source: `manifests/database/cloudnative-pg/immich/`
- Existing deploy target: `clusters/talos/database/cloudnative-pg/immich/`
- DR procedures: [`docs/domains/cnpg/disaster-recovery.md`](../../docs/domains/cnpg/disaster-recovery.md)
