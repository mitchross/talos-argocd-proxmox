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

- CNPG backs up via the **Barman Cloud Plugin** to S3/RustFS (`spec.plugins[]` +
  an `ObjectStore` CR), NOT the deprecated in-tree `barmanObjectStore` (removed
  in CNPG 1.30.0). This is a **separate** backup system from kopiur.
- **Never add kopiur backup CRs** (`SnapshotPolicy`/`SnapshotSchedule`/`Restore`)
  to CNPG database PVCs — they use Barman/S3, not kopiur.
- Use the **overlay feature-flag** pattern: root `kustomization.yaml` activates
  one of `overlays/initdb` (steady state — fresh DB) or `overlays/recovery` (DR).
  After a recovery, flip back to `overlays/initdb`.
- Keep the CNPG Barman plugin dependency after cert-manager: cert-manager is Wave `1`, plugin is Wave `3`.
- Bump `serverName` (the S3 lineage) after DR recovery when the runbook requires a new lineage.

## Reference

- Existing database: `infrastructure/database/cloudnative-pg/immich/`
- **Beginner guide (backup/restore/start, diagrams):** [`docs/domains/cnpg/backup-restore-start-guide.md`](../../docs/domains/cnpg/backup-restore-start-guide.md)
- Full DR runbook: [`docs/domains/cnpg/disaster-recovery.md`](../../docs/domains/cnpg/disaster-recovery.md)
- Repo rules + current lineage table: [`infrastructure/database/CLAUDE.md`](../../infrastructure/database/CLAUDE.md)
