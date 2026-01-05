# VolSync Secrets Setup

## Required 1Password Items

Before VolSync backups will work, you need to create one new item in 1Password.

### volsync-kopia

Create a new **Password** item in your 1Password vault:

| Field | Value |
|-------|-------|
| **Item name** | `volsync-kopia` |
| **Field name** | `password` |
| **Value** | A strong random password (32+ characters) |

This password encrypts all Kopia/Restic backup repositories stored in S3.

**Generate a secure password:**
```bash
openssl rand -base64 32
```

Example output: `K7x9mP2nL4qR8vT1wY5zA3cF6hJ0bN+dG=`

### Existing Items Used

The VolSync configuration also uses your existing `minio` item:

| Item | Fields Used |
|------|-------------|
| `minio` | `minio_access_key`, `minio_secret_key` |

These should already exist from your Longhorn backup configuration.

## Verification

After creating the `volsync-kopia` item, verify the ExternalSecrets are syncing:

```bash
# Check VolSync system secret
kubectl get externalsecret -n volsync-system

# Check app-level secrets (example)
kubectl get externalsecret -n home-assistant
```

All ExternalSecrets should show `SecretSynced` status.

## S3 Bucket Setup

Ensure these buckets exist in your RustFS/MinIO (192.168.10.133):

| Bucket | Purpose |
|--------|---------|
| `volsync-backups` | VolSync PVC backups (Kopia repositories) |
| `postgres-backups` | CNPG and Crunchy database backups |

Create them if they don't exist:
```bash
mc mb truenas/volsync-backups
mc mb truenas/postgres-backups
```
