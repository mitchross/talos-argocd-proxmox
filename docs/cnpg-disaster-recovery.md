# CNPG Database Disaster Recovery

## Overview

CloudNativePG (CNPG) databases are backed up via **Barman** to RustFS S3 (`s3://postgres-backups/cnpg/`). Unlike PVC backups (which auto-restore via Kyverno + PVC Plumber), database recovery is **manual** and must bypass ArgoCD.

## Database ApplicationSet Architecture

Database Applications are managed by a **separate ApplicationSet** (`database-appset.yaml`) with key differences from the infrastructure AppSet:

| Setting | Infrastructure AppSet | Database AppSet |
|---------|----------------------|-----------------|
| `selfHeal` | `true` | **`false`** |
| `ignoreApplicationDifferences` | none | preserves `skip-reconcile` |

**Why**: Databases have a fundamentally different lifecycle from infrastructure. During disaster recovery, you need to manually create recovery clusters with `kubectl create`, which conflicts with ArgoCD's auto-sync. With `selfHeal: false`:
- ArgoCD still auto-syncs **from Git** (push = deploy)
- ArgoCD does **not** revert manual kubectl changes (needed for DR)
- `skip-reconcile` annotations **stick** (ApplicationSet doesn't strip them)

This means recovery no longer requires scaling down ArgoCD controllers.

## Why Recovery Can't Go Through ArgoCD

ArgoCD uses **Server-Side Apply (SSA)**. CNPG has a **mutating admission webhook** that adds `initdb` defaults to every Cluster creation. When combined:

1. ArgoCD sends SSA patch with `bootstrap.recovery`
2. CNPG webhook intercepts and adds `bootstrap.initdb` defaults
3. SSA merges both field managers — `initdb` wins
4. Result: fresh empty database, every time

Additionally, ArgoCD ApplicationSets enforce `selfHeal: true`, recreating deleted clusters in sub-second — too fast to manually intervene.

**Solution**: Apply recovery manifests directly with `kubectl create`, bypassing ArgoCD entirely.

## GitOps During Recovery: Source of Truth & skip-reconcile

**Key principle: Git is ALWAYS source of truth.** But during recovery, we temporarily pause ArgoCD's auto-sync to avoid conflicts.

### Normal GitOps Flow (Always)

```
┌──────────────┐
│     Git      │  ← Source of truth (cluster.yaml, values, etc.)
└──────┬───────┘
       │
       │ (ArgoCD watches continuously)
       │ "Any change in Git = auto-sync to cluster"
       ↓
┌──────────────┐
│   ArgoCD     │
│ (auto-sync)  │
└──────┬───────┘
       │
       │ (SSA, Helm rendering, kustomize apply)
       ↓
┌──────────────┐
│   Cluster    │
│ (synced to   │
│  Git state)  │
└──────────────┘
```

Git change → ArgoCD auto-discovers → Cluster updates. Simple, automated, always consistent.

### Recovery Flow: Temporary skip-reconcile

During CNPG recovery, we PAUSE auto-sync to prevent conflicts:

```
STEP 1: Pause auto-sync (Set skip-reconcile=true)
┌──────────────┐
│     Git      │
└──────┬───────┘
       │
       X (ArgoCD paused)
       │ "Don't auto-sync yet"
       ↓
┌──────────────────────────────┐
│   ArgoCD (PAUSED)            │
│ skip-reconcile=true          │
│ (manual sync only)           │
└──────────────────────────────┘
       │
       │ (Manual sync via UI still works)
       ↓
┌──────────────────────────────┐
│   Cluster (unchanged so far) │
└──────────────────────────────┘

STEP 2: Manual kubectl recovery (bypass ArgoCD)
┌──────────────────────────────┐
│   You (kubectl create)       │
│   recovery-cluster.yaml      │
└──────┬───────────────────────┘
       │
       │ (Direct API call, no SSA conflict)
       ↓
┌──────────────────────────────┐
│   Cluster                    │
│ (recovery pod running)       │
└──────────────────────────────┘

STEP 3: Recovery completes, unpause (Remove skip-reconcile)
┌──────────────┐
│     Git      │
└──────┬───────┘
       │
       │ (ArgoCD unpaused)
       │ "Resume auto-sync"
       ↓
┌──────────────────────────────┐
│   ArgoCD (RESUMING)          │
│ skip-reconcile removed       │
│ (auto-sync enabled)          │
└──────────────────────────────┘
       │
       │ (normal GitOps resumes)
       ↓
┌──────────────────────────────┐
│   Cluster (final state)      │
│  (recovered data + Git sync) │
└──────────────────────────────┘
```

### Why skip-reconcile Doesn't Break GitOps

**Git remains source of truth the whole time:**
- You commit recovered state back to Git (cluster.yaml reverted to initdb, backup lineage bumped to v3)
- skip-reconcile only blocks **automatic reconciliation** (ArgoCD watching)
- Manual sync (UI click) still reads Git and applies to cluster
- Once skip-reconcile is removed, auto-sync resumes from Git state

**Think of it like:**
- Normal: ArgoCD is always watching Git, automatically syncing any changes
- skip-reconcile pause: You tell ArgoCD "ignore Git for now, let me work"
- Manual recovery: You directly fix the cluster
- Unpause: ArgoCD starts watching Git again, makes sure cluster matches Git

**After unpause, if someone changed Git while paused:**
- ArgoCD syncs the newest Git state
- Old recover state is overwritten by Git
- Git wins (as it should)

### Cleanup Checklist

```
[ ] Recovery cluster is healthy (pod Ready 1/1, data validated)
[ ] cluster.yaml reverted to initdb mode (not recovery)
[ ] ⚠️  ALL recovery code DELETED from cluster.yaml (not just commented!)
    - bootstrap.recovery section removed
    - externalClusters section removed
    - REASON: CNPG webhook blocks sync if both bootstrap methods present
[ ] cluster.yaml backup lineage bumped to v3 (not v2)
[ ] Commit cluster.yaml to Git
[ ] Push to main branch
[ ] Verify Git shows only initdb block (no recovery code)
[ ] Wait for ArgoCD to auto-detect sync → should show Synced
[ ] Manual sync via Argo UI (if needed)
[ ] Remove skip-reconcile annotations
[ ] Verify auto-sync working again
```

**Key reminder: CNPG webhook validates mutual exclusivity of bootstrap methods. Recovery code must be completely removed before committing to Git, or ArgoCD will remain OutOfSync forever.**

After unpause, Git and cluster sync normally, and you're back to true GitOps.

## Backup Architecture

```
CNPG Cluster
    ↓ (continuous WAL archiving + scheduled base backups)
Barman → RustFS S3
    s3://postgres-backups/cnpg/<app>/<serverName>/base/     (base backups)
    s3://postgres-backups/cnpg/<app>/<serverName>/wals/     (WAL files)
```

### Current Database Inventory

| Database | S3 Path | Current serverName | Schedule |
|----------|---------|-------------------|----------|
| immich | `s3://postgres-backups/cnpg/immich` | `immich-database-v4` | Hourly + WAL |
| khoj | `s3://postgres-backups/cnpg/khoj` | `khoj-database` | Daily 2am + WAL |
| paperless | `s3://postgres-backups/cnpg/paperless` | `paperless-database` | Daily 2am + WAL |

### serverName Versioning

CNPG requires a **clean WAL archive** for new clusters. After recovery, the new cluster can't write WALs to the same path as the old cluster. The `serverName` in `backup.barmanObjectStore` controls the subdirectory:

```
s3://postgres-backups/cnpg/immich/
├── immich-database/        ← original (pre-recovery backups)
│   ├── base/
│   └── wals/
└── immich-database-v2/     ← current (post-recovery backups)
    ├── base/
    └── wals/
```

**Each recovery bumps the version**: `-v2` → `-v3` → `-v4`, etc.

### Restore Source vs Backup Target (Critical)

During recovery, treat these as two different values:

- `externalClusters[].barmanObjectStore.serverName` = **restore source** (existing lineage, e.g. `immich-database-v2`)
- `backup.barmanObjectStore.serverName` = **new backup target** (next lineage, e.g. `immich-database-v3`)

After recovery succeeds, keep backups on the new lineage (`v3`). Do **not** switch backup target back to `v2`.

## CNPG Normal Operation (Continuous Backups)

This is what happens every day to keep backups current:

```
┌─────────────────────────────────────────────────────────────┐
│   CNPG Cluster (Normal Operation)                          │
│                                                             │
│   ┌──────────────┐                                          │
│   │  Postgres    │  ← Running, accepting transactions      │
│   │  (immich)    │                                          │
│   └──────┬───────┘                                          │
│          │                                                   │
│  ┌───────┴──────────────────────┬────────────────────────┐  │
│  │ split into two paths:        │                        │  │
│  ↓                              ↓                        │  │
│  ┌──────────────┐       ┌──────────────────┐           │  │
│  │  WAL Stream  │       │ Scheduled Base   │           │  │
│  │  (every txn) │       │ Backups (daily)  │           │  │
│  └──────┬───────┘       └────────┬─────────┘           │  │
│         │                        │                     │  │
│         │ (continuous)           │ (full dump)         │  │
│         ↓                        ↓                     │  │
│  ┌──────────────────────────────────────────┐         │  │
│  │  Barman (CloudNativePG operator)         │         │  │
│  │  "Archive everything to S3"              │         │  │
│  └──────┬───────────────────────────────────┘         │  │
│         │                                             │  │
│         │ (upload to S3)                              │  │
│         ↓                                             │  │
│  ┌──────────────────────────────────────────┐         │  │
│  │  RustFS S3 Storage                       │         │  │
│  │                                          │         │  │
│  │  s3://postgres-backups/cnpg/immich/     │         │  │
│  │  ├── immich-database-v2/                │         │  │
│  │  │   ├── base/     (full backups)       │         │  │
│  │  │   └── wals/     (transaction logs)   │         │  │
│  │  └── (encrypted, compressed)            │         │  │
│  └──────────────────────────────────────────┘         │  │
│                                                       │  │
└───────────────────────────────────────────────────────┘  │
```

**Result**: If something breaks tomorrow, backups with all transactions up to the failure moment are sitting on S3.

## CNPG Disaster Recovery (Reading from Backups)

When you nuke the cluster and rebuild, CNPG needs to restore from S3:

```
SCENARIO: Cluster crashed, PVCs deleted, you're rebuilding

STEP 1: You tell CNPG "Use recovery mode" (in cluster.yaml)
┌─────────────────────────────────────┐
│  cluster.yaml bootstrap section:    │
│  recovery:                          │
│    source: immich-backup       ← points to S3│
├─────────────────────────────────────┤
│  externalClusters:                 │
│    serverName: v2              ← restore FROM this version
└─────────────────────────────────────┘
         │
         │ (kubectl create - bypass ArgoCD)
         ↓
┌─────────────────────────────────────────────────────────┐
│   CNPG Operator sees "recovery" mode                   │
│   Looks for source in externalClusters                 │
└────────────────────┬────────────────────────────────────┘
                     │
                     ↓
         ┌───────────────────────┐
         │  RustFS S3            │
         │  (look for v2)        │
         └─────────┬─────────────┘
                   │
              ┌────┴────┐
              ↓         ↓
         ┌────────┐  ┌───────┐
         │ base/  │  │ wals/ │  ← Latest transaction logs
         └────┬───┘  └───┬───┘
              │          │
              └────┬─────┘
                   │ (download + restore)
                   ↓
         ┌─────────────────────┐
         │  New Postgres Pod   │
         │  (recovering...)    │
         │  + Longhorn PVCs    │
         │  (data being written)
         └────────┬────────────┘
                  │ (after restore completes)
                  ↓
         ┌─────────────────────┐
         │  Postgres Ready     │
         │  All data restored! │
         │  (v2 lineage)       │
         └─────────────────────┘

STEP 2: You change cluster.yaml back to initdb (normal mode)
         BUT change backup.serverName to v3 (new lineage)
         
         This prevents WAL conflicts:
         - Old backups stay at v2 (untouched, point-in-time recovery available)
         - New writes go to v3 (fresh archive)
         - Next recovery will restore from v3, then bump to v4
```

## Bootstrap Decision Tree

CNPG's bootstrap section determines what happens when a Cluster is created:

```
        ┌──────────────────────────────────┐
        │  CNPG Cluster Created            │
        │  (kubectl create or apply)       │
        └──────────────┬───────────────────┘
                       │
                       │ Check spec.bootstrap:
                       │
            ┌──────────┴──────────┐
            │                     │
            ↓                     ↓
    ┌───────────────┐    ┌──────────────┐
    │   initdb      │    │   recovery   │
    │   (default)   │    │   (restore)  │
    └───────┬───────┘    └──────┬───────┘
            │                   │
            ↓                   │ Look for externalClusters:
    ┌──────────────────────┐    │
    │ Create fresh db      │    ↓
    │ (empty, new owner)   │ ┌──────────────────────────┐
    │                      │ │ Find serverName=v2 in S3 │
    │ Starting postgres,   │ │ Download base backup     │
    │ then run            │ │ + replay WALs            │
    │ postInitSQL:        │ │                          │
    │  - CREATE EXT       │ │ → Postgres starts with   │
    │  - GRANT PRIVS      │ │   restored data!         │
    │                      │ └──────────────────────────┘
    │ RESULT: Empty DB    │
    │ User must sign up   │    RESULT: Full data restored
    │ or restore from     │    Users see their data
    │ PVCs               │    All tables/users back
    └──────────────────────┘
            OR
    ┌──────────────────────┐
    │ BUG: Both present    │
    │ (initdb + recovery)  │
    │                      │
    │ CNPG webhook adds    │
    │ defaults → merger    │
    │ conflict → initdb    │
    │ wins                 │
    │                      │
    │ RESULT: Empty DB    │
    │ (lost data!)        │
    └──────────────────────┘
```

**Key takeaway:** Only ONE bootstrap section should be present. If both exist, `initdb` wins and you lose data. Always remove recovery section before pushing to Git.

## Recovery Procedure

### Prerequisites

- Cluster is running (ArgoCD has bootstrapped)
- CNPG operator is deployed
- `cnpg-s3-credentials` secret exists in `cloudnative-pg` namespace
- Barman backups exist on RustFS S3

### Step-by-Step (example: immich)

**1. Check if backups exist:**

```bash
kubectl run -it --rm barman-check --image=amazon/aws-cli:latest \
  --restart=Never --namespace=cloudnative-pg --overrides='{
  "spec":{"containers":[{"name":"check","image":"amazon/aws-cli:latest",
  "command":["sh","-c","aws --endpoint-url http://192.168.10.133:30293 s3 ls s3://postgres-backups/cnpg/immich/immich-database-v2/base/ 2>&1 | tail -5"],
  "env":[
    {"name":"AWS_ACCESS_KEY_ID","valueFrom":{"secretKeyRef":{"name":"cnpg-s3-credentials","key":"AWS_ACCESS_KEY_ID"}}},
    {"name":"AWS_SECRET_ACCESS_KEY","valueFrom":{"secretKeyRef":{"name":"cnpg-s3-credentials","key":"AWS_SECRET_ACCESS_KEY"}}}
  ]}]}}'
```

**2. Edit the cluster.yaml:**

In `infrastructure/database/cloudnative-pg/immich/cluster.yaml`:
- Comment out the `initdb` bootstrap section
- Uncomment the `recovery` bootstrap + `externalClusters` section
- Set `externalClusters[].barmanObjectStore.serverName` to the **current** backup serverName (e.g. `immich-database-v2`)
- Bump `backup.barmanObjectStore.serverName` to the **next** version (e.g. `immich-database-v3`)

⚠️ **CRITICAL: Webhook Validation (Do Not Commit Both Methods)**

The CNPG webhook validates that **only ONE bootstrap method is present**. Even commented-out recovery code will cause ArgoCD sync to fail with:
```
admission webhook "vcluster.cnpg.io" denied the request: 
spec.bootstrap: Forbidden: Only one bootstrap method can be specified at a time
```

**Why**: After recovery completes, you must **DELETE all recovery code** from the manifest before committing to Git. Do not leave `bootstrap.recovery` or `externalClusters` commented in Git — remove them entirely.

**Procedure**:
1. During recovery: edit cluster.yaml locally, toggle bootstrap methods
2. Test recovery with `kubectl create`
3. **Before committing**: Delete ALL recovery code blocks
4. Revert to `bootstrap.initdb` (normal mode)
5. Keep `backup.barmanObjectStore.serverName` at the bumped version (e.g. `v3`)
6. Commit and push — ArgoCD will accept the manifest

**3. Extract just the Cluster resource:**

```bash
kubectl kustomize infrastructure/database/cloudnative-pg/immich/ \
  | awk '/^apiVersion: postgresql.cnpg.io\/v1/{p=1} p{print} /^---/{if(p) exit}' \
  > /tmp/immich-recovery.yaml

# Verify it has recovery, not initdb:
grep -c "recovery" /tmp/immich-recovery.yaml  # should be >= 1
grep -c "initdb" /tmp/immich-recovery.yaml    # should be 0
```

**4. Pause ArgoCD and delete/recreate:**

Database Applications use `selfHeal: false` (via `database-appset.yaml`), so `skip-reconcile` annotations are preserved by the ApplicationSet controller.

```bash
# Pause ArgoCD reconciliation for the database app and its consumer
kubectl annotate application immich -n argocd argocd.argoproj.io/skip-reconcile=true --overwrite
kubectl annotate application my-apps-immich -n argocd argocd.argoproj.io/skip-reconcile=true --overwrite

# Delete existing cluster and wait for PVC cleanup
kubectl delete cluster immich-database -n cloudnative-pg --wait=false
kubectl wait --for=delete cluster/immich-database -n cloudnative-pg --timeout=180s

# Create recovery cluster (bypasses SSA — must use create, not apply)
kubectl create -f /tmp/immich-recovery.yaml
```

> **Note**: If `kubectl wait` times out, PVCs may still be terminating (Longhorn cleanup). Wait 15-30 seconds and retry the create.

**4b. Confirm live cluster is actually in recovery mode:**

```bash
kubectl get cluster immich-database -n cloudnative-pg -o yaml | sed -n '/bootstrap:/,/storage:/p'
# Must show: bootstrap.recovery
# Must NOT show: bootstrap.initdb
```

**5. Monitor recovery:**

```bash
# Watch cluster status
kubectl get clusters -n cloudnative-pg -w

# Watch recovery pod logs
kubectl logs -n cloudnative-pg -l cnpg.io/cluster=immich-database -f
```

Recovery typically takes 1-5 minutes depending on backup size.

**6. Verify data:**

```bash
kubectl exec -n cloudnative-pg immich-database-1 -- \
  psql -U postgres -d immich -c "SELECT email FROM \"user\" LIMIT 5;"
```

**7. Revert to normal operation:**

In `cluster.yaml`:
- Replace `bootstrap.recovery` + `externalClusters` with `bootstrap.initdb` (normal mode)
- **DELETE all recovery code** — do not leave it commented in Git (CNPG webhook rejects dual bootstrap)
- Keep `backup.barmanObjectStore.serverName` at the bumped version (e.g. `immich-database-v4`)
- Update the DR comment with the new recovery source for next time

```bash
git add infrastructure/database/cloudnative-pg/immich/cluster.yaml
git commit -m "CNPG: revert immich to initdb after successful recovery"
git push
```

**8. Remove skip-reconcile and resume ArgoCD:**

```bash
kubectl annotate application immich -n argocd argocd.argoproj.io/skip-reconcile- --overwrite
kubectl annotate application my-apps-immich -n argocd argocd.argoproj.io/skip-reconcile- --overwrite
```

ArgoCD syncs. CNPG ignores `initdb` bootstrap on existing clusters — your data is safe.

### Quick Example Timeline (Immich)

- Before nuke: backups writing to `immich-database-v4`
- Recovery manifest: restore from `v4`, write new backups to `v5`
- After recovery: normal manifest with `initdb` active, backup still on `v5`
- Next DR event: restore from `v5`, then bump backup target to `v6`

## Troubleshooting

### "Expected empty archive"

**Cause**: `backup.barmanObjectStore.serverName` matches old backup path (WALs already exist).

**Fix**: Bump `serverName` to next version (e.g. `-v2` → `-v3`).

### "no target backup found"

**Cause**: `externalClusters[].barmanObjectStore.serverName` is wrong or missing.

**Fix**: Set it to the serverName that the old backups were written under. Check S3:
```bash
aws --endpoint-url http://192.168.10.133:30293 s3 ls s3://postgres-backups/cnpg/immich/
# Lists subdirectories like: immich-database/, immich-database-v2/
```

### ArgoCD recreates cluster before manual apply

**Cause**: `skip-reconcile` annotation wasn't set before deleting the cluster.

**Fix**: Database Applications use `selfHeal: false` (via `database-appset.yaml`), so the recovery procedure is:
1. Set `skip-reconcile` annotation on both Applications **first**
2. Then delete and recreate the cluster

The `database-appset.yaml` has `ignoreApplicationDifferences` configured to preserve the `skip-reconcile` annotation, so the ApplicationSet controller won't strip it.

### `Error from server (AlreadyExists)` during `kubectl create`

**Cause**: ArgoCD recreated the cluster before your manual create landed (annotation wasn't set).

**Fix**:
1. Verify `skip-reconcile` is set: `kubectl get application immich -n argocd -o jsonpath='{.metadata.annotations}'`
2. If missing, re-annotate and retry delete/wait/create.
3. `kubectl create -f /tmp/immich-recovery.yaml`.
4. Verify live spec shows `bootstrap.recovery`.

### Recovery pod stuck in Pending

**Cause**: Old PVCs from previous cluster still terminating (Longhorn cleanup).

**Fix**: Wait 15-30 seconds for PVCs to fully delete, then recreate the cluster.

### Recovery pod stuck at `Init:0/1` with `volume is not ready for workloads`

**Cause**: Longhorn data/WAL volume is still attaching/remounting after restore.

**Fix**:
```bash
kubectl get pods -n cloudnative-pg -l cnpg.io/cluster=immich-database -o wide
kubectl -n longhorn-system get volumes.longhorn.io | grep immich-database-1
kubectl -n longhorn-system describe volumes.longhorn.io <wal-volume-name>
```
Wait for Longhorn volume `state=attached` and `robustness=healthy`; CNPG will proceed automatically.

### "Only one bootstrap method can be specified"

**Cause**: Both `initdb` and `recovery` present in manifest (ArgoCD SSA merged them).

**Fix**: Don't use `kubectl apply`. Use `kubectl create` to bypass SSA.

### ArgoCD shows "OutOfSync + SyncFailed" with webhook error after recovery

**Cause**: Recovery code (commented `bootstrap.recovery` + `externalClusters`) left in Git.

**Error message**:
```
admission webhook "vcluster.cnpg.io" denied the request: 
spec.bootstrap: Forbidden: Only one bootstrap method can be specified
```

**Fix**: Delete all recovery code from `cluster.yaml` before committing to Git.
1. Remove the `bootstrap.recovery` section entirely (not just comment it).
2. Remove the `externalClusters` section entirely (not just comment it).
3. Keep `bootstrap.initdb` as the only bootstrap method.
4. Commit and push.
5. ArgoCD will sync successfully.

**Why**: The CNPG webhook validates at the manifest yaml level, not at the applied level. Even commented-out code blocks parse as valid YAML and trigger validation errors.

## Verifying Backups Are Running

```bash
# Check scheduled backups
kubectl get scheduledbackup -n cloudnative-pg

# Check latest backup timestamp
kubectl get backup -n cloudnative-pg --sort-by=.metadata.creationTimestamp | tail -5

# Check WAL archiving status
kubectl get cluster -n cloudnative-pg -o jsonpath='{range .items[*]}{.metadata.name}: {.status.firstRecoverabilityPoint}{"\n"}{end}'

# Check S3 for actual backup files
kubectl run -it --rm barman-ls --image=amazon/aws-cli:latest \
  --restart=Never --namespace=cloudnative-pg --overrides='{...}'
```

## Two Backup Systems Summary

```
┌──────────────────────────────────┐    ┌──────────────────────────────────┐
│     PVC BACKUPS (App Data)       │    │   DATABASE BACKUPS (CNPG)        │
│                                  │    │                                  │
│  Tool: VolSync + Kopia           │    │  Tool: CNPG + Barman             │
│  Dest: TrueNAS NFS               │    │  Dest: RustFS S3                 │
│  Auto-restore: YES               │    │  Auto-restore: NO                │
│    (PVC Plumber + Kyverno)       │    │    (manual kubectl create)       │
│  Trigger: PVC label              │    │  Trigger: ScheduledBackup CRD    │
│  Schedule: hourly/daily          │    │  Schedule: hourly + WAL          │
│                                  │    │                                  │
│  Covers:                         │    │  Covers:                         │
│  - App configs                   │    │  - User accounts                 │
│  - Thumbnails/previews           │    │  - Metadata (albums, tags)       │
│  - ML model caches               │    │  - Search indexes                │
│  - Home automation data          │    │  - App state                     │
│                                  │    │                                  │
└──────────────────────────────────┘    └──────────────────────────────────┘
```

## LLM Recovery Prompt Templates

Use these prompts when you want an AI assistant to guide or execute CNPG disaster recovery safely.

### Option A: System Prompt (for agent/custom mode)

```text
You are assisting with CloudNativePG disaster recovery in this repository.

Hard rules:
1) Recovery must bypass ArgoCD apply/SSA path for Cluster creation.
2) Never use kubectl apply for recovery cluster creation; use kubectl create.
3) Verify rendered recovery manifest contains bootstrap.recovery and does not contain bootstrap.initdb.
4) If create fails with AlreadyExists, treat as ArgoCD race; pause reconcile on both immich applications, then retry delete/wait/create.
5) After recovery, revert manifest to initdb mode but keep bumped backup serverName lineage (do not roll back lineage).
6) Always validate restored data with SQL query before declaring success.

Required sequence:
- Confirm backup source lineage (e.g., externalClusters serverName=v2) and backup target lineage (backup serverName=v3).
- Render /tmp/immich-recovery.yaml from kustomize output and verify recovery-only bootstrap.
- Delete cluster and create recovery cluster from /tmp/immich-recovery.yaml.
- Monitor cluster/pods until ready.
- If pod is stuck with volume not ready, check Longhorn volume state and wait for attached/healthy.
- Validate SQL (e.g., SELECT count(*) FROM "user";).
- Revert cluster.yaml to normal initdb mode; keep backup lineage bumped.
- Summarize exactly what changed and next operator actions.

Output requirements:
- Be explicit, command-by-command.
- Explain failures and fallback commands.
- Do not skip verification steps.
```

### Option B: Copy/Paste User Prompt (for ChatGPT/Copilot/Claude)

```text
Help me perform CloudNativePG disaster recovery for Immich in this repo.

Context:
- This cluster uses ArgoCD with self-heal and server-side apply.
- CNPG recovery must be created with kubectl create (not apply).
- Current backup lineage is [FILL ME, e.g. immich-database-v2].
- New backup lineage target is [FILL ME, e.g. immich-database-v3].

What I need from you:
1) Give exact commands to render /tmp/immich-recovery.yaml from kustomize.
2) Include checks to confirm manifest has recovery and no initdb.
3) Give safe delete/create commands for immich-database.
4) Include fallback if kubectl create returns AlreadyExists (Argo race).
5) Include readiness checks and Longhorn attach troubleshooting.
6) Include SQL validation commands to confirm data restored.
7) Include exact post-recovery steps to revert manifest to initdb mode while keeping bumped backup serverName.

Do not skip any verification commands. Explain what success/failure looks like at each step.
```
