# CNPG Barman Cloud Plugin Migration Plan

**Status:** Draft — for human review before any cluster YAML changes.
**Branch:** `cnpg-plugin-migration` (off `main`).
**Scope:** Migrate the four production CNPG `Cluster` CRs (immich, gitea,
paperless, temporal) from the deprecated in-tree
`spec.backup.barmanObjectStore` shape to the modern `spec.plugins[]` +
sibling `ObjectStore` CR shape provided by the `barman-cloud.cnpg.io`
plugin.
**Author:** cluster (tempo-soloist), 2026-05-07.
**Last verified live cluster state:** 2026-05-07 (commands captured during
plan authoring; see § "Current state per cluster").

---

## TL;DR

CNPG removed in-tree `spec.backup.barmanObjectStore` in 1.30.0. We're on
1.29.0 today, so it still works, but a Renovate bump to 1.30+ would brick
all four database backup paths simultaneously. Upstream provides a
documented seamless migration: create one `ObjectStore` CR per cluster,
swap `spec.backup.barmanObjectStore` → `spec.plugins[]` in a single atomic
edit, switch `ScheduledBackup.spec.method` to `plugin`. CNPG performs a
rolling restart of each Postgres pod (single-instance clusters → ~30 s of
downtime per DB), no primary failover, no WAL gap if `serverName` is
preserved through `parameters.serverName`.

Recommended order: **temporal → paperless → gitea → immich**. One DB
per session, verify backup successfully written via plugin path before
proceeding to the next. ArgoCD `selfHeal: false` on the database AppSet
keeps changes manual. **Open question: confirm `parameters.serverName`
override in plugin shape — our v1/v2 lineage prefixes must keep being
written to the same RustFS prefixes.** No execution until that is
verified.

---

## 1. Current state

### 1.1 Versions live in cluster (verified 2026-05-07)

| Component | Live image | Source pin |
|---|---|---|
| CNPG operator | `ghcr.io/cloudnative-pg/cloudnative-pg:1.29.0` | Helm chart `cloudnative-pg` v0.28.0 in `infrastructure/database/cloudnative-pg/cloudnative-pg-operator/kustomization.yaml` |
| Barman Cloud plugin | `ghcr.io/cloudnative-pg/plugin-barman-cloud:v0.12.0` | Raw manifest at the v0.12.0 tag in `infrastructure/database/cnpg-barman-plugin/kustomization.yaml` |

The plugin is **already installed and healthy** (`barman-cloud-7655994b79-dcx4f`
in `cnpg-system`, Running 2d10h). No infrastructure changes needed; this
plan only touches the four database manifests.

CNPG 1.29 still accepts `spec.backup.barmanObjectStore`. Removal is in
1.30.0 per upstream docs. Renovate auto-update is the immediate risk.

### 1.2 Per-cluster snapshot

All four are single-instance (`instances: 1`), `storageClass: longhorn`,
`monitoring.enablePodMonitor: true`, `enableSuperuserAccess: true`. All
four use the same RustFS endpoint `http://192.168.10.133:30293` and share
the same S3 SecretRef `cnpg-s3-credentials` (managed by an ExternalSecret
in `cloudnative-pg/postgres-global-secrets/`).

| Cluster | Source path | serverName | Bucket / prefix | Retention | Schedule | Last backup | Active overlay |
|---|---|---|---|---|---|---|---|
| immich | `cloudnative-pg/immich/` | `immich-database-v1` | `s3://postgres-backups/cnpg/immich` | `14d` | daily 02:00 | 2026-05-07T02:00:21Z | `overlays/initdb` |
| gitea | `cloudnative-pg/gitea/` | `gitea-database-v2` | `s3://postgres-backups/cnpg/gitea` | `14d` | daily 04:00 | 2026-05-07T04:00:11Z | **`overlays/recovery`** (mid-DR cleanup) |
| paperless | `cloudnative-pg/paperless/` | `paperless-database-v1` | `s3://postgres-backups/cnpg/paperless` | `14d` | daily 05:00 | 2026-05-07T05:00:10Z | `overlays/initdb` |
| temporal | `cloudnative-pg/temporal/` | `temporal-database-v2` | `s3://postgres-backups/cnpg/temporal` | `14d` | daily 03:00 | 2026-05-07T03:01:15Z | `overlays/initdb` |

All four show `ContinuousArchiving=True` in `.status.conditions` and have
`firstRecoverabilityPoint` matching the lineage open date. WAL archiving
is healthy.

### 1.3 gitea-specific note (READ THIS BEFORE ORDERING)

`infrastructure/database/cloudnative-pg/gitea/kustomization.yaml` has
`overlays/recovery` ACTIVE and `overlays/initdb` commented out. The live
cluster is healthy on v2 (Barman recovery completed 2026-05-02 from v1).
The recovery overlay is **dormant** at runtime — `spec.bootstrap` is only
consulted at cluster creation; CNPG ignores it on existing clusters.

But `spec.externalClusters[]` is still in the live spec because Argo
rendered it from `overlays/recovery/bootstrap-patch.yaml`. That block uses
`barmanObjectStore` (in-tree shape) and would need to be converted to
plugin shape too — even though it's dormant — because git-vs-cluster diff
matters for ArgoCD sync health.

**Two options**:

**A. Flip gitea back to `overlays/initdb` BEFORE migration** (clean — restores
steady-state git, removes the dormant `externalClusters[]` block entirely).
Requires no live-cluster mutation; just a kustomization.yaml swap and an
ArgoCD sync.

**B. Migrate gitea on `overlays/recovery` and translate the externalClusters
block too**. More YAML churn for what is dormant config; preserves the DR
overlay shape but in plugin form.

**Recommend A** — flip-back as a one-line PR before this migration starts,
land it, verify gitea still healthy, then proceed with the plugin migration.

### 1.4 Files in scope per cluster

For each `<cluster>` in {immich, gitea, paperless, temporal}:

```
infrastructure/database/cloudnative-pg/<cluster>/
├── base/cluster.yaml             ← MODIFY (remove backup.barmanObjectStore, add plugins[])
├── base/kustomization.yaml       ← MODIFY (add objectstore.yaml to resources)
├── overlays/recovery/bootstrap-patch.yaml  ← MODIFY (translate externalClusters to plugin shape)
├── scheduled-backup.yaml         ← MODIFY (add method: plugin + pluginConfiguration)
├── objectstore.yaml              ← NEW (sibling ObjectStore CR)
└── kustomization.yaml            ← unchanged
```

Sync-wave annotation on the new `ObjectStore` CR should ensure it is
reconciled BEFORE the Cluster mod takes effect; current pattern uses
`commonAnnotations.argocd.argoproj.io/sync-wave: "-5"` at the root, and
the postgres-demo reference uses `"0"` on its ObjectStore. Will use `"-6"`
on each cluster's ObjectStore to land before the Cluster (which inherits
`-5`).

---

## 2. Target state

### 2.1 Per-cluster target shape

For each cluster, the target is the postgres-demo reference shape adapted
to our existing serverName lineage. Example for **temporal** (others are
analogous):

**`base/cluster.yaml` (modified)** — remove the entire `spec.backup` block
and add `spec.plugins[]`:

```yaml
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: temporal-database
  labels:
    app: temporal
spec:
  instances: 1
  imageName: ghcr.io/cloudnative-pg/postgresql:16.2
  resources: { ... unchanged ... }
  postgresql: { ... unchanged ... }
  storage: { ... unchanged ... }
  walStorage: { ... unchanged ... }
  enableSuperuserAccess: true
  monitoring:
    enablePodMonitor: true
  plugins:
    - name: barman-cloud.cloudnative-pg.io
      isWALArchiver: true
      parameters:
        barmanObjectName: temporal-database-backups   # name of sibling ObjectStore CR
        serverName: temporal-database-v2              # PRESERVES our existing lineage prefix on RustFS
  # NOTE: spec.backup removed entirely. retentionPolicy moves to ObjectStore.
```

**`objectstore.yaml` (new)** — sibling CR holding the S3 destination + retention:

```yaml
apiVersion: barmancloud.cnpg.io/v1
kind: ObjectStore
metadata:
  name: temporal-database-backups
  namespace: cloudnative-pg
  annotations:
    argocd.argoproj.io/sync-wave: "-6"   # before Cluster (-5)
spec:
  configuration:
    destinationPath: s3://postgres-backups/cnpg/temporal
    endpointURL: http://192.168.10.133:30293
    s3Credentials:
      accessKeyId:
        name: cnpg-s3-credentials
        key: AWS_ACCESS_KEY_ID
      secretAccessKey:
        name: cnpg-s3-credentials
        key: AWS_SECRET_ACCESS_KEY
    wal:
      compression: gzip
    data:
      compression: gzip
  retentionPolicy: "14d"
```

**`base/kustomization.yaml` (modified)** — add `objectstore.yaml`:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - cluster.yaml
  - objectstore.yaml   # NEW
```

**`scheduled-backup.yaml` (modified)** — set method + pluginConfiguration:

```yaml
apiVersion: postgresql.cnpg.io/v1
kind: ScheduledBackup
metadata:
  name: temporal-daily-backup
  namespace: cloudnative-pg
spec:
  schedule: "0 0 3 * * *"     # unchanged
  backupOwnerReference: self
  cluster:
    name: temporal-database
  immediate: true
  method: plugin                         # NEW
  pluginConfiguration:                   # NEW
    name: barman-cloud.cloudnative-pg.io
```

**`overlays/recovery/bootstrap-patch.yaml` (modified)** — translate
`externalClusters[].barmanObjectStore` → `externalClusters[].plugin`:

```yaml
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: temporal-database
spec:
  bootstrap:
    recovery:
      source: temporal-recovery-source
  externalClusters:
    - name: temporal-recovery-source
      plugin:
        name: barman-cloud.cloudnative-pg.io
        parameters:
          barmanObjectName: temporal-database-backups   # SAME ObjectStore as runtime
          serverName: temporal-database-v1              # PRIOR lineage to restore from
```

Note: in the externalCluster plugin shape, the `barmanObjectName` is the
SAME ObjectStore CR (same destinationPath, credentials), with `serverName`
parameter telling the plugin to read from the v1 prefix. This works
because all our lineages live in the same bucket under the same prefix
(`s3://postgres-backups/cnpg/<app>/`) — they only differ by serverName
suffix. The plugin's serverName parameter selects which lineage subtree
to read.

### 2.2 Bucket / prefix / retention preservation

| Field | In-tree | Plugin |
|---|---|---|
| Bucket | `s3://postgres-backups/cnpg/<app>` | **identical** (`destinationPath` on ObjectStore) |
| Endpoint | `http://192.168.10.133:30293` | **identical** |
| SecretRef | `cnpg-s3-credentials` | **identical** |
| serverName | e.g. `immich-database-v1` | **identical** via `plugins[].parameters.serverName` |
| Compression | gzip (wal+data) | **identical** |
| Retention | `14d` on Cluster | **identical, moves to ObjectStore.spec.retentionPolicy** |

We are NOT migrating to a new bucket. We are NOT changing serverName. We
are NOT rotating credentials. The only thing that changes is **which CRD
field carries the configuration**.

### 2.3 RustFS lifecycle policy

`infrastructure/storage/rustfs-lifecycle/postgres-backups-lifecycle-cm.yaml`
encodes per-prefix expiration rules referencing the abandoned-lineage
prefixes (gitea-database-v1, temporal-database-v1). Those rules are
serverName-prefix-based on object keys; the plugin writes to the same key
prefixes, so **no lifecycle policy changes are needed**.

---

## 3. Operator-behavior risk analysis

### 3.1 What the upstream migration doc explicitly says

(Source: <https://cloudnative-pg.io/plugin-barman-cloud/docs/migration/>)

- The Cluster spec change is a **single atomic edit**: remove
  `.spec.backup.barmanObjectStore` (and `.spec.backup.retentionPolicy`),
  add `.spec.plugins[]`.
- **This triggers a rolling update of the Cluster.** Each Postgres pod is
  recreated to gain the `plugin-barman-cloud` sidecar container.
- ScheduledBackup conversion is independent of the Cluster change and can
  be deferred.
- externalClusters conversion is required if the cluster is bootstrapped
  via Barman recovery; otherwise dormant.

### 3.2 What the doc does NOT explicitly say (verified gaps)

- **Existing WAL chains and base backups remain readable**: not stated in
  the doc, but the practitioner blog (mei-home.net) reports continuous
  archiving through the migration with no gap, when serverName is preserved.
  The plugin uses the same Barman storage layout, so existing prefixes are
  readable.
- **Dual-config not supported**: removing in-tree and adding plugin is a
  single atomic change. There is no "dual write" mode.
- **Rollback procedure**: undocumented officially, but symmetric to the
  forward path — revert YAML, CNPG performs another rolling restart back
  to in-tree. No state lost on the storage side because the same prefix
  keeps receiving WAL.

### 3.3 Restart impact

- **Single instance** = the rolling update is "stop primary, recreate pod,
  start primary." No failover target. Brief connection drop while the new
  pod starts (Longhorn RWO PVC re-attaches, Postgres opens, plugin sidecar
  becomes ready).
- Empirically: ~30–60 s of unavailability per cluster.
- Apps that use these DBs (immich web, gitea, paperless-ngx, temporal
  workers) WILL see connection errors. Most reconnect cleanly. Notable:
  **temporal** workflow workers cache connections aggressively — schedule
  this when nobody is actively running production workflows.

### 3.4 Vector / vchord extension risk (immich only)

immich uses `shared_preload_libraries: vchord.so` and
`ghcr.io/tensorchord/cloudnative-vectorchord:17.5-0.4.3`. The plugin
sidecar runs in a separate container; the Postgres container is
unchanged. **Plugin should be image-agnostic** but flag for explicit
verification: confirm temporal/paperless/gitea succeed first, then
attempt immich with a manual backup before the next ScheduledBackup tick.

### 3.5 Failure modes considered

| Failure | Detection | Recovery |
|---|---|---|
| ObjectStore CR rejected by webhook (typo, bad SecretRef) | `kubectl get objectstore -n cloudnative-pg <name> -o yaml` shows error | Fix YAML, commit |
| Cluster YAML rejected by CNPG webhook | `kubectl get cluster ... -o jsonpath='{.status.conditions}'` | Argo shows OutOfSync, no live mutation |
| Pod fails to start with sidecar (image pull, RBAC, mount) | `kubectl describe pod` | Revert Cluster YAML, kubectl apply old shape, sync |
| WAL archiving silent failure post-restart | `.status.conditions[ContinuousArchiving]` flips to False; `kubectl logs -c plugin-barman-cloud` | Investigate plugin logs, fix; if irrecoverable, revert |
| `plugins[].parameters.serverName` not honored, plugin writes to default `<cluster-name>` prefix | RustFS shows new objects under e.g. `temporal-database/` instead of `temporal-database-v2/` | **CRITICAL** — would split backup lineage. See § 9.1. |

---

## 4. Recommended migration order per cluster

For each cluster, in sequence:

1. **Pre-flight** (manual, read-only):
   - `kubectl get cluster -n cloudnative-pg <c> -o jsonpath='{.status.conditions[?(@.type=="ContinuousArchiving")].status}'` → must be `True`
   - `kubectl get cluster -n cloudnative-pg <c> -o jsonpath='{.status.lastSuccessfulBackup}'` → within last 24h
   - Verify a recent backup is restorable: optionally do a **dry-run** `kubectl cnpg backup` (creates a Backup CR via the existing in-tree path) to confirm the fallback path is alive
   - `kubectl describe cluster -n cloudnative-pg <c>` → no warning events in the last hour

2. **Land YAML in git** (one PR per cluster, or one PR all four — recommend
   per-cluster for blast-radius isolation):
   - Add `objectstore.yaml`
   - Update `base/cluster.yaml` (remove backup.barmanObjectStore, add plugins[])
   - Update `base/kustomization.yaml` to include `objectstore.yaml`
   - Update `scheduled-backup.yaml` (add method + pluginConfiguration)
   - Update `overlays/recovery/bootstrap-patch.yaml` (plugin externalCluster)

3. **ArgoCD sync** (manual — selfHeal: false):
   - User opens ArgoCD UI for the database app
   - Reviews the diff: confirms ObjectStore is created, Cluster diff matches expectation
   - Click Sync. Watch Sync history.

4. **Live verification** (within 5 minutes of sync):
   - `kubectl get objectstore -n cloudnative-pg <c>-database-backups` → ready
   - `kubectl get pods -n cloudnative-pg <c>-database-1 -o jsonpath='{.spec.containers[*].name}'` → contains `plugin-barman-cloud`
   - `kubectl logs -n cloudnative-pg <c>-database-1 -c plugin-barman-cloud --tail=50` → see WAL archive lines
   - `kubectl get cluster -n cloudnative-pg <c>-database -o jsonpath='{.status.conditions[?(@.type=="ContinuousArchiving")].status}'` → still `True`
   - `kubectl cnpg backup <c>-database -n cloudnative-pg --method=plugin` → manual base backup completes successfully
   - Verify the new base backup landed in the **same RustFS prefix** as before:
     ```
     kubectl exec -it -n volsync-system deploy/pvc-plumber -- ls -la /repository  # NOT this — pvc-plumber is for kopia, not S3
     # Use rustfs-mc or s3 client against http://192.168.10.133:30293
     ```
     (This step requires either an in-cluster MinIO client pod or running the
     mc client locally with the rustfs creds. Spelling out: an mc-client pod
     spec is included in § 7.)

5. **Wait for next scheduled backup tick**:
   - Whichever cluster's daily slot fires next, watch `kubectl get backup -n cloudnative-pg`
   - Confirm Backup CR succeeds
   - Confirm `.status.lastSuccessfulBackup` advances

6. **Move to next cluster** only after current is fully verified.

### 4.1 Cluster ordering (rationale)

| Order | Cluster | Why |
|---|---|---|
| 1 | **temporal** | Smallest data (10Gi), single workflow worker, easy to recover from PITR if anything breaks. Most "developer" stakes — no end-user impact. |
| 2 | **paperless** | Medium data (50Gi). Has a `LoadBalancer` Service for external access (`paperless-postgres-external` at 192.168.10.42) but that's the live read path, unaffected by backup migration. Single user. |
| 3 | **gitea** | After flipping back to `overlays/initdb` (per § 1.3, Option A). Pre-step PR lands first, verify steady-state, then plugin-migrate. |
| 4 | **immich** | Largest data (50Gi+50Gi WAL), vchord extension complexity, most-used app. Migrate last with the most learnings already absorbed. |

### 4.2 Pacing

Don't migrate all four in one session. Recommended cadence: **one cluster
per day**, watch the next-day's ScheduledBackup tick land successfully
before starting the next cluster. Total wall-clock: ~4–5 days end-to-end
for the migration itself, plus 1 day each for the gitea overlay flip-back
and post-migration cleanup.

---

## 5. ArgoCD interaction

### 5.1 selfHeal: false preserves manual control

The database AppSet
(`infrastructure/controllers/argocd/apps/appsets/database-appset.yaml`)
sets `syncPolicy.automated: { selfHeal: false }`. After committing to git
the cluster shows OutOfSync until the user clicks Sync — desired
behavior.

### 5.2 Sync-wave inside the database Application

Current pattern:
- `commonAnnotations.argocd.argoproj.io/sync-wave: "-5"` on the root
  `kustomization.yaml` for each cluster directory
- ScheduledBackup inherits the same wave via commonAnnotations

New pattern adds:
- ObjectStore CR with explicit `argocd.argoproj.io/sync-wave: "-6"` so it
  reconciles BEFORE the Cluster modification triggers the rolling restart

**Critical**: kustomize `commonAnnotations` does NOT override per-resource
`metadata.annotations`. The ObjectStore explicit `-6` wins; the Cluster
inherits `-5` from the directory. ScheduledBackup inherits `-5`. We do
not need to set `-7` on ScheduledBackup because `method: plugin` is
ignored until the Cluster has the plugin loaded; once loaded, the
existing Schedule semantics resume.

### 5.3 skip-reconcile annotations

DR runbooks reference `argocd.argoproj.io/skip-reconcile=true` for
freezing a Cluster during recovery. The migration adds no new annotation.
If a user has skip-reconcile set on a cluster during this migration, the
ArgoCD sync will skip that resource. Verify all four clusters have NO
skip-reconcile set before starting:

```bash
for c in immich gitea paperless temporal; do
  kubectl get cluster -n cloudnative-pg ${c}-database \
    -o jsonpath='{.metadata.annotations.argocd\.argoproj\.io/skip-reconcile}{"\n"}'
done
```

Empty output = good.

### 5.4 ServerSideApply

The database Application uses SSA. The plugin migration removes a top-
level field (`spec.backup`) and adds a new one (`spec.plugins`). SSA
should handle this cleanly because no other field manager owns
`spec.backup` — CNPG owns the live spec, ArgoCD's manager owns what's in
git, and the diff is a clean replace. **Watch for stale-field-manager
warnings during sync** as a sanity check.

---

## 6. Cross-cluster ordering (ALREADY COVERED IN § 4.1)

One cluster at a time. **Recommended sequence: temporal → paperless →
gitea (after flip-back) → immich**. Don't parallelize.

---

## 7. Pre-flight checks

### 7.1 Plugin install health

```bash
kubectl get deploy -n cnpg-system barman-cloud
kubectl get pods -n cnpg-system -l app=barman-cloud
kubectl get crd objectstores.barmancloud.cnpg.io
```

Expect: 1/1 ready, ObjectStore CRD installed.

### 7.2 Operator version

```bash
kubectl get deploy -n cloudnative-pg cloudnative-pg-operator \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
```

Expect: `ghcr.io/cloudnative-pg/cloudnative-pg:1.29.0` (in-tree backup still
supported). Block migration if Renovate has bumped to 1.30+ already (in-tree
gone, this whole plan changes posture from elective to emergency).

### 7.3 Each cluster has recent successful backup

```bash
for c in immich gitea paperless temporal; do
  echo "=== $c ==="
  kubectl get cluster -n cloudnative-pg ${c}-database \
    -o jsonpath='{.status.lastSuccessfulBackup}{"\n"}'
done
```

Expect: timestamp within last 24 h. Block migration on any cluster whose
last successful backup is older.

### 7.4 RustFS bucket reachable + writable

Standalone test pod (one-shot, deletes itself):

```bash
kubectl run --rm -it --restart=Never mc-test \
  --image=minio/mc:latest \
  --env="MC_HOST_rustfs=http://${ACCESS_KEY}:${SECRET_KEY}@192.168.10.133:30293" \
  --command -- /bin/sh -c '
    mc ls rustfs/postgres-backups/cnpg/ &&
    mc cp /etc/hostname rustfs/postgres-backups/cnpg/_migration_canary &&
    mc rm rustfs/postgres-backups/cnpg/_migration_canary
'
```

Where `${ACCESS_KEY}` and `${SECRET_KEY}` come from
`kubectl get secret cnpg-s3-credentials -n cloudnative-pg -o jsonpath='{.data.AWS_ACCESS_KEY_ID}' | base64 -d` (and the secret key analog).

### 7.5 No skip-reconcile annotations stuck

(Per § 5.3.)

---

## 8. Rollback per cluster

### 8.1 Git revert

For any cluster that fails post-migration, revert the cluster's commit on
the migration branch:

```bash
git checkout cnpg-plugin-migration
git revert <commit-sha>
git push origin cnpg-plugin-migration
```

User syncs in ArgoCD UI (selfHeal: false → manual sync). ArgoCD removes
the plugin config, restores `spec.backup.barmanObjectStore`. CNPG
performs another rolling restart back to in-tree shape. The
`plugin-barman-cloud` sidecar container is removed from the pod.

### 8.2 What stays on RustFS

All backups taken via the plugin path live in the **same prefix** as the
in-tree path (because we preserve `serverName`). Reverting does not need
to migrate any data. The only risk: if the ObjectStore CR is deleted by
ArgoCD prune, the plugin's view of the bucket is gone but the data
stays — a re-apply restores access.

### 8.3 ScheduledBackup revert

If the Cluster is reverted but the ScheduledBackup still has
`method: plugin`, the next scheduled tick will fail because the plugin is
not loaded on the Cluster. Always revert ScheduledBackup in lockstep with
the Cluster.

### 8.4 ObjectStore CR deletion semantics

`ArgoCD prune: true` is set on the database AppSet. If a revert removes
the ObjectStore from git, ArgoCD will delete it from the cluster. CNPG
plugin should tolerate transient ObjectStore unavailability during
revert, but the WAL archiver may emit errors until the in-tree path is
back. Order of operations during revert: Cluster YAML revert first
(reattach in-tree archiver), THEN allow ObjectStore deletion.

---

## 9. Open questions (require human review)

### 9.1 [BLOCKER] Does `plugins[].parameters.serverName` actually override the default cluster-name serverName?

The official migration doc shows `parameters: { barmanObjectName: ... }`
and uses the cluster's metadata.name as serverName implicitly. Our
clusters have non-default serverNames (e.g., `immich-database-v1`,
`gitea-database-v2`) that MUST be preserved or backup continuity is lost.

The externalClusters example in the migration doc DOES show
`parameters: { barmanObjectName: ..., serverName: ... }`. This implies
the parameter is recognized in the plugin parameters block.

**Action before any migration**: in a non-prod test, deploy a single
test Cluster with `parameters.serverName: <custom-name>` and confirm the
plugin writes WAL/base under that prefix on RustFS. If serverName
override is NOT honored, this entire plan is blocked until upstream adds
support OR we accept rotating each cluster to its default serverName
(which means cutting all four lineages and starting fresh — much higher
risk).

### 9.2 Should we adopt the v3-style 6-field cron syntax in the plugin migration too?

The current ScheduledBackups already use 6-field cron. The plugin's
ScheduledBackup spec is the same CRD (postgresql.cnpg.io/v1
ScheduledBackup), so cron format is unchanged. **Resolved: no change
needed.** Listed here so reviewer doesn't worry.

### 9.3 Does the plugin sidecar count toward the Cluster's resource budget?

The plugin sidecar `plugin-barman-cloud` runs alongside Postgres in the
same pod. CPU/memory limits on the Postgres container don't apply to the
sidecar. Need to verify the plugin chart doesn't request unbounded
resources on small clusters (temporal at 512Mi). If it does, gitea +
temporal pods may hit memory pressure post-migration. Mitigation: file a
follow-up to set explicit sidecar requests via Cluster annotations if
upstream supports it.

### 9.4 Do we need a Backup smoke test before declaring each cluster done?

Recommended: yes, manually trigger `kubectl cnpg backup --plugin
<cluster>-database` immediately after sync to confirm a base backup
completes via the plugin path before the next scheduled tick. Listed in
§ 4 step 4 but flagging here for explicit user agreement.

### 9.5 Should this migration include image bumps?

The four cluster.yaml files use varying Postgres image tags:
- immich: `ghcr.io/tensorchord/cloudnative-vectorchord:17.5-0.4.3` (PG 17)
- gitea/paperless/temporal: `ghcr.io/cloudnative-pg/postgresql:16.2` (PG 16)

**Recommend: NO.** Keep image tags identical to current. Doing a major
version bump simultaneously with a backup-path migration multiplies risk
unnecessarily. Image bumps are a separate PR after this migration is
verified live.

### 9.6 What about the operator chart bump (0.28.0 → latest) tied to plugin compatibility?

CNPG operator 1.29 supports both in-tree and plugin paths. Operator 1.30
removes in-tree. If we plugin-migrate first, then bump operator, the
sequence is safe. If Renovate bumps operator first, in-tree breaks
immediately on all four clusters. **Action: pin operator to 1.29 in
Renovate config until plugin migration is complete on all four clusters,
then unpin.** This is a separate config change (likely
`renovate.json` or `.github/renovate.json`); flag for the conductor to
queue as a precondition.

---

## 10. What this plan does NOT do

- **Does not change** anything in `infrastructure/database/cnpg-barman-plugin/` (already installed and working).
- **Does not change** `infrastructure/database/cloudnative-pg/cloudnative-pg-operator/` (operator pin stays at 1.29).
- **Does not change** `infrastructure/database/cloudnative-pg/postgres-global-secrets/` (the SecretRef stays the same).
- **Does not change** `infrastructure/storage/rustfs-lifecycle/postgres-backups-lifecycle-cm.yaml` (prefix-based lifecycle rules still apply identically).
- **Does not bump** any Postgres image tags.
- **Does not change** the ScheduledBackup cron schedule (still daily 02–05 staggered).
- **Does not migrate** any data. Same bucket, same prefix, same serverName.

---

## 11. Pre-execution checklist (for the human reviewer)

Before greenlighting execution:

- [ ] § 9.1 resolved: `plugins[].parameters.serverName` confirmed working in a test (or accepted as a constraint)
- [ ] Renovate pinned to CNPG operator 1.29.x range until migration done (see § 9.6)
- [ ] Confirm cluster sequencing: temporal first, immich last (or override)
- [ ] Confirm gitea overlay flip-back is a separate PR, lands first
- [ ] Confirm pacing: one cluster per day, watch overnight ScheduledBackup tick
- [ ] Confirm § 9.4: manual backup smoke test required after each migration
- [ ] Confirm rollback path is acceptable: revert YAML + manual ArgoCD sync

When all boxes checked, this branch becomes executable and a soloist can
land the first cluster (temporal) in a separate PR.

---

## Sources

- [CloudNativePG migration doc — Migrating from Built-in CloudNativePG Backup](https://cloudnative-pg.io/plugin-barman-cloud/docs/migration/)
- [Practitioner blog — Migrating my CNPG backups to the Barman Cloud Plugin](https://blog.mei-home.net/posts/cnpg-barman-plugin-migration/)
- [Plugin GitHub — cloudnative-pg/plugin-barman-cloud](https://github.com/cloudnative-pg/plugin-barman-cloud)
- [CNPG main repo — Releases](https://github.com/cloudnative-pg/cloudnative-pg/releases)
- [CNPG appendix — Backup on object stores (deprecation notice)](https://cloudnative-pg.io/docs/devel/appendixes/backup_barmanobjectstore/)
- Reference repo: `/home/vanillax/programming/talos-argocd-proxmox-advanced-starter/apps/postgres-demo/` (postgres-demo target shape)
