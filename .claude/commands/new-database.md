Create a new CNPG (CloudNativePG) database for `$ARGUMENTS`.

## Steps

1. Create `infrastructure/database/cloudnative-pg/<app-name>/`.
2. Copy the current CNPG cluster and plugin pattern from an existing
   application such as `infrastructure/database/cloudnative-pg/immich/`.
3. Create `kustomization.yaml` listing every resource.
4. Confirm the database AppSet discovers the directory through
   `infrastructure/database/*/*`.
5. Validate the native Barman/S3 configuration and credentials.

## Critical Rules

- CNPG uses native Barman/S3. Do not generic-migrate CNPG PVCs to pvc-plumber.
- Do not add pvc-plumber fuse labels or generic VolSync RS/RD resources to CNPG PVCs.
- Keep the CNPG Barman plugin dependency after cert-manager: cert-manager is Wave `1`, plugin is Wave `3`.
- Bump `serverName` after DR recovery when the CNPG runbook requires a new lineage.
- Follow [`docs/domains/cnpg/disaster-recovery.md`](../../docs/domains/cnpg/disaster-recovery.md) for recovery.

## Reference

- Existing database: `infrastructure/database/cloudnative-pg/immich/`
- DR procedures: [`docs/domains/cnpg/disaster-recovery.md`](../../docs/domains/cnpg/disaster-recovery.md)
