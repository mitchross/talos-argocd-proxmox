# CNPG Database Disaster Recovery

## Overview

CloudNativePG (CNPG) databases are backed up via **Barman** to RustFS S3 (`s3://postgres-backups/cnpg/`). Unlike PVC backups (which auto-restore via Kyverno + PVC Plumber), database recovery is **manual** and must bypass ArgoCD.

## Why Recovery Can't Go Through ArgoCD

ArgoCD uses **Server-Side Apply (SSA)**. CNPG has a **mutating admission webhook** that adds `initdb` defaults to every Cluster creation. When combined:

1. ArgoCD sends SSA patch with `bootstrap.recovery`
2. CNPG webhook intercepts and adds `bootstrap.initdb` defaults
3. SSA merges both field managers — `initdb` wins
4. Result: fresh empty database, every time

Additionally, ArgoCD ApplicationSets enforce `selfHeal: true`, recreating deleted clusters in sub-second — too fast to manually intervene.

**Solution**: Apply recovery manifests directly with `kubectl create`, bypassing ArgoCD entirely.

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
| immich | `s3://postgres-backups/cnpg/immich` | `immich-database-v2` | Hourly + WAL |
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

**3. Extract just the Cluster resource:**

```bash
kubectl kustomize infrastructure/database/cloudnative-pg/immich/ \
  | awk '/^apiVersion: postgresql.cnpg.io\/v1/{p=1} p{print} /^---/{if(p) exit}' \
  > /tmp/immich-recovery.yaml

# Verify it has recovery, not initdb:
grep -c "recovery" /tmp/immich-recovery.yaml  # should be >= 1
grep -c "initdb" /tmp/immich-recovery.yaml    # should be 0
```

**4. Delete and immediately recreate (one command — ArgoCD is fast):**

```bash
kubectl delete cluster immich-database -n cloudnative-pg --wait=false; \
  sleep 15; \
  kubectl create -f /tmp/immich-recovery.yaml
```

The 15-second sleep ensures old PVCs are cleaned up by Longhorn.

If you get `AlreadyExists`, ArgoCD recreated the Cluster first. Use this fallback, then retry step 4:

```bash
# Temporarily pause reconcile for both immich apps
kubectl annotate application immich -n argocd argocd.argoproj.io/skip-reconcile=true --overwrite
kubectl annotate application my-apps-immich -n argocd argocd.argoproj.io/skip-reconcile=true --overwrite

# Retry delete/create with explicit delete wait
kubectl delete cluster immich-database -n cloudnative-pg --wait=false
kubectl wait --for=delete cluster/immich-database -n cloudnative-pg --timeout=180s
kubectl create -f /tmp/immich-recovery.yaml
```

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
- Uncomment `initdb` bootstrap
- Comment out `recovery` bootstrap + `externalClusters`
- Keep the new `serverName` in the backup section (e.g. `immich-database-v3`)
- Update the commented recovery `externalClusters.serverName` for next time (e.g. `immich-database-v3`)

```bash
git add infrastructure/database/cloudnative-pg/immich/cluster.yaml
git commit -m "CNPG: revert immich to initdb after successful recovery"
git push
```

ArgoCD syncs. CNPG ignores `initdb` bootstrap on existing clusters — your data is safe.

### Quick Example Timeline (Immich)

- Before nuke: backups writing to `immich-database-v2`
- Recovery manifest: restore from `v2`, write new backups to `v3`
- After recovery: normal manifest with `initdb` active, backup still on `v3`
- Next DR event: restore from `v3`, then bump backup target to `v4`

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

**Cause**: `selfHeal: true` in ApplicationSet template.

**Fix**: Use `delete --wait=false; sleep 15; kubectl create` in rapid succession. The sleep gives PVCs time to terminate.

If Argo still wins and `kubectl create` returns `AlreadyExists`, temporarily annotate both Applications with `argocd.argoproj.io/skip-reconcile=true`, then retry delete/wait/create.

### `Error from server (AlreadyExists)` during `kubectl create`

**Cause**: ArgoCD recreated `immich-database` before your manual create landed.

**Fix**:
1. Pause reconcile for `immich` and `my-apps-immich` Applications.
2. `kubectl delete ... --wait=false` + `kubectl wait --for=delete ...`.
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
