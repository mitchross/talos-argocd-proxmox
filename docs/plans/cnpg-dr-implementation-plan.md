# CNPG Disaster Recovery: Implementation Plan for talos-argocd-proxmox

**Target state:** Same DR UX for Postgres as you already have for PVCs — one script, one file per DB, parallel execution across all DBs after a cluster nuke, zero cluster.yaml edits during the DR flow.

**Current state:** Per-DB manual recovery: edit cluster.yaml, bump serverName, pause ArgoCD, delete/sleep 15/create race, verify, revert cluster.yaml, unpause ArgoCD. Multiply by N databases.

**The hard constraints we cannot remove:**
1. CNPG recovery is bootstrap-only (creation-time field). Issue #5203 open since 2024, still not implemented in 1.29.
2. The serverName version bump is required to prevent WAL archive collision — this is the documented pattern in 1.29.
3. CNPG's defaulting webhook adds bootstrap.initdb to any Cluster without an explicit bootstrap. This causes the ArgoCD SSA merge to produce dual-bootstrap manifests.

**The improvements we CAN stack:**
1. The `cnpg.io/validation: disabled` annotation (1.25+) can bypass the dual-bootstrap validation rejection — *if* the reconciler handles it safely. Needs lab verification.
2. Per-DB lineage file outside cluster.yaml makes cluster.yaml immutable during DR.
3. One orchestrator script makes N databases the same amount of work as 1.
4. Barman Cloud Plugin migration cleans up the manifest shape and is required before 1.30.0.
5. VolumeSnapshot + WAL-archive hybrid recovery is first-class in 1.29 and faster than S3-only. Carries known risk (Bug #5056 from 2024 — check if fixed).

---

## Phase 0: Prerequisites and verification

Before changing any production DB, run three lab tests. These answer the three unknowns no amount of documentation can settle.

### Test 0.1 — Dual-bootstrap reconciler behavior (do this first)

**Question answered:** does `cnpg.io/validation: disabled` actually make the annotation+recovery approach safe, or does the reconciler silently prefer initdb and destroy data?

**Setup:**
```bash
# On talos-lab, create a throwaway namespace
kubectl create namespace dr-test-1
```

Deploy a sentinel cluster with Barman Cloud Plugin (prerequisite: you have the plugin installed, or do that as part of Phase 2 first if needed — see "When to order" section below).

```yaml
# dr-test-1-sentinel.yaml
apiVersion: barmancloud.cnpg.io/v1
kind: ObjectStore
metadata:
  name: dr-test-store
  namespace: dr-test-1
spec:
  configuration:
    destinationPath: s3://cnpg-lab-backups/
    endpointURL: http://192.168.10.133:30293  # your RustFS
    s3Credentials:
      accessKeyId:
        name: rustfs-creds
        key: access-key
      secretAccessKey:
        name: rustfs-creds
        key: secret-key
  retentionPolicy: 7d
---
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: sentinel-v1
  namespace: dr-test-1
  annotations:
    cnpg.io/validation: disabled
spec:
  instances: 1
  bootstrap:
    initdb:
      database: app
      owner: app
  storage:
    size: 1Gi
    storageClass: longhorn
  plugins:
    - name: barman-cloud.cloudnative-pg.io
      isWALArchiver: true
      parameters:
        barmanObjectName: dr-test-store
        serverName: sentinel-v1
```

Apply it, insert sentinel data, trigger a backup:
```bash
kubectl apply -f dr-test-1-sentinel.yaml
# wait for it to come up
kubectl cnpg status sentinel-v1 -n dr-test-1
# insert sentinel data
kubectl cnpg psql sentinel-v1 -n dr-test-1 -- -c "CREATE TABLE sentinel (note text); INSERT INTO sentinel VALUES ('ORIGINAL_CLUSTER');"
# trigger backup
kubectl cnpg backup sentinel-v1 -n dr-test-1
# wait for backup to complete
kubectl get backups -n dr-test-1 -w
```

**The actual test — dual bootstrap manifest:**
```yaml
# dr-test-1-dual.yaml
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: dual-test
  namespace: dr-test-1
  annotations:
    cnpg.io/validation: disabled
spec:
  instances: 1
  # DELIBERATELY both bootstrap methods present
  bootstrap:
    initdb:
      database: app
      owner: app
    recovery:
      source: sentinel-origin
  storage:
    size: 1Gi
    storageClass: longhorn
  plugins:
    - name: barman-cloud.cloudnative-pg.io
      isWALArchiver: true
      parameters:
        barmanObjectName: dr-test-store
        serverName: dual-test
  externalClusters:
    - name: sentinel-origin
      plugin:
        name: barman-cloud.cloudnative-pg.io
        parameters:
          barmanObjectName: dr-test-store
          serverName: sentinel-v1
```

Apply, wait, check sentinel data:
```bash
kubectl apply -f dr-test-1-dual.yaml
# wait 5+ minutes for recovery to complete
kubectl cnpg status dual-test -n dr-test-1
kubectl cnpg psql dual-test -n dr-test-1 -- -c "SELECT * FROM sentinel;"
```

**Decision matrix:**

| Result | What it means | Design path |
|--------|---------------|-------------|
| Returns `ORIGINAL_CLUSTER` | Reconciler prefers recovery. Annotation is safe. | **Path A** (below) |
| Returns no table / empty | Reconciler prefers initdb. Annotation is a footgun. | **Path B** |
| Cluster stuck in error state | Reconciler refuses dual-bootstrap. Annotation is neutral. | **Path B** (no silent loss, just annoying) |

### Test 0.2 — Longhorn VolumeSnapshot recovery

**Question answered:** does snapshot-based recovery actually work end-to-end on your Longhorn setup?

**Prereq check:** `kubectl get volumesnapshotclass`. If empty, create a Longhorn one first.

**Skip this test if Test 0.1 returned "Path B"** — you'll be handling bootstrap manifests ephemerally regardless, so snapshot vs S3 is a smaller UX win. Come back to it later if you want speed.

**Setup:** new namespace `dr-test-2`, single-instance cluster on Longhorn, Barman plugin for WAL archive (you'll have this from Test 0.1).

**The test:**
1. Create cluster, insert pre-snapshot sentinel: `INSERT INTO sentinel VALUES ('PRE_SNAP');`
2. Trigger a VolumeSnapshot backup: `kubectl cnpg backup test-vs -n dr-test-2 --method volumeSnapshot`
3. Note the timestamp when snapshot completes.
4. Insert post-snapshot sentinel: `INSERT INTO sentinel VALUES ('POST_SNAP');`
5. Wait ~2 minutes for WAL to archive to S3.
6. Capture current time as `$TARGET_TIME`.
7. Create recovery cluster using hybrid pattern from 1.29 docs — volumeSnapshots for storage, externalClusters for WAL archive, recoveryTarget.targetTime set to `$TARGET_TIME`.
8. Verify: `SELECT * FROM sentinel` should return both `PRE_SNAP` and `POST_SNAP`.

**Decision:**
- Both rows present → snapshot recovery works. Phase 3 (snapshot-primary design) is on the table.
- Only `PRE_SNAP` → WAL replay failed. Stay on S3-primary design.
- Cluster never reaches ready → Longhorn + CNPG snapshot integration broken. Stay on S3-primary.

### Test 0.3 — ArgoCD drift after recovery

**Question answered:** does ArgoCD keep trying to patch `spec.bootstrap` back to the Git-declared value after recovery completes?

**Setup:** pick one of the clusters from Test 0.1 or 0.2. Register it under an ArgoCD Application where the Git manifest declares `bootstrap.initdb` and the live cluster has `bootstrap.recovery`.

**The test:** let ArgoCD sync, wait 10 minutes, observe.

| Result | Action |
|--------|--------|
| Synced/Healthy | No drift rule needed |
| OutOfSync, cluster unchanged | Add `ignoreDifferences` on `/spec/bootstrap` — cosmetic fix |
| OutOfSync + ArgoCD patches cluster | Mandatory `ignoreDifferences` — also consider `Replace=false` sync option |

---

## Path A: Validation-annotation-based flow (if Test 0.1 passed)

This is the cleaner flow. It lets cluster.yaml remain in Git as the source of truth, and DR is handled by a script that uses `kubectl apply` with the annotation suppressing the webhook rejection.

### Repo structure

```
kubernetes/
├── apps/
│   └── databases/
│       ├── _shared/
│       │   ├── object-store.yaml       # Barman Cloud Plugin ObjectStore (one per cluster or per-DB)
│       │   └── kustomization.yaml
│       ├── immich/
│       │   ├── cluster.yaml            # CNPG Cluster, steady-state, with validation annotation
│       │   ├── lineage.yaml            # THE ONE FILE that changes during DR
│       │   └── kustomization.yaml
│       ├── temporal/
│       │   ├── cluster.yaml
│       │   ├── lineage.yaml
│       │   └── kustomization.yaml
│       └── ... (other DBs)
└── scripts/
    ├── dr/
    │   ├── restore-all.sh              # parallel restore across all DBs
    │   ├── restore-one.sh              # single-DB restore
    │   ├── lib/
    │   │   ├── render-recovery.sh      # lineage.yaml + cluster.yaml → recovery manifest
    │   │   ├── wait-ready.sh           # wait for cnpg status to report Healthy
    │   │   └── validate-restore.sh     # psql sentinel check
    │   └── lineage-bump.sh             # post-restore: bump serverName in lineage.yaml
```

### lineage.yaml format

```yaml
# kubernetes/apps/databases/immich/lineage.yaml
# This file tracks DR state for the immich database.
# It is the ONLY file that changes during a restore operation.
#
# Format is stable, human-readable, AI-readable.
db: immich
namespace: immich
# Current write target — all new backups go to this serverName in the object store
currentServerName: immich-v3
# Previous serverName — the source of truth for the next restore
# This is what recovery reads when restoring.
restoreFromServerName: immich-v2
# Recovery target: 'latest' for end-of-WAL, or an RFC3339 timestamp for PITR
restoreTarget: latest
# Last successful restore (for audit)
lastRestored: "2026-03-15T10:22:00Z"
# Whether this DB is currently in a "first-boot, no backups yet" state
firstBoot: false
```

On a fresh DB (never restored), `restoreFromServerName` is null and `firstBoot: true`. The script treats this as "just let initdb run, no recovery needed."

### cluster.yaml template

```yaml
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: immich
  namespace: immich
  annotations:
    # Critical: allows the DR script's apply-with-recovery-manifest to bypass
    # the "only one bootstrap method" validation that ArgoCD-merge triggers.
    cnpg.io/validation: disabled
spec:
  instances: 2
  # Steady-state bootstrap: initdb. During DR, the script patches in recovery.
  bootstrap:
    initdb:
      database: immich
      owner: immich
  storage:
    size: 20Gi
    storageClass: longhorn
  plugins:
    - name: barman-cloud.cloudnative-pg.io
      isWALArchiver: true
      parameters:
        barmanObjectName: immich-store
        # This value comes from lineage.yaml via Kustomize overlay
        # Steady-state cluster.yaml has it hardcoded but the overlay patches it
        serverName: immich-v3  # overlay from lineage.yaml currentServerName
```

### ArgoCD Application config

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: databases
  namespace: argocd
spec:
  source:
    repoURL: https://github.com/mitchross/talos-argocd-proxmox
    path: kubernetes/apps/databases
  destination:
    server: https://kubernetes.default.svc
  syncPolicy:
    automated:
      prune: false     # don't let ArgoCD prune a cluster during DR window
      selfHeal: true   # but do heal other drift
    syncOptions:
      - ServerSideApply=true
  # Per Test 0.3 result, add if needed:
  ignoreDifferences:
    - group: postgresql.cnpg.io
      kind: Cluster
      jsonPointers:
        - /spec/bootstrap  # CNPG ignores this after creation; so should ArgoCD
```

### restore-one.sh (the core script)

```bash
#!/usr/bin/env bash
set -euo pipefail

# Usage: restore-one.sh <db-name>
# Example: restore-one.sh immich

DB="$1"
REPO_ROOT="$(git rev-parse --show-toplevel)"
DB_DIR="$REPO_ROOT/kubernetes/apps/databases/$DB"

if [[ ! -d "$DB_DIR" ]]; then
  echo "ERROR: no directory for db '$DB' at $DB_DIR" >&2
  exit 1
fi

LINEAGE="$DB_DIR/lineage.yaml"
CLUSTER="$DB_DIR/cluster.yaml"

# Parse lineage
NAMESPACE=$(yq '.namespace' "$LINEAGE")
FIRST_BOOT=$(yq '.firstBoot' "$LINEAGE")
RESTORE_FROM=$(yq '.restoreFromServerName' "$LINEAGE")
CURRENT_SN=$(yq '.currentServerName' "$LINEAGE")
RESTORE_TARGET=$(yq '.restoreTarget' "$LINEAGE")

if [[ "$FIRST_BOOT" == "true" ]]; then
  echo "[$DB] firstBoot=true, applying cluster.yaml as initdb"
  kubectl apply -f "$CLUSTER"
  exit 0
fi

if [[ "$RESTORE_FROM" == "null" || -z "$RESTORE_FROM" ]]; then
  echo "ERROR: [$DB] restoreFromServerName is empty but firstBoot=false — inconsistent lineage" >&2
  exit 1
fi

echo "[$DB] Restoring: $RESTORE_FROM -> $CURRENT_SN (target: $RESTORE_TARGET)"

# Check if a live cluster exists. If so, delete it first.
if kubectl get cluster "$DB" -n "$NAMESPACE" &>/dev/null; then
  echo "[$DB] Deleting existing cluster..."
  kubectl delete cluster "$DB" -n "$NAMESPACE"
  # Also clean PVCs — CNPG will not reuse them on recovery
  kubectl delete pvc -n "$NAMESPACE" -l "cnpg.io/cluster=$DB" --ignore-not-found=true
  # Give Longhorn time to actually reclaim
  sleep 15
fi

# Render the recovery manifest from cluster.yaml + lineage.yaml
RECOVERY_MANIFEST=$(mktemp)
trap "rm -f $RECOVERY_MANIFEST" EXIT

# Start from cluster.yaml, mutate with yq:
#   - Replace bootstrap.initdb with bootstrap.recovery
#   - Add externalClusters pointing at restoreFrom serverName
#   - Update plugin parameters.serverName to currentServerName (new write target)
yq eval "
  del(.spec.bootstrap.initdb) |
  .spec.bootstrap.recovery.source = \"origin\" |
  .spec.bootstrap.recovery.database = \"$(yq '.spec.bootstrap.initdb.database' $CLUSTER)\" |
  .spec.bootstrap.recovery.owner = \"$(yq '.spec.bootstrap.initdb.owner' $CLUSTER)\" |
  .spec.externalClusters = [{
    \"name\": \"origin\",
    \"plugin\": {
      \"name\": \"barman-cloud.cloudnative-pg.io\",
      \"parameters\": {
        \"barmanObjectName\": \"$DB-store\",
        \"serverName\": \"$RESTORE_FROM\"
      }
    }
  }]
" "$CLUSTER" > "$RECOVERY_MANIFEST"

# If PITR target is set, add recoveryTarget
if [[ "$RESTORE_TARGET" != "latest" && -n "$RESTORE_TARGET" ]]; then
  yq eval -i ".spec.bootstrap.recovery.recoveryTarget.targetTime = \"$RESTORE_TARGET\"" "$RECOVERY_MANIFEST"
fi

# Apply. The validation annotation lets this through even though ArgoCD's
# steady-state manifest says bootstrap.initdb.
echo "[$DB] Applying recovery manifest..."
kubectl apply -f "$RECOVERY_MANIFEST"

# Wait for cluster to be ready
echo "[$DB] Waiting for cluster to reach Cluster in healthy state..."
if ! "$REPO_ROOT/scripts/dr/lib/wait-ready.sh" "$DB" "$NAMESPACE" 900; then
  echo "ERROR: [$DB] cluster did not become healthy within 15 minutes" >&2
  # Dump diagnostics
  kubectl cnpg status "$DB" -n "$NAMESPACE" || true
  kubectl describe cluster "$DB" -n "$NAMESPACE" || true
  exit 1
fi

# Validate — run the DB-specific validation script if present, otherwise do
# a minimal sentinel check
if [[ -x "$DB_DIR/validate.sh" ]]; then
  echo "[$DB] Running DB-specific validation..."
  "$DB_DIR/validate.sh"
else
  echo "[$DB] Minimal validation: connecting with psql..."
  kubectl cnpg psql "$DB" -n "$NAMESPACE" -- -c "SELECT 1;" > /dev/null
fi

echo "[$DB] Restore complete. Bumping lineage..."
"$REPO_ROOT/scripts/dr/lineage-bump.sh" "$DB"

echo "[$DB] ✓ DONE"
```

### restore-all.sh (parallel version)

```bash
#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
DB_ROOT="$REPO_ROOT/kubernetes/apps/databases"
CONCURRENCY="${CONCURRENCY:-4}"

# Collect all DBs (any directory with a lineage.yaml)
mapfile -t DBS < <(find "$DB_ROOT" -mindepth 2 -maxdepth 2 -name lineage.yaml -exec dirname {} \; | xargs -n1 basename | sort)

echo "Found ${#DBS[@]} databases: ${DBS[*]}"
echo "Running with concurrency $CONCURRENCY"

# Use xargs for simple parallel, with per-DB output files so logs don't interleave
LOG_DIR=$(mktemp -d)
echo "Per-DB logs: $LOG_DIR"

printf '%s\n' "${DBS[@]}" | xargs -n1 -P "$CONCURRENCY" -I {} bash -c "
  echo '=== STARTING {} ==='
  if \"$REPO_ROOT/scripts/dr/restore-one.sh\" {} > \"$LOG_DIR/{}.log\" 2>&1; then
    echo '=== ✓ {} COMPLETE ==='
  else
    echo '=== ✗ {} FAILED (see $LOG_DIR/{}.log) ==='
  fi
"

echo ""
echo "All restores finished."
echo "Logs: $LOG_DIR"
echo ""
echo "NEXT: Review lineage.yaml changes and commit to Git:"
echo "  cd $REPO_ROOT"
echo "  git diff kubernetes/apps/databases/*/lineage.yaml"
echo "  git add kubernetes/apps/databases/*/lineage.yaml"
echo "  git commit -m 'dr: post-restore lineage bump'"
echo "  git push"
```

### lineage-bump.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

DB="$1"
REPO_ROOT="$(git rev-parse --show-toplevel)"
LINEAGE="$REPO_ROOT/kubernetes/apps/databases/$DB/lineage.yaml"

# Current -> previous restoreFrom; bump current to next version
CURRENT=$(yq '.currentServerName' "$LINEAGE")
# Extract numeric suffix; default to 1 if none
if [[ "$CURRENT" =~ ^(.+)-v([0-9]+)$ ]]; then
  BASE="${BASH_REMATCH[1]}"
  N="${BASH_REMATCH[2]}"
  NEXT_N=$((N + 1))
  NEXT="$BASE-v$NEXT_N"
else
  NEXT="$CURRENT-v2"
fi

NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)

yq eval -i "
  .restoreFromServerName = \"$CURRENT\" |
  .currentServerName = \"$NEXT\" |
  .restoreTarget = \"latest\" |
  .lastRestored = \"$NOW\" |
  .firstBoot = false
" "$LINEAGE"

echo "[$DB] Lineage bumped: $CURRENT -> $NEXT"
```

### Cold-nuke runbook (Path A)

```bash
# 1. Cluster is freshly rebuilt. ArgoCD syncs CNPG operator + Barman plugin.
#    Wait for operator pods to be Ready.
kubectl get pods -n cnpg-system -w

# 2. ArgoCD will try to create all Cluster resources from Git manifests.
#    These will come up as empty-initdb — that's fine, we're about to replace them.
#    Do NOT wait for them to be healthy.

# 3. Run the restore orchestrator
cd ~/repos/talos-argocd-proxmox
./scripts/dr/restore-all.sh

# 4. Review lineage updates
git diff kubernetes/apps/databases/*/lineage.yaml

# 5. Commit
git add kubernetes/apps/databases/*/lineage.yaml
git commit -m "dr: post-nuke lineage bumps ($(date -u +%Y-%m-%d))"
git push

# 6. ArgoCD re-reads lineage, sees the new currentServerName, eventually
#    reconciles the cluster.yaml serverName field (via Kustomize overlay).
#    Because CNPG ignores bootstrap post-creation and ignoreDifferences hides
#    drift on that field, no further action needed.
```

This is the target experience: one command, parallel execution, done. The only cluster.yaml edits happen in scripts, not by hand. Git history shows only lineage.yaml commits, which are one-line changes.

---

## Path B: Ephemeral-manifest flow (if Test 0.1 failed)

If the reconciler doesn't safely handle dual-bootstrap-with-validation-annotation, the fallback is the "ephemeral manifest" approach the second LLM advocated for. Same script architecture, different manifest handling.

**Key differences from Path A:**
- cluster.yaml in Git: same (initdb, with validation annotation — doesn't hurt).
- During restore, script generates a manifest with ONLY `bootstrap.recovery` (no initdb), applies with `kubectl create` after deleting the live cluster.
- ArgoCD is briefly at war with you — its Git manifest says initdb. You need to add `ignoreDifferences` on `/spec/bootstrap` at minimum. You may also need `spec.syncPolicy.automated.selfHeal: false` on the databases ApplicationSet during the restore window.

**The race window problem:** Between `kubectl delete cluster` and `kubectl create -f recovery.yaml`, ArgoCD's reconcile loop could fire. This is what the sleep-15 dance in your current runbook is for. Path B inherits this. Options to mitigate:
1. Set `selfHeal: false` on the databases Application during DR, re-enable after.
2. Patch the Application to `syncPolicy: {}` during DR (fully disables sync), reapply after.
3. Rely on speed + the 2-second ArgoCD sync wave delay. Works most of the time, not always.

**Script changes for Path B:** the `restore-one.sh` above stays mostly the same, with these edits:
- Replace `kubectl apply -f "$RECOVERY_MANIFEST"` with `kubectl create -f "$RECOVERY_MANIFEST"`.
- Before the create, pause ArgoCD selfheal for the databases Application:
  ```bash
  kubectl patch app databases -n argocd --type merge \
    -p '{"spec":{"syncPolicy":{"automated":{"selfHeal":false}}}}'
  ```
- After the create + wait-ready, restore selfheal:
  ```bash
  kubectl patch app databases -n argocd --type merge \
    -p '{"spec":{"syncPolicy":{"automated":{"selfHeal":true}}}}'
  ```

Everything else — lineage.yaml, parallel orchestrator, validation scripts — is identical.

---

## Phase 1: Migrate to Barman Cloud Plugin (do this regardless of Path A/B)

This is decoupled from the DR work but required before CNPG 1.30.0. Doing it first makes cluster.yaml smaller, which makes the DR work cleaner.

**Migration per DB:**

1. Create `ObjectStore` resource in the DB's namespace (or a shared one, if DBs share a bucket with different serverNames):
   ```yaml
   apiVersion: barmancloud.cnpg.io/v1
   kind: ObjectStore
   metadata:
     name: immich-store
     namespace: immich
   spec:
     configuration:
       destinationPath: s3://cnpg-backups/
       endpointURL: http://192.168.10.133:30293
       s3Credentials:
         accessKeyId:
           name: rustfs-creds
           key: access-key
         secretAccessKey:
           name: rustfs-creds
           key: secret-key
     retentionPolicy: 30d  # moved from Cluster.spec.backup.retentionPolicy
   ```

2. In the Cluster manifest, in a **single commit**:
   - Remove `spec.backup.barmanObjectStore` entirely.
   - Remove `spec.backup.retentionPolicy`.
   - Add `spec.plugins[]` entry for `barman-cloud.cloudnative-pg.io`.
   - Update any `externalClusters` entries to use `plugin:` instead of `barmanObjectStore:`.
   - Update any `ScheduledBackup` resources to use `method: plugin` and `pluginConfiguration:`.

3. Wait for next scheduled backup to complete against the new plumbing. Verify files appear in the bucket under the expected `serverName` path.

**Recommended order:**
- Test on the smallest/least critical DB first (pick one where data loss would be annoying but not catastrophic).
- Wait 24 hours after migration to confirm scheduled backups are still flowing.
- Migrate remaining DBs in batches of 2-3 per day.
- Keep the `cnpg-1.30.0-upgrade` branch open in your mind as the forcing function — you need all DBs migrated before you take that upgrade.

**What Phase 1 does NOT do:** it does not change your DR workflow. Manual recovery still works the same way post-migration, just with the new manifest shape. Phase 1 is pure plumbing cleanup.

---

## Phase 2: Build the orchestration (post Test 0.1)

This is where you implement either Path A or Path B. The work is the same shape either way — the difference is which primitives the script uses internally.

**Order of implementation:**

1. **Create the repo structure** — empty lineage.yaml files, unchanged cluster.yaml files, placeholder scripts.

2. **Write the scripts** — restore-one, restore-all, lineage-bump, wait-ready, render-recovery. Keep validation scripts optional/per-DB.

3. **Test on one DB in talos-lab** — pick a non-critical DB, restore it through the script once, verify data, check lineage.yaml was updated correctly.

4. **Test parallel restore in talos-lab** — create 3 small test DBs, nuke them, run restore-all, verify all three recovered independently.

5. **Test cold nuke** — completely wipe talos-lab, let ArgoCD rebuild, run restore-all, verify all DBs come back. This is the real test. Schedule a weekend session for this.

6. **Roll out to prod** — once talos-lab cold-nuke works reliably:
   - Add lineage.yaml to each production DB (start with firstBoot: false, restoreFromServerName matching current serverName).
   - Add the validation annotation to each production Cluster.
   - Do NOT run restore on prod — these are live DBs.
   - The first real prod use of this flow is the next scheduled DR drill or actual DR event.

**Quarterly DR drill (new practice):** pick one prod DB per quarter, restore it to a disposable namespace using the script, validate, document the time it took. This keeps the muscle memory and catches regressions.

---

## Phase 3: Snapshot recovery (optional, only if Test 0.2 passed)

This is an enhancement, not a requirement. The S3-only flow works fine; snapshots are a speed upgrade.

**Before doing this: verify Bug #5056 resolution.** The 2024 report of data loss with VolumeSnapshot + WAL archive recovery is concerning. Check its status before proceeding:

```bash
# Check if the issue is closed with a fix
# https://github.com/cloudnative-pg/cloudnative-pg/issues/5056
```

If unresolved, stop here and stay on S3-only.

If resolved or you've independently confirmed consistency in Test 0.2:

**Architecture shift:**
- lineage.yaml gains a new field: `restoreFromSnapshot: <volumesnapshot-name>`.
- The restore script checks: if snapshot exists, use hybrid (snapshot + WAL). If not, fall back to S3-only.
- Backups are configured to take periodic VolumeSnapshots via ScheduledBackup with `method: volumeSnapshot`, keeping ~7 days of snapshots in the namespace.
- WAL archive via Barman Cloud Plugin continues regardless — it's needed for PITR in both modes.

**Snapshot garbage collection:** VolumeSnapshots are Kubernetes resources that need lifecycle management. Options:
- CNPG's retention policy handles backup retention but you may need separate logic for orphaned snapshots.
- Simple cron-based cleanup: delete snapshots older than N days that aren't referenced in any lineage.yaml.

**When to pick which mode in the script:**
```bash
# Pseudo-code inside restore-one.sh
SNAPSHOT_NAME=$(yq '.restoreFromSnapshot // ""' "$LINEAGE")
if [[ -n "$SNAPSHOT_NAME" ]] && kubectl get volumesnapshot "$SNAPSHOT_NAME" -n "$NAMESPACE" &>/dev/null; then
  # Generate hybrid manifest (snapshot + WAL)
  render_hybrid_recovery > "$RECOVERY_MANIFEST"
else
  # Fallback to S3-only recovery
  render_s3_recovery > "$RECOVERY_MANIFEST"
fi
```

---

## Failure modes and their responses

| Symptom | Likely cause | Response |
|---------|-------------|----------|
| Cluster stuck in `Setting up primary`, logs show `Expected empty archive` | serverName collision with existing backup data | lineage.yaml currentServerName was not actually a fresh name. Check previous commits to lineage.yaml history. Bump again to a known-fresh value. |
| Recovery pod errors with "Cannot restore, PGDATA exists" | PVC from previous cluster attempt still attached | Script didn't delete PVCs before recreate. Delete manually: `kubectl delete pvc -n $NS -l cnpg.io/cluster=$DB` and retry. |
| Cluster comes up but sentinel validation fails | Reconciler picked initdb path despite recovery intent | Reproduces Test 0.1 failure. Switch to Path B (ephemeral manifests). |
| ArgoCD immediately re-patches the recovery cluster back to initdb | ignoreDifferences not configured, or selfHeal too fast | Apply ignoreDifferences rule from Path A config, or disable selfHeal for the databases Application for the duration. |
| Parallel restore: some DBs succeed, some hang indefinitely | Longhorn PVC provisioning serialized, backpressure | Reduce CONCURRENCY env var. Your Longhorn setup may not handle 4 parallel large-disk provisions. |
| restore-all.sh reports success but one DB has stale data | WAL replay didn't reach target, exited early | Check `kubectl cnpg status $DB -n $NS` for "Current WAL" — compare to expected end-of-WAL. If mismatched, check barman archive in S3 for gaps. |

## What to actually deliver first

Realistically, your first PR should contain only these things:

1. **Test 0.1 results documented** — in `docs/cnpg-disaster-recovery.md`, add a section "2026 investigation" with what you found running the dual-bootstrap experiment.
2. **Barman Cloud Plugin installed** — the operator and CRDs in place, but no DBs migrated yet.
3. **One DB migrated to the plugin** — your smallest, to validate the plumbing. Don't touch DR workflow yet.

That's one weekend of work. It de-risks Phase 1, gives you the Path A/B decision data, and doesn't change your DR runbook yet.

From there, Phase 2 implementation is probably 2-3 weekends: building the scripts, testing on talos-lab, then a cold-nuke rehearsal. Phase 3 is optional and can wait for a quiet month.

## One more honest note

Everything in this plan is based on documented CNPG behavior as of 1.29 (March 2026). The three lab tests exist specifically because some things — like the dual-bootstrap reconciler behavior — are undocumented and can only be verified empirically. The plan is robust to either outcome of Test 0.1, which is why it has a Path A and a Path B. Run the tests first, commit to a path, then build.

If Issue #5203 (in-place recovery) is ever implemented upstream, throw this whole plan out and use that instead. But it's been open 20 months with no movement, so don't wait.
