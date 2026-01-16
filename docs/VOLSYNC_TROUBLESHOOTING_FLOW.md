# VolSync Troubleshooting & Flow Diagram

## Data Flow & Current Status (Jan 16, 2026)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          KUBERNETES CLUSTER                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────┐         ┌──────────────────────────────────────┐  │
│  │   PVC with Label    │         │  Kyverno ClusterPolicy              │  │
│  │  backup: "hourly"   │────────▶│  volsync-smart-protection           │  │
│  │                     │  CREATE │  ✅ Removes problematic apiCall     │  │
│  │ Examples:           │         │  ✅ Always generates jobs            │  │
│  │ - khoj/config       │         │  ✅ Uses hardcoded S3 paths         │  │
│  │ - open-webui/data   │         │  ✅ No external API checks          │  │
│  │ - karakeep/data-pvc │         │                                      │  │
│  │ - jellyfin/config   │         │  Generated Resources:                │  │
│  └─────────────────────┘         │  • ReplicationSource (backup job)    │  │
│            │                     │  • ReplicationDestination (restore)  │  │
│            │                     └──────────────┬───────────────────────┘  │
│            │                                    │                           │
│            └────────────────────────────────────┘                           │
│                                 │                                           │
│                                 ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  ReplicationSource (RS) - The Backup Scheduler                       │  │
│  │  ─────────────────────────────────────────────────────────────────  │  │
│  │  name: <pvc-name>-backup                                             │  │
│  │  schedule: "0 * * * *"  (hourly at :00)                             │  │
│  │  sourcePVC: <pvc-name>                                              │  │
│  │  repository: "s3:http://192.168.10.133:30292/volsync-backup/..."   │  │
│  │  copyMethod: Direct                                                  │  │
│  │  storageClass: longhorn                                              │  │
│  │                                                                      │  │
│  │  STATUS: ✅ Should show "Latest Mover Status" when running         │  │
│  └──────────────────────┬───────────────────────────────────────────────┘  │
│                         │                                                   │
│                         ▼ (triggers on schedule)                            │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  VolSync Controller Pod (in volsync-system namespace)                │  │
│  │  ─────────────────────────────────────────────────────────────────  │  │
│  │  Pod: volsync-<hash>                                                 │  │
│  │  Status: 2/2 Running ✅                                              │  │
│  │                                                                      │  │
│  │  JOB: Creates temporary PVCs and runs Restic backup                 │  │
│  │  • volsync-src-<pvc>-backup-cache (temporary cache)                 │  │
│  │  • Reads source PVC snapshot                                         │  │
│  │  • Compresses & encrypts with Restic                                 │  │
│  │  • Pushes to S3                                                      │  │
│  └──────────────────────┬───────────────────────────────────────────────┘  │
│                         │                                                   │
└─────────────────────────┼───────────────────────────────────────────────────┘
                          │ (network call)
                          ▼
        ┌──────────────────────────────────────────┐
        │  EXTERNAL: RustFS / MinIO (TrueNAS)      │
        │  IP: 192.168.10.133:30292                │
        │  ──────────────────────────────────────  │
        │                                           │
        │  S3 Bucket: volsync-backup/               │
        │  ├── karakeep/                            │
        │  │   ├── data-pvc/        ✅ (has data)  │
        │  │   └── meilisearch-pvc/ ✅ (has data)  │
        │  ├── khoj/                                │
        │  │   └── config/          ✅ (has data)  │
        │  ├── open-webui/                          │
        │  │   ├── data/            ✅ (has data)  │
        │  │   └── storage/         ✅ (has data)  │
        │  ├── home-assistant/                      │
        │  │   └── config/          ✅ (has data)  │
        │  ├── paperless-ngx/                       │
        │  │   ├── data/            ✅ (has data)  │
        │  │   └── media/           ✅ (has data)  │
        │  ├── redis-instance/                      │
        │  │   └── redis-master-0/  ✅ (has data)  │
        │  └── [other namespaces]/                  │
        │                                           │
        │  Access Keys:                             │
        │  ├── volsync (Available) ✅               │
        │  ├── loki                                 │
        │  └── longhorn                             │
        │                                           │
        │  Credentials from 1Password:              │
        │  ├── rustfs (item name) ✅ exists        │
        │  │   ├── access_key                       │
        │  │   ├── secret_key                       │
        │  │   ├── restic_password                  │
        │  │   └── restic_repository (base path)    │
        └──────────────────────────────────────────┘
```

## Current Status Check

| Component | Status | Details |
|-----------|--------|---------|
| **RustFS/MinIO** | ✅ Running | Visible in screenshots, 3+ namespaces with backup data |
| **Access Keys** | ✅ Available | "volsync" key is Available in RustFS console |
| **1Password Item** | ✅ Exists | rustfs item has all required fields |
| **VolSync CRDs** | ✅ Installed | replicationsources.volsync.backube, replicationdestinations.volsync.backube |
| **VolSync Operator** | ✅ Running | 1 pod in volsync-system, 2/2 containers Running |
| **Kyverno Policy** | ❓ Broken | apiCall checks failing (can't reach external S3 from cluster) |
| **Backup Jobs** | ❓ Stuck | Only meilisearch-pvc-backup exists, others not generated |
| **ExternalSecrets** | ✅ Syncing | All namespaces getting volsync-rustfs-base secret |

---

## Troubleshooting Path: What Failed

### ❌ Original Problem
```
PVC created with backup: hourly label
         │
         ▼
Kyverno matches the PVC
         │
         ▼
Kyverno tries apiCall: http://192.168.10.133:30292/volsync-backup/.../config
         │
         ▼
🔴 FAIL: Can't reach external IP from inside cluster
         │
         ▼
ReplicationSource NOT generated
         │
         ▼
NO BACKUPS created (except old ones)
```

### ❌ Failed Attempt #1: Use Secret Reference
- Changed policy to use `repository: volsync-rustfs-base` (secret name)
- Changed ExternalSecret to output `RESTIC_REPOSITORY` field
- Result: VolSync still couldn't find credentials properly
- **Problem**: VolSync needs the full S3 URL, not just a secret name

### ✅ Correct Fix: Hardcoded S3 Paths (No API Calls)
```
PVC created with backup: hourly label
         │
         ▼
Kyverno matches the PVC
         │
         ▼
✅ Kyverno generates ReplicationSource with:
   repository: "s3:http://192.168.10.133:30292/volsync-backup/namespace/pvc-name"
         │
         ▼
✅ No external API calls needed
         │
         ▼
✅ ReplicationSource created immediately
         │
         ▼
✅ VolSync controller picks it up
         │
         ▼
✅ VolSync reads AWS credentials from ExternalSecret
   (ONLY for S3 auth, not for path determination)
         │
         ▼
✅ Hourly backup to S3 starts
```

---

## Decision Tree

```
Does ReplicationSource exist?
├─ YES (e.g., karakeep/meilisearch-pvc-backup)
│  │
│  └─ Does it show "Message: secret is missing field: RESTIC_REPOSITORY"?
│     ├─ YES → Problem: Old policy, secret reference not set up
│     │        Action: Apply new policy WITHOUT apiCall
│     └─ NO → Check "LAST SYNC" timestamp
│        ├─ Recent (< 1 hour) → ✅ Working!
│        └─ Old (> 1 hour) → Problem: Schedule not triggering
│           Action: Check VolSync controller logs
│
└─ NO (most PVCs)
   │
   └─ Does PVC have label backup: hourly?
      ├─ NO → Action: Add label to PVC
      └─ YES → Problem: Kyverno policy not generating it
         │
         └─ Check Kyverno events on PVC:
            kubectl describe pvc <name> -n <namespace>
            
            Look for:
            ✅ Events from kyverno-policy
               "mutation policy volsync-smart-protection" = policy ran
            ❌ "mutation policy volsync-smart-protection error"
               = Check what error is shown
            
            Common errors:
            • "failed to fetch data for APICall" → Policy trying to call external IP
              Action: Apply updated policy without apiCall
            
            • No events at all → Kyverno not running or policy not matching
              Action: Check Kyverno is Ready, check label selector matches
```

---

## Verification Steps

### Step 1: Check Policy is applied (no apiCall errors)
```bash
kubectl describe clusterpolicy volsync-smart-protection
# Look for: "3 Generate rules"
# NO mention of "context:" or "apiCall" should be visible
```

### Step 2: Create test PVC and watch Kyverno
```bash
# In one terminal, watch events:
kubectl describe pvc test-pvc -n default -w

# In another terminal, create PVC:
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: test-pvc
  namespace: default
  labels:
    backup: "hourly"
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: longhorn
  resources:
    requests:
      storage: 1Gi
EOF

# Watch for Kyverno events saying it generated ReplicationSource
```

### Step 3: Check ReplicationSource was created
```bash
kubectl get replicationsource -n default test-pvc-backup -o yaml

# Should show:
# spec:
#   sourcePVC: test-pvc
#   trigger:
#     schedule: "0 * * * *"
#   restic:
#     repository: "s3:http://192.168.10.133:30292/volsync-backup/default/test-pvc"
```

### Step 4: Wait for first backup (next hour)
```bash
# Check status:
kubectl describe replicationsource -n default test-pvc-backup

# Should show:
# Status:
#   Conditions:
#     Type: Synchronizing
#     Status: True
#   Latest Mover Status: (shows when running)
#   Last Sync Start Time: <timestamp>
```

### Step 5: Verify data in S3
```bash
# Login to RustFS console and check:
# volsync-backup/default/test-pvc/ → should have files
```

---

## Summary of Current Fix

✅ **What we're doing:**
1. Remove apiCall checks that try to reach external S3
2. Keep hardcoded S3 paths in policy (no secret reference)
3. Keep ExternalSecret for AWS credentials only
4. Kyverno generates jobs immediately without network calls
5. VolSync controller uses hardcoded paths + external secret creds

✅ **Why it works:**
- No network dependency during policy evaluation
- S3 paths are determined at policy creation time
- AWS creds are fetched from secret when VolSync actually runs
- Backups proceed on schedule

⚠️ **Trade-off:**
- Lost "smart restore" (checking if backup exists before creating)
- But gained reliability (no external calls during policy)
- Manual restore still works with ReplicationDestination
