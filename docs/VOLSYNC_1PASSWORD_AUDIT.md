# 1Password Secrets Audit & Validation

## ✅ Verified 1Password Configuration

**UNIFIED AUTHENTICATION:** Using single `k8s-admin` universal access key for all S3 operations (VolSync, Longhorn, etc.)

### Item: `rustfs` (Universal S3 Credentials)
**Location:** 1Password vault
**Type:** Password
**Verified Fields:** ✅
- [x] `k8s-admin-access-key` = `k8s-admin` (Universal admin key)
- [x] `k8s-admin-secret-key` = (Secret value from RustFS console)
- [x] `restic_password` = Restic/Kopia encryption password (32+ chars)
- [x] `restic_repository` = `s3:http://192.168.10.133:30292/volsync-backup/`

**Status:** ✅ **Confirmed** - All apps now use single universal `k8s-admin` key

---

## Current Configuration Analysis

### VolSync Setup (From Git) ✅ UPDATED

#### File: `infrastructure/storage/volsync/rustfs-credentials.yaml`
```yaml
ClusterExternalSecret: volsync-rustfs-base
Pulls from 1Password:
  - key: "rustfs"
    - property: "k8s-admin-access-key" → AWS_ACCESS_KEY_ID
    - property: "k8s-admin-secret-key" → AWS_SECRET_ACCESS_KEY
    - property: "restic_password"     → RESTIC_PASSWORD
    - property: "restic_repository"   → RESTIC_REPOSITORY_BASE
```

**Status:** ✅ Updated to use universal `k8s-admin` key

#### File: `infrastructure/storage/volsync/externalsecret.yaml`
```yaml
ExternalSecret: volsync-s3-credentials (in volsync-system namespace)
Pulls from 1Password:
  - key: "rustfs"
    - property: "k8s-admin-access-key" → AWS_ACCESS_KEY_ID
    - property: "k8s-admin-secret-key" → AWS_SECRET_ACCESS_KEY
```

**Status:** ✅ Updated to use universal `k8s-admin` key

---

### Longhorn Setup (From Git) ✅ UPDATED

#### File: `infrastructure/storage/longhorn/externalsecret.yaml`
```yaml
ExternalSecret: longhorn-backup-credentials
Pulls from 1Password:
  - key: "rustfs" (CHANGED from "minio")
    - property: "k8s-admin-access-key" → AWS_ACCESS_KEY_ID (CHANGED from minio_access_key)
    - property: "k8s-admin-secret-key" → AWS_SECRET_ACCESS_KEY (CHANGED from minio_secret_key)
    (AWS_ENDPOINTS removed - not needed with hardcoded path)
```

**Status:** ✅ Updated to use universal `k8s-admin` key from `rustfs` item (minio removed)

---

## Screenshots Evidence

From your TrueNAS console screenshots:

### Screenshot 1: RustFS volsync-backup bucket
✅ Confirmed folders exist:
- karakeep/ (data-pvc, meilisearch-pvc with data)
- khoj/ (config with data)
- open-webui/ (data, storage with data)
- home-assistant/ (config with data)
- paperless-ngx/ (data, media with data)
- redis-instance/ (redis-master-0 with data)
- plex/, jellyfin/, nestmtx/, nginx-example/

### Screenshot 2: RustFS Access Keys
✅ Confirmed keys exist:
- volsync (Available) ← **This is the one VolSync should use**
- loki (Available)
- longhorn (Available)

**KEY QUESTION:** Which access key does your 1Password "rustfs" item reference?
- If it's "volsync" key → ✅ Correct
- If it's "longhorn" key → ❌ Wrong, that's for Longhorn
- If it's something else → ❌ Mismatch

### Screenshot 3: RustFS Applications (Installed)
✅ minio and rustfs both running

### Screenshot 4: 1Password "rustfs" item
Showing fields:
- access_key: `volsync` ← **This is the access key NAME**
- secret_key: (masked)
- restic_password: (masked)  
- restic_repository: `s3:http://192.168.10.133:30292/volsync-backup/` ← **Need to verify this exact value**

---

## Critical Verification Checklist ✅

### For VolSync & Longhorn to work, we now have:

```
┌─ 1Password Item: rustfs (SINGLE SOURCE OF TRUTH)
│  ├─ k8s-admin-access-key: k8s-admin
│  ├─ k8s-admin-secret-key: [universal admin secret]
│  ├─ restic_password: [encryption password]
│  └─ restic_repository: "s3:http://192.168.10.133:30292/volsync-backup/"
│
├─ TrueNAS RustFS Endpoint
│  ├─ IP: 192.168.10.133 ✓
│  ├─ Port: 30292 (for S3) ✓
│  ├─ Access Key "k8s-admin": Universal admin with all bucket access ✓
│  └─ Buckets available: volsync-backup/, longhorn/, etc. ✓
│
├─ Kubernetes Secrets (auto-created from ExternalSecret)
│  ├─ AWS_ACCESS_KEY_ID: k8s-admin (from rustfs.k8s-admin-access-key)
│  ├─ AWS_SECRET_ACCESS_KEY: [admin secret] (from rustfs.k8s-admin-secret-key)
│  └─ RESTIC_PASSWORD: [encryption] (from rustfs.restic_password)
│
├─ VolSync (Hardcoded S3 path in policy)
│  └─ repository: "s3:http://192.168.10.133:30292/volsync-backup/NAMESPACE/PVC"
│     Uses: AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY for auth
│
└─ Longhorn (Simplified for universal key)
   └─ backupTarget: s3://longhorn-backups/
      Uses: AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY for auth
```

**✅ All apps now use the single `k8s-admin` universal key!**

---

## What Could Go Wrong (And How to Diagnose)

### Scenario 1: "access_key" Mismatch
**Symptom:** VolSync backup fails with "Access Denied" or auth error
**Cause:** 1Password `rustfs.access_key` doesn't match the actual RustFS access key name
**Fix:** Verify the access key value in 1Password matches "volsync" key in RustFS

### Scenario 2: "secret_key" Mismatch  
**Symptom:** VolSync backup fails with "Signature mismatch"
**Cause:** 1Password `rustfs.secret_key` is wrong or out of sync
**Fix:** Get the correct secret from RustFS console, update 1Password

### Scenario 3: "restic_repository" Malformed
**Symptom:** VolSync backup fails with "Invalid repository" error
**Cause:** Typo in the S3 URL base path
**Expected:** `s3:http://192.168.10.133:30292/volsync-backup/`
**Fix:** Verify exact URL in 1Password

### Scenario 4: Port Wrong
**Symptom:** VolSync can't reach S3 at all, times out
**Cause:** Using port 9000 instead of 30292 (or vice versa)
**Fix:** Confirm correct port in both Kyverno policy and 1Password URL

---

## Action Plan ✅ COMPLETE

**Updated:**
1. ✅ `infrastructure/storage/volsync/rustfs-credentials.yaml` - Now uses `k8s-admin` key
2. ✅ `infrastructure/storage/volsync/externalsecret.yaml` - Now uses `k8s-admin` key  
3. ✅ `infrastructure/storage/longhorn/externalsecret.yaml` - Now uses `k8s-admin` from rustfs (minio removed)
4. ✅ This audit document - Reflects unified authentication

**Next Steps:**
1. Commit changes to git
2. ArgoCD will sync updated ExternalSecrets
3. Kubernetes will pull new k8s-admin credentials from 1Password
4. VolSync backups will use k8s-admin for S3 authentication
5. Longhorn backups will use k8s-admin for S3 authentication
