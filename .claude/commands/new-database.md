Create a new CNPG (CloudNativePG) database for `$ARGUMENTS`.

## Steps

1. Create directory: `infrastructure/database/cloudnative-pg/<app-name>/`

2. Create `cluster.yaml`:
   ```yaml
   apiVersion: postgresql.cnpg.io/v1
   kind: Cluster
   metadata:
     name: <app>-database
     namespace: cloudnative-pg
   spec:
     instances: 1
     imageName: ghcr.io/cloudnative-pg/postgresql:16.2
     bootstrap:
       initdb:
         database: <app>
         owner: <app>
     storage:
       size: 20Gi
       storageClass: longhorn
     backup:
       barmanObjectStore:
         serverName: <app>-database
         destinationPath: s3://postgres-backups/cnpg/<app>
         endpointURL: http://192.168.10.133:30293
         s3Credentials:
           accessKeyId:
             name: cnpg-s3-credentials
             key: AWS_ACCESS_KEY_ID
           secretAccessKey:
             name: cnpg-s3-credentials
             key: AWS_SECRET_ACCESS_KEY
       retentionPolicy: "14d"
   ```

3. Create `kustomization.yaml` listing all resources

4. Database AppSet auto-discovers via `infrastructure/database/*/*` glob — no need to add paths to `infrastructure-appset.yaml`

## Critical Rules

- DO NOT add Kyverno backup labels to CNPG PVCs (Barman handles database backups via S3)
- `serverName` must be bumped after each DR recovery (e.g. `-v2`, `-v3`)
- Recovery cannot go through ArgoCD (SSA + CNPG webhook conflict)
- See `docs/cnpg-disaster-recovery.md` for DR procedures

## Reference

- Existing database: `infrastructure/database/cloudnative-pg/immich/`
- DR procedures: `docs/cnpg-disaster-recovery.md`
