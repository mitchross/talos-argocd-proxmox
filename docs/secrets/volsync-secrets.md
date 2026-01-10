# VolSync Secrets Setup

## ✅ Fully Automated via Kyverno

**You only need ONE 1Password item - Kyverno auto-generates everything else!**

## Required 1Password Item

### rustfs

Create a **Password** item in your 1Password vault:

| Field | Value |
|-------|-------|
| **Item name** | `rustfs` |
| **access_key** | RustFS access key |
| **secret_key** | RustFS secret key |
| **restic_password** | A strong random password (32+ characters) |
| **restic_repository** | `s3:http://192.168.10.133:30292/volsync-backup/` |

The `restic_password` encrypts all backup repositories stored in S3.

The `restic_repository` is the S3 endpoint - each PVC will have its namespace and name appended automatically.

**Generate a secure password:**
```bash
openssl rand -base64 32
```

Example output: `K7x9mP2nL4qR8vT1wY5zA3cF6hJ0bN+dG=`

**That's it!** When you add `backup: "hourly"` or `backup: "daily"` to a PVC, Kyverno automatically:
1. Generates an ExternalSecret pulling from the `rustfs` 1Password item
2. Creates a Kubernetes Secret with S3 credentials
3. No manual YAML creation needed!

## Verification

After creating the `rustfs` item and labeling PVCs, verify auto-generated ExternalSecrets:

```bash
# Check all auto-generated ExternalSecrets (Kyverno created these!)
kubectl get externalsecret -A | grep volsync

# View a specific auto-generated ExternalSecret
kubectl get externalsecret karakeep-data-volsync-secret -n karakeep -o yaml
```

All ExternalSecrets should show `SecretSynced` status.

## S3 Bucket Setup

Ensure the `volsync-backup` bucket exists in RustFS (192.168.10.133:30292):

| Bucket | Purpose |
|--------|---------|
| `volsync-backup` | VolSync PVC backups (Restic repositories) |

Create it if it doesn't exist:
```bash
mc alias set rustfs http://192.168.10.133:30292 <access_key> <secret_key>
mc mb rustfs/volsync-backup
```

## Auto-Generated Secret Structure

Kyverno generates an ExternalSecret for each labeled PVC that creates:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: <pvc-name>-volsync-secret
  namespace: <pvc-namespace>
type: Opaque
stringData:
  RESTIC_REPOSITORY: s3:http://192.168.10.133:30292/volsync-backup/<namespace>-<pvc>
  RESTIC_PASSWORD: <from 1Password rustfs.restic_password>
  AWS_ACCESS_KEY_ID: <from 1Password rustfs.access_key>
  AWS_SECRET_ACCESS_KEY: <from 1Password rustfs.secret_key>
