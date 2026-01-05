# VolSync Secrets Setup

## Required 1Password Items

Before VolSync backups will work, you need the `rustfs` item in 1Password.

### rustfs

Create a **Password** item in your 1Password vault:

| Field | Value |
|-------|-------|
| **Item name** | `rustfs` |
| **access_key** | RustFS access key |
| **secret_key** | RustFS secret key |
| **restic_password** | A strong random password (32+ characters) |

The `restic_password` encrypts all backup repositories stored in S3.

**Generate a secure password:**
```bash
openssl rand -base64 32
```

Example output: `K7x9mP2nL4qR8vT1wY5zA3cF6hJ0bN+dG=`

## Verification

After creating the `rustfs` item, verify the ExternalSecrets are syncing:

```bash
# Check app-level secrets (example)
kubectl get externalsecret -n home-assistant

# View secret details
kubectl get externalsecret home-assistant-volsync-secret -n home-assistant -o yaml
```

All ExternalSecrets should show `SecretSynced` status.

## S3 Bucket Setup

Ensure the `volsync` bucket exists in RustFS (192.168.10.133:30292):

| Bucket | Purpose |
|--------|---------|
| `volsync` | VolSync PVC backups (Restic repositories) |

Create it if it doesn't exist:
```bash
mc alias set rustfs http://192.168.10.133:30292 <access_key> <secret_key>
mc mb rustfs/volsync
```

## Secret Structure

Each app has an ExternalSecret that creates a Secret with this structure:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: <app>-volsync-secret
type: Opaque
stringData:
  RESTIC_REPOSITORY: s3:http://192.168.10.133:30292/volsync/<app>
  RESTIC_PASSWORD: <from 1Password rustfs.restic_password>
  AWS_ACCESS_KEY_ID: <from 1Password rustfs.access_key>
  AWS_SECRET_ACCESS_KEY: <from 1Password rustfs.secret_key>
