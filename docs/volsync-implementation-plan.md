# VolSync Implementation Plan

> **Reference:** See [backup-restore-architecture.md](./backup-restore-architecture.md) for the vision, goals, and guiding principles.

This document contains the technical deep-dive, problem analysis, and implementation plan for achieving the zero-touch backup/restore system.

---

## Table of Contents

1. [Current State](#current-state)
2. [The Core Problem: Timing](#the-core-problem-timing)
3. [Detailed Scenario Analysis](#detailed-scenario-analysis)
4. [Problems Encountered](#problems-encountered)
5. [Solution Analysis](#solution-analysis)
6. [Chosen Solution: Pre-warmed RDs](#chosen-solution-pre-warmed-rds)
7. [Implementation Steps](#implementation-steps)
8. [Testing Plan](#testing-plan)

---

## Current State

### What Exists

| Component | Status | Location |
|-----------|--------|----------|
| VolSync Operator | Deployed | `infrastructure/storage/volsync/` |
| Longhorn CSI | Deployed | `infrastructure/storage/longhorn/` |
| Kyverno | Deployed | `infrastructure/controllers/kyverno/` |
| Generate Policy | **DISABLED** | `volsync-clusterpolicy.yaml` - empty rules |
| Mutate Policy | Exists | `volsync-auto-restore.yaml` - checks RD for latestImage |
| Sync CronJob | Exists | `sync-cronjob.yaml` - triggers sync on existing RDs |
| Pre-warm CronJob | **NOT IMPLEMENTED** | Needed to create RDs before app deploy |
| ClusterExternalSecret | Exists | `rustfs-credentials.yaml` - provides S3 creds to namespaces |

### What's Broken

1. **No backups happening** - Generate policy disabled, no RS being created
2. **No restores possible** - No RDs exist, mutate policy has nothing to check
3. **Apps starting fresh** - Even if backups exist in S3, they're not restored

---

## The Core Problem: Timing

### Kubernetes Admission is Synchronous

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   When a PVC is created:                                                    │
│                                                                             │
│   1. API Server receives PVC CREATE request                                 │
│   2. Admission webhooks run (Kyverno) ◄── MUST DECIDE NOW (milliseconds)   │
│   3. PVC is persisted to etcd                                               │
│   4. CSI Driver provisions volume                                           │
│                                                                             │
│   Steps 1-3 happen SYNCHRONOUSLY in milliseconds.                          │
│   There is NO way to "wait for something else" during admission.           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### The Timeline Problem

```
T+0ms:      PVC CREATE request arrives
T+1ms:      Kyverno mutate webhook must decide about dataSourceRef NOW
T+30-90s:   RD would finish syncing from S3 (if we created it)

The decision about dataSourceRef must be made at T+1ms,
but the information needed (does backup exist? is RD ready?)
takes 30-90 seconds to obtain.
```

### Why Previous Approaches Failed

**Approach 1: Generate RD at PVC creation time**
- RD created at T+0, but has no latestImage until T+30-90s
- Mutate policy runs at T+1ms, sees no latestImage
- Decision: no dataSourceRef (wrong if backup exists)

**Approach 2: Always add dataSourceRef**
- PVC waits for RD's latestImage
- On fresh install, latestImage never appears (no backup in S3)
- PVC stuck pending forever

**Approach 3: Strip all dataSourceRef**
- PVCs always bind fresh
- Never restores from backup (defeats the purpose)

---

## Detailed Scenario Analysis

### Scenario 1: Fresh Cluster Install

```
TIME    ARGOCD              POLICY                  VOLSYNC                 STORAGE            S3
─────────────────────────────────────────────────────────────────────────────────────────────────────

T0      Deploy app
        │
T1      ├──► Create PVC
        │    (backup: hourly)
        │         │
        │         ├──► Pre-warm CronJob already ran
        │         │    No backup found in S3
        │         │    No RD created
        │         │
        │         ├──► Mutate: Check for RD
        │         │    RD doesn't exist
        │         │    → No dataSourceRef added
        │         │
        │         └──► Generate: Create RS ──────────────────────────────────► (no data yet)
        │
T2      │                                                               ───────► Provision
        │                                                               ◄─────── fresh volume
        │                                                                        PVC BOUND
T3      ├──► Create Deployment
        │         │
        │         └──► Pod starts with EMPTY storage ✓
        │
T4      │                              RS runs on schedule ────────────────────► First backup
        │                                                                        to S3!

RESULT: Fresh install works, backups begin automatically
```

### Scenario 2: Cluster Rebuild (Backup Exists)

```
TIME    ARGOCD              POLICY                  VOLSYNC                 STORAGE            S3
─────────────────────────────────────────────────────────────────────────────────────────────────────

        (BEFORE app deploy)
        │
T-5     │                   Pre-warm CronJob runs
        │                        │
        │                        ├──► List S3 bucket
        │                        │    Found: namespace/pvc-name backup!
        │                        │
        │                        ├──► Create namespace (if needed)
        │                        │
        │                        ├──► Create RD in namespace ──────────────────► Sync from S3
        │                        │                                    │              │
T-4     │                        │                                    │              ▼
        │                        │                                    │         S3 HAS DATA
        │                        │                                    │              │
T-3     │                        │                                    │         Syncing...
        │                        │                                    │              │
T-2     │                        │                                    │              ▼
        │                        │                                    │         RD has
        │                        │                                    │         latestImage! ✓
        │
T0      Deploy app
        │
T1      ├──► Create PVC
        │    (backup: hourly)
        │         │
        │         ├──► Mutate: Check for RD
        │         │    RD EXISTS with latestImage! ✓
        │         │    → ADD dataSourceRef
        │         │
        │         └──► Generate: Create RS
        │
T2      │                                                               ───────► Volume Populator
        │                                                               ◄─────── restores from
        │                                                                        latestImage
        │                                                                        PVC BOUND
T3      ├──► Create Deployment
        │         │
        │         └──► Pod starts with RESTORED data! ✓

RESULT: Zero-touch restore from backup
```

### Scenario 3: Add New App

Same as Scenario 1 - no backup exists for this app, starts fresh, backups begin.

### Scenario 4: Delete App, Re-add Later (Karakeep)

**Phase 1: Running normally**
- RS backing up hourly to S3
- RD synced with latestImage
- S3 has backup data

**Phase 2: Delete app in ArgoCD**
- All resources deleted (Deployment, PVC, RS, RD)
- S3 backup REMAINS (external, not deleted)

**Phase 3: Time passes**
- Pre-warm CronJob runs, finds backup in S3
- Creates RD, syncs, has latestImage
- RD is "warm" waiting for app

**Phase 4: Re-add app**
- Same as Scenario 2
- RD already exists with latestImage
- PVC gets dataSourceRef
- Restores from backup

---

## Problems Encountered

### Problem 1: Generate Policy Caused Corruption

The original generate policy created RS AND RD for every PVC with backup label.

**What went wrong:**
- On fresh install, RD created but S3 empty
- RD has no latestImage
- PVC with dataSourceRef waits forever
- OR: Volume Populator tries to restore from nothing → faulted volume

**Fix:** Don't generate RD at PVC creation time. Pre-warm RDs only when backup exists.

### Problem 2: Kyverno apiCall Behavior

Checking if RD has latestImage via apiCall:

```yaml
context:
  - name: rdExists
    apiCall:
      urlPath: "/apis/volsync.../replicationdestinations/{{name}}"
      jmesPath: "status.latestImage.name"
```

**Cases:**
- RD doesn't exist → 404 / null / error (behavior varies)
- RD exists, no latestImage → null
- RD exists with latestImage → "snapshot-name"

**Challenge:** Distinguishing null (no RD) from null (RD exists but no latestImage)

**Fix:** Use `default: ""` and check for empty string

### Problem 3: PVCs Stuck Pending

When PVC has dataSourceRef to RD without latestImage:
- Longhorn waits for latestImage
- No timeout - waits forever
- Pod stuck pending

**Fix:** Only add dataSourceRef when RD has latestImage (pre-warm ensures this)

### Problem 4: Longhorn Faulted Volumes

Some volumes ended up faulted with "insufficient storage" despite free space.

**Possible causes:**
- Volume Populator timeout issues
- Network isolation between nodes
- Replica scheduling problems

**Status:** May be separate from VolSync issue, needs investigation

---

## Solution Analysis

### Solution A: Pre-warmed RDs (RECOMMENDED)

**How it works:**
1. CronJob runs every 5 minutes
2. Lists S3 bucket to find existing backups
3. For each backup, creates RD in the namespace (if namespace exists)
4. Triggers sync to populate latestImage
5. When app deploys, RD is already "warm"

**Pros:**
- Zero-touch for user
- DRY - one CronJob for all apps
- Works with existing Kyverno mutate policy
- Handles all scenarios correctly

**Cons:**
- 5-minute window where new app won't have RD ready
- CronJob adds complexity

### Solution B: Init Container Restore

**Pros:** No timing issues, simple logic
**Cons:** VIOLATES DRY - every app needs init container

### Solution C: Pre-restore Job per App

**Pros:** Clear ordering via sync-waves
**Cons:** VIOLATES DRY - job per app

### Solution D: Custom Controller

**Problem:** Can't patch dataSourceRef after PVC creation (immutable)

### Solution E: Validating Webhook with Retry

**Pros:** Guarantees correct ordering
**Cons:** Complex, ArgoCD shows degraded during wait

---

## Chosen Solution: Pre-warmed RDs

Based on the requirements (zero-touch, DRY, works in all scenarios), **Solution A** is the best fit.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   PRE-WARM CRONJOB (runs every 5 minutes)                                   │
│                                                                             │
│   1. List S3 bucket: aws s3 ls s3://volsync-backups/                        │
│   2. For each path (namespace/pvc-name):                                    │
│      a. Check if namespace exists                                           │
│      b. Check if namespace has volsync-rustfs-base secret                   │
│      c. Create RD if doesn't exist                                          │
│      d. Trigger sync                                                        │
│   3. Result: RDs are "warm" with latestImage                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   KYVERNO GENERATE POLICY (for backup)                                      │
│                                                                             │
│   When: PVC created with backup: "hourly" label                             │
│   Action: Create ReplicationSource (RS) for backup                          │
│                                                                             │
│   Note: Does NOT create RD - that's the pre-warm CronJob's job              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   KYVERNO MUTATE POLICY (for restore)                                       │
│                                                                             │
│   When: PVC created with backup: "hourly" label                             │
│   Check: Does RD exist with latestImage?                                    │
│   If YES: Add dataSourceRef to PVC                                          │
│   If NO: Leave PVC without dataSourceRef                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   RESULT                                                                    │
│                                                                             │
│   Fresh cluster:   No backup → No RD → No dataSourceRef → Fresh storage    │
│   Cluster rebuild: Backup exists → RD warm → dataSourceRef → Restore       │
│   New app:         No backup → No RD → Fresh → Backups begin               │
│   Re-add app:      Backup exists → RD warm → Restore                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Steps

### Step 1: Create Pre-warm CronJob

Create `infrastructure/storage/volsync/prewarm-cronjob.yaml`:
- ServiceAccount with permissions to create RDs
- CronJob that lists S3 and creates RDs
- Runs every 5 minutes

### Step 2: Update Kyverno Generate Policy

Modify `infrastructure/controllers/kyverno/volsync-clusterpolicy.yaml`:
- Re-enable the policy
- Generate ONLY ReplicationSource (RS) for backup
- Do NOT generate ReplicationDestination (RD) - pre-warm handles this
- Generate the Secret for S3 credentials

### Step 3: Verify Mutate Policy

Check `infrastructure/controllers/kyverno/volsync-auto-restore.yaml`:
- Rule 1: If RD exists with latestImage → add dataSourceRef
- Rule 2: If no RD or no latestImage → ensure no dataSourceRef
- Handle all edge cases (null, empty string, missing)

### Step 4: Update Kustomization

Add pre-warm CronJob to `infrastructure/storage/volsync/kustomization.yaml`

### Step 5: Test All Scenarios

See Testing Plan below.

---

## Testing Plan

### Test 1: Fresh Install (No Backup)

1. Ensure S3 bucket is empty for test namespace
2. Deploy app with `backup: "hourly"` label on PVC
3. Verify:
   - PVC binds immediately (no dataSourceRef)
   - App starts with empty storage
   - RS created, first backup runs
   - S3 now has backup data

### Test 2: Restore from Backup

1. Have existing backup in S3 from Test 1
2. Delete the app (namespace, PVC, etc.)
3. Wait for pre-warm CronJob to run (or trigger manually)
4. Verify RD created with latestImage
5. Re-deploy app
6. Verify:
   - PVC has dataSourceRef
   - Data restored from backup
   - App has previous data

### Test 3: Add New App (Existing Cluster)

1. Cluster running with other apps
2. Add new app with backup label
3. Verify same as Test 1 (fresh install behavior)

### Test 4: Karakeep Scenario

1. App running for a while with backups
2. Delete app in ArgoCD
3. Wait days/weeks (or simulate by waiting for CronJob)
4. Re-add app
5. Verify data restored

### Test 5: Edge Cases

- Namespace doesn't exist yet (pre-warm should skip)
- Secret not yet created (pre-warm should skip)
- RD exists but no latestImage (mutate should not add dataSourceRef)
- Multiple PVCs in same namespace

---

## S3 Bucket Structure

```
s3://volsync-backups/
│
├── karakeep/
│   └── data/
│       └── (restic repo files)
│
├── home-assistant/
│   └── config/
│       └── (restic repo files)
│
├── immich/
│   ├── library/
│   │   └── (restic repo files)
│   └── postgres/
│       └── (restic repo files)
│
└── [namespace]/
    └── [pvc-name]/
        └── (restic repo files)
```

The pre-warm CronJob discovers these paths and creates RDs accordingly.

---

## Open Questions

1. **CronJob interval:** 5 minutes acceptable? Could be 1 minute for faster discovery.
2. **RD capacity:** Currently hardcoded to 10Gi - should match original PVC size?
3. **Cleanup:** Should pre-warm delete orphaned RDs (backup deleted from S3)?
4. **Namespace creation:** Should pre-warm create namespace if it doesn't exist?
