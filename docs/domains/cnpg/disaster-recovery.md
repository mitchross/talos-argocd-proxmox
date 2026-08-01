# CloudNativePG Disaster Recovery

> **New to CNPG?** Start with the plain-English, diagram-first
> [Backup/Restore/Start beginner guide](./backup-restore-start-guide.md) — then
> come back here for the full copy-paste runbook.

This doc is the canonical reference for backing up, restoring, and managing
CloudNativePG (CNPG) Postgres clusters in this repository.

## Quick links

- [Concepts](#concepts) — what each piece does
- [Repo layout per DB](#repo-layout-per-db) — overlay pattern
- [Runbook: fresh DB](#runbook-fresh-db-initdb)
- [Runbook: restore from Barman](#runbook-restore-from-barman-recovery)
- [Runbook: cluster nuke rebuild](#runbook-cluster-nuke-rebuild)
- [Monitoring and tools](#monitoring-and-tools)
- [Troubleshooting and gotchas](#troubleshooting-and-gotchas)

## Concepts

CNPG databases live in two layers:

| Layer | What | Backup mechanism | Restore mechanism |
|-------|------|------------------|-------------------|
| **Postgres data** | inside the CNPG `Cluster` CR | Barman Cloud → RustFS S3 | `spec.bootstrap.recovery` + `externalClusters` |
| **App state** | outside (ExternalSecret, ScheduledBackup) | committed to Git as declarative state | ArgoCD sync |

**Barman ≠ PVC backups.** The PVC/Kopia system (the **kopiur** operator, writing
to RustFS S3) handles *file-level* PVC backups. CNPG has its own SQL-aware backup
path: Barman Cloud → RustFS S3. The two never touch each other. See
[docs/disaster-recovery.md](../../disaster-recovery.md) for why both exist.

### How recovery works (the 30-second version)

- Normal operation → `Cluster` has `bootstrap.initdb`, Postgres comes up empty, Barman writes WAL + scheduled base backups to S3.
- DR event → flip the feature flag to `bootstrap.recovery` + specify
  `externalClusters` pointing at a verified data-bearing lineage; CNPG runs
  `barman-cloud-restore` on first boot to pull the selected base backup + replay WAL.

### Why "lineage" (`-v1`, `-v2`, ...)

CNPG requires a **clean WAL archive** for every new cluster. After a recovery,
the new cluster cannot write WAL to the same S3 directory that the previous
cluster wrote to. So every recovery bumps the `serverName` by one:

```
s3://postgres-backups/cnpg/<app>/
├── <app>-database-v1/     ← original / day-0 lineage
│   ├── base/              (full backups)
│   └── wals/              (WAL archive — append-only)
├── <app>-database-v2/     ← prior lineage (restore source)
│   ├── base/
│   └── wals/
└── <app>-database-v3/     ← current write target
    ├── base/
    └── wals/
```

During DR, you restore FROM a verified lineage (e.g., v2) and point new backups
AT a brand-new higher lineage (e.g., v3). Empty or polluted lineages may require
skipping a number. The recovery lineage stays untouched as a PITR source.

## Repo layout per DB

Each database directory has a base + two overlays. The root `kustomization.yaml`
picks the active overlay — **this is the DR feature flag.**

```
infrastructure/database/cloudnative-pg/<db>/
├── kustomization.yaml              ← FEATURE FLAG. Change this one line to switch modes.
├── externalsecret.yaml             ← shared, never edited during DR
├── scheduled-backup.yaml           ← shared, never edited during DR
├── base/
│   ├── kustomization.yaml
│   ├── cluster.yaml                ← NO `spec.bootstrap`; spec.plugins[] serverName = current write target
│   └── objectstore.yaml           ← Barman `ObjectStore` CR (S3 destinationPath, creds, retention)
└── overlays/
    ├── initdb/
    │   ├── kustomization.yaml
    │   └── bootstrap-patch.yaml    ← strategic merge: adds bootstrap.initdb
    └── recovery/
        ├── kustomization.yaml
        └── bootstrap-patch.yaml    ← strategic merge: adds bootstrap.recovery + externalClusters
```

### Root kustomization.yaml — the feature flag

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: cloudnative-pg
labels: [ ... ]   # (was commonLabels — migrated repo-wide 2026-07-09)
resources:
  # Comment one, uncomment the other. That IS the DR switch.
  - overlays/initdb           # ← fresh DB, no restore
  # - overlays/recovery       # ← pull from Barman on first boot
  - externalsecret.yaml
  - scheduled-backup.yaml
```

### `base/cluster.yaml` — everything except bootstrap

The base Cluster manifest contains all immutable spec (image, resources,
storage, monitoring, backup target). Backups are **plugin-based**: `spec.plugins[]`
with `name: barman-cloud.cloudnative-pg.io`, `isWALArchiver: true`, and
`parameters.barmanObjectName` pointing at the sibling `ObjectStore` CR
(`base/objectstore.yaml`), which owns the S3 `destinationPath`, credentials,
and retention. `spec.plugins[0].parameters.serverName` in base is always the
**write target for new backups** — bump this when you bump the lineage. Do not
add an in-tree `spec.backup.barmanObjectStore` field; it does not exist in CNPG
1.30.0+.

### `overlays/initdb/bootstrap-patch.yaml`

Strategic-merge patch adding `spec.bootstrap.initdb` with database, owner,
secret, and any `postInitApplicationSQL` (extensions, grants, initial data).

### `overlays/recovery/bootstrap-patch.yaml`

Adds `spec.bootstrap.recovery` pointing at a named `externalClusters` entry,
which in turn points at the **verified data-bearing lineage** on S3. It can
include `recoveryTarget.backupID` for deterministic base-backup selection or
`targetTime` for point-in-time recovery. **Do not set a targetTime beyond the last archived WAL** — Postgres will FATAL with
"recovery ended before configured recovery target was reached."

---

## Runbook: fresh DB (initdb)

New day-zero app, no data to restore:

1. Edit root `kustomization.yaml` → `overlays/initdb` active.
2. Ensure `base/cluster.yaml` `spec.plugins[0].parameters.serverName` = `<db>-database-v1` (and `parameters.barmanObjectName` references the `<db>-objectstore` CR in `base/objectstore.yaml`).
3. Ensure `overlays/initdb/bootstrap-patch.yaml` has your database name, owner, secret, postInitApplicationSQL.
4. `git add / commit / push`.
5. ArgoCD syncs, CNPG operator creates Cluster with `bootstrap.initdb`, Postgres comes up empty, scheduled backups start writing to `<db>-database-v1/` on S3.

If this is a rebuild of a database whose S3 path already exists, do not reuse
its previous `serverName`. Advance to a clean lineage and move the recovery
overlay to the superseded lineage in the same commit. Otherwise Barman rejects
WAL archiving with `Expected empty archive`.

---

## Runbook: restore from Barman (recovery)

In-place disaster recovery — an existing DB has bad/corrupt data (or is empty
after a cluster nuke) and you want to restore from backups.

**Critical facts:**

- CNPG evaluates `spec.bootstrap` **only at Cluster creation**. To force a
  fresh bootstrap, you MUST delete the live Cluster + its PVCs and let
  ArgoCD re-create it.
- `kubectl delete cluster` does NOT delete PVCs — CNPG leaves them as a
  data-protection measure. You must explicitly delete the PVCs.

### Steps

**1. Bump lineage versions in Git.**

```yaml
# base/cluster.yaml — bump write target to the NEW lineage
spec:
  plugins:
    - name: barman-cloud.cloudnative-pg.io
      isWALArchiver: true
      parameters:
        barmanObjectName: <db>-objectstore     # the prod ObjectStore CR (base/objectstore.yaml)
        serverName: <db>-database-vN           # N = new lineage, e.g. v2 → v3

# overlays/recovery/bootstrap-patch.yaml — point at the verified data lineage
spec:
  bootstrap:
    recovery:
      source: <db>-recovery-source
      database: <db>                 # required — CNPG defaults to "app" otherwise
      owner: <owner>
      secret:
        name: <db>-app-secret
      # Pin this whenever a serverName contains backups from more than one
      # PostgreSQL system ID or a newer backup is known to be empty.
      # recoveryTarget:
      #   backupID: "YYYYMMDDTHHMMSS"
  externalClusters:
    - name: <db>-recovery-source
      plugin:
        name: barman-cloud.cloudnative-pg.io
        parameters:
          # Reuse the SAME prod ObjectStore CR as live backups (same bucket,
          # creds, endpoint — destinationPath/endpointURL/s3Credentials all live
          # on the ObjectStore, NOT inline here). Only serverName differs: it
          # selects the PRIOR lineage subtree to restore from.
          barmanObjectName: <db>-objectstore
          serverName: <db>-database-vM       # M = the verified lineage with good data
```

> The `serverName` here selects the prior backup lineage on the same RustFS
> bucket. **Verify that lineage is still within the S3 recovery window** —
> older lineages age out of RustFS lifecycle retention and become
> unrestorable. All DBs use the `plugin:` shape (no in-tree
> `externalClusters[].barmanObjectStore`).
>
> A `DONE` backup is not proof that it contains the wanted data. A rebuilt
> empty PostgreSQL cluster can successfully write a newer base backup into a
> reused serverName. Compare PostgreSQL system IDs and application row counts;
> pin the last data-bearing `backupID` when the catalog is mixed.

**2. Flip the feature flag.**

```yaml
# root kustomization.yaml
resources:
  # - overlays/initdb
  - overlays/recovery        # ← activate recovery
  - externalsecret.yaml
  - scheduled-backup.yaml
```

**3. Commit and push.**

```bash
git add infrastructure/database/cloudnative-pg/<db>/
git commit -m "dr(<db>): flip to recovery — restore from vN-1, write to vN"
git push
```

**4. Hard-refresh the ArgoCD app FIRST so its manifest cache matches the
new git state.** Without this, ArgoCD may re-create the deleted Cluster
from a stale rendered manifest (pre-recovery-flip) — you'll get a fresh
empty database with `bootstrap.initdb` and `serverName: v(N-1)` despite
git being correct.

```bash
kubectl annotate application database-<db> -n argocd \
  argocd.argoproj.io/refresh=hard --overwrite

# Verify ArgoCD now sees the Cluster as OutOfSync (proves cache picked
# up the new bootstrap.recovery + new serverName)
kubectl get application database-<db> -n argocd \
  -o jsonpath='{.status.resources[?(@.kind=="Cluster")].status}{"\n"}'
# Expect: OutOfSync
```

**5. Delete the live Cluster + PVCs (forces CNPG to re-evaluate bootstrap).**

```bash
kubectl -n cloudnative-pg delete cluster <db>-database
kubectl -n cloudnative-pg delete pvc -l cnpg.io/cluster=<db>-database
# Wait for Longhorn to finish terminating the PVCs (~30–90s)
kubectl -n cloudnative-pg get pvc -l cnpg.io/cluster=<db>-database
```

**6. Trigger ArgoCD sync.**

```bash
kubectl -n argocd patch application database-<db> --type merge \
  -p '{"operation":{"sync":{"revision":"HEAD"}}}'
```

**7. Watch the recovery.**

```bash
kubectl -n cloudnative-pg get cluster <db>-database -w
kubectl -n cloudnative-pg get pods | grep <db>

# Once a <db>-database-1-full-recovery-* pod is Running, tail its logs
kubectl -n cloudnative-pg logs <db>-database-1-full-recovery-xxxxx -f
```

Look for:

- `"restored log file \"...\" from archive"` — WAL being pulled
- `"consistent recovery state reached at ..."` — success signal
- `"recovery ended before configured recovery target was reached"` — FATAL, means your `recoveryTarget.targetTime` is beyond last archived WAL. Remove the target or pick an earlier one.

**8. Verify data.**

```bash
kubectl exec -n cloudnative-pg <db>-database-1 -c postgres -- \
  psql -U postgres -d <db> -c "\dt"   # should show restored tables
```

**9. Reconcile the consumer app** so it picks up the fresh DB connection.

```bash
kubectl -n <db> rollout restart deployment/<app>
```

Temporal is different: schema creation is an Argo Sync hook, not server startup
logic. After a **database-only** recreation, explicitly sync
`my-apps-temporal`; a Deployment restart does not execute the hook:

```bash
argocd app sync my-apps-temporal
```

**10. Flip back to initdb.** Once the Cluster is running with verified data,
`spec.bootstrap` is a no-op on that existing Cluster. Restore
`overlays/initdb` as the steady-state declaration so an accidental future PVC
loss cannot silently replay this now-stale recovery plan.

---

## Runbook: cluster nuke rebuild

Entire K8s cluster is being rebuilt, ArgoCD is bootstrapping fresh, and CNPG
databases need to come back:

- If Barman S3 still has usable backups → set root `kustomization.yaml` to
  `overlays/recovery` **before ArgoCD first-syncs** the DB. The AppSet will
  create each Cluster with `bootstrap.recovery` on initial creation — no
  delete/recreate dance needed.
- If Barman S3 is empty or unreliable → use `overlays/initdb` only when an
  intentionally empty database is acceptable. Do not assume an app will
  recreate data merely because it can recreate tables.

Before deleting the cluster, verify all four parts for every database:

1. The recovery source serverName contains the intended data-bearing backup.
2. `recoveryTarget.backupID` selects it when the catalog contains a newer empty
   backup or multiple PostgreSQL system IDs.
3. The base manifest writes to a brand-new serverName with an empty S3 prefix.
4. The root kustomization already renders `bootstrap.recovery`.

After Argo bootstrap installs Waves 0–4, run the prepared transaction. Its
default mode is read-only preflight; mutation requires the explicit flag:

```bash
./scripts/bootstrap-cnpg-recovery.sh
./scripts/bootstrap-cnpg-recovery.sh --execute
```

Neither the Argo CD nor CloudNativePG project publishes a joint recovery guide
that prescribes this manual boundary. It is a repository-specific safety
decision based on the two controllers' documented behavior and the acceptance
evidence required after the July 29 empty-`initdb` incident; it must not be
presented as an upstream best practice.

[Argo CD 3.4 treats `automated.enabled: false` as an explicit
pause](https://argo-cd.readthedocs.io/en/release-3.4/user-guide/auto_sync/),
while disabling only self-heal does not prevent a Git-triggered auto-sync.
Argo CD does have a direct CNPG integration: its
[built-in CNPG health check](https://github.com/argoproj/argo-cd/blob/release-3.4/resource_customizations/postgresql.cnpg.io/Cluster/health.lua)
maps `Setting up primary` to `Progressing` and `Cluster in healthy state` to
`Healthy`, and it ships
[CNPG resource actions](https://argo-cd.readthedocs.io/en/release-3.4/operator-manual/resource_actions_builtin/).
That integration can prove controller-level readiness, but not the restored
PostgreSQL system identifier, application rows, or a completed backup in the
new lineage. ApplicationSet RollingSync could order database and consumer
Applications using that health result, but it remains Beta and cannot perform
those data-level acceptance checks. The script retains the manual boundary so
the consumer is released only after all of those checks pass.

[CloudNativePG recovery bootstraps a new Cluster rather than restoring
in-place](https://cloudnative-pg.io/documentation/current/recovery/); its
guidance also supports exact `backupID` selection and distinct recovery/read
and forward-write `serverName` values. Those are CNPG recovery requirements,
not a CNPG recommendation about Argo CD sync policy.

### Prepared recovery for the 2026-07-31 rebuild

The pre-nuke audit queried each Barman catalog directly and compared it with
the live application tables. The July 31 v7/v7/v9 backups are valid backups of
empty replacement databases and are intentionally not restore sources.

| Database | Read lineage | Pinned backup | Backup completed (UTC) | New write lineage |
|---|---|---|---|---|
| Immich | `immich-database-v6` | `20260728T020000` | 2026-07-28 02:00:18 | `immich-database-v8` |
| Paperless | `paperless-database-v6` | `20260728T050000` | 2026-07-28 05:00:10 | `paperless-database-v8` |
| Temporal | `temporal-database-v8` | `20260728T030000` | 2026-07-28 03:02:57 | `temporal-database-v10` |

Paperless v6 also contains a successful 2026-07-30 backup from the empty
replacement PostgreSQL system ID. Removing its `backupID` pin will restore the
wrong database.

**Post-bootstrap acceptance.** Auto-sync is disabled for all three database
Applications and their three consumers. The script hard-refreshes and syncs
each database, verifies the pinned manifest and PostgreSQL system identifier,
requires a non-empty application table plus `ContinuousArchiving` and
the exact recovery-only `Backup` in `completed` phase (plus
`LastBackupSucceeded`), then syncs the consumer. That event-specific Backup is
part of the recovery overlay and is pruned when the root returns to `initdb`.
The equivalent data checks are:

```bash
kubectl exec -n cloudnative-pg immich-database-1 -c postgres -- \
  psql -U postgres -d immich -c 'select count(*) from asset;'
kubectl exec -n cloudnative-pg paperless-database-1 -c postgres -- \
  psql -U postgres -d paperless -c 'select count(*) from documents_document;'
kubectl exec -n cloudnative-pg temporal-database-1 -c postgres -- \
  psql -U postgres -d temporal -c 'select count(*) from executions;'
```

The first `my-apps-temporal` sync runs the schema hook and namespace seed. If
Temporal's database is ever recreated without also recreating its Application,
sync `my-apps-temporal` explicitly before judging the UI; syncing
`database-temporal` only reconciles PostgreSQL.

---

## Monitoring and tools

**Use these first:**

- **ArgoCD UI** (http://localhost:39681 or https://argocd.vanillax.me)
  Shows sync/health status per DB app. Good for "is this DB's git in sync with cluster?"
- **Grafana** (https://grafana.vanillax.me) via kube-prometheus-stack
  The CNPG Helm chart ships with Grafana dashboards — check for panels under
  "CloudNativePG" folder. Covers backup timing, WAL archiving, Cluster state.
  If missing, import from https://github.com/cloudnative-pg/grafana-dashboards.
- **K8sGPT** (in `monitoring/k8sgpt/`) — detects CNPG Cluster anomalies and
  surfaces them in its dashboard.
- **Headlamp** (https://headlamp.vanillax.me) — generic K8s UI, can view CNPG
  Cluster CRDs, pods, events. Good for "why is this DB stuck?"
- **`kubectl cnpg plugin`** (install locally):
  ```bash
  curl -sSfL https://github.com/cloudnative-pg/cloudnative-pg/raw/main/hack/install-cnpg-plugin.sh | sudo sh
  kubectl cnpg status <cluster> -n cloudnative-pg
  ```
  Shows replication lag, backup timing, WAL position, recovery progress — all
  in a colored terminal view. **This is the single best CLI tool for CNPG health.**

**State visibility quick-check (copy-paste this script):**

```bash
for db in gitea immich paperless temporal; do
  echo "--- $db ---"
  kubectl -n cloudnative-pg get cluster "$db-database" \
    -o jsonpath='  mode={.spec.bootstrap.*}{"\n"}  serverName={.spec.plugins[0].parameters.serverName}{"\n"}  ready={.status.readyInstances}/{.spec.instances}{"\n"}  phase={.status.phase}{"\n"}'
  echo
done
```

---

## Future improvements (ideas to come back to)

Optional tooling to build when DR becomes a routine drill (quarterly) or painful
enough that the tools are worth it. Rough-ordered by effort-vs-payoff.

### Tier 1 — quick wins (do first when you have 30 min)

- **Import the official CNPG Grafana dashboards.** Upstream publishes
  ready-made JSON at https://github.com/cloudnative-pg/grafana-dashboards.
  Drop into `monitoring/prometheus-stack/` as ConfigMaps with the Grafana
  sidecar label so they auto-import. Covers: backup age per cluster, WAL
  archiving lag, connection count, checkpoint stats. One-time commit, forever-on
  visibility.

- **Install the `kubectl cnpg` plugin locally.** Single best tool for CNPG
  state. Pin this as a prerequisite in onboarding.

- **Committed state-check script** in `scripts/` that prints a summary table
  of all CNPG DBs: current serverName, last successful backup, last WAL
  archive age, Cluster phase. Expands the inline script above into a
  standalone tool with nicer formatting. ~30 lines of bash.

### Tier 2 — DR wizard CLI (weekend project, ~1-2 days)

A thin local CLI (`scripts/dr-wizard`) that turns the full DR runbook into
guided steps. Minimum viable feature set:

- `dr-wizard status` — reads git + live state, prints "here's each DB's
  current lineage, mode flag, backup age."
- `dr-wizard plan <db>` — dry-run: available lineages on S3, proposed
  serverName changes, the diff, ready to open a PR.
- `dr-wizard execute <db>` — after PR merged, performs the destructive
  kubectl delete cluster + PVC + sync step with y/N confirmations.
- `dr-wizard validate <db>` — post-recovery, runs SQL sanity check (counts
  rows in a few tables, reports vs. previously-known counts).

Worth it IF DR becomes routine: collapses a 30-minute copy-paste dance into ~3
commands with built-in guardrails (WAL range check, lineage math, consumer-app
restart). Not worth building for a once-a-year use case.

**Scope creep to avoid:** don't build a web UI. CLI + GitHub PR checkout is
already a UI. Just make the CLI nice.

### Tier 3 — proper state-management UI (only if scale grows)

If the cluster grows to 10+ CNPG DBs, revisit with a real web interface:

- **Adopt an existing tool first.** Check whether CNPG has an upstream
  dashboard project by the time this matters. If yes, use that.
- **Custom web UI (last resort).** Only build if nothing upstream exists
  AND DR is happening monthly+. A Next.js dashboard reading the Cluster
  CRDs, showing backup lineage timelines per DB, offering the same wizard
  actions the CLI has. Huge maintenance tax.

### Explicitly NOT worth building

- **General-purpose Postgres management GUI** (pgAdmin, Adminer, DBeaver
  server, etc.). They operate at the SQL layer, not the CNPG Cluster
  lifecycle you care about during DR. Install locally as a client tool if
  useful for ad-hoc queries — but they add zero value for DR.
- **Lua / Helm-hook automation** around the delete-cluster-PVC step. The
  manual `kubectl` sequence is already 2 commands and explicitly destructive;
  hiding it behind automation just makes "oops I meant the other DB" blastier.
- **Automated PITR-target guessing** (e.g. "restore to yesterday 23:59").
  Always specify targets explicitly or omit them entirely. Guesswork here
  produces the "recovery ended before target" FATAL.

---

## Troubleshooting and gotchas

### "recovery ended before configured recovery target was reached"

Your `recoveryTarget.targetTime` is AFTER the last archived WAL on S3.
Remove the target (restore to latest-WAL-available) OR pick an earlier
timestamp. Symptom: `full-recovery` pods CrashLoopBackOff with this FATAL in
the Postgres log.

### `barman-cloud-check-wal-archive`: `Expected empty archive`

The new forward write lineage is already dirty. Do not reuse that
`serverName`, and do not delete random RustFS objects unless you have already
identified the exact abandoned prefix. The safe recovery is:

1. Keep the recovery source pointed at the last known-good lineage.
2. Bump `base/cluster.yaml` `spec.plugins[0].parameters.serverName` to the next
   clean forward lineage.
3. Hard-refresh Argo before deleting the Cluster/PVCs.
4. Delete the live Cluster, recovery Jobs, and CNPG PVCs.
5. Let Argo recreate the Cluster from the current render.

### "relation does not exist" after a successful recovery

The restored DB is empty (or has a subset of data). Common causes:
- Barman base backup was taken BEFORE the app had populated its tables.
- WAL archive had a gap (archiving was broken for some period). Check with:
  ```bash
  kubectl exec -n cloudnative-pg <db>-database-1 -c postgres -- \
    psql -U postgres -c "SELECT count(*) FROM pg_tables WHERE schemaname='public';"
  ```
- Recovery ran, but the consumer app hasn't been restarted — its migration
  logic hasn't touched the new DB. Reconcile the app. For Temporal, sync
  `my-apps-temporal`; a rollout restart cannot run its schema hook.

### New Cluster comes up with `bootstrap.initdb` despite git saying `recovery`

ArgoCD's `ignoreDifferences` on `.spec.bootstrap` + `RespectIgnoreDifferences=true`
**strips** the bootstrap field during apply. The database AppSet must NOT have
`.spec.bootstrap` in its `jqPathExpressions` — verify
`infrastructure/controllers/argocd/apps/appsets/database-appset.yaml`. If it
does, ArgoCD is silently dropping your recovery config.

### Sync "Succeeded" but Cluster doesn't appear

The DB's ArgoCD Application may carry a `argocd.argoproj.io/skip-reconcile: "true"`
annotation. ArgoCD reports sync success but never actually reconciles. Fix:

```bash
kubectl -n argocd annotate application database-<db> \
  argocd.argoproj.io/skip-reconcile- --overwrite
```

### PVCs stuck in Terminating

Longhorn cleanup sometimes takes >60s when many volumes delete concurrently.
If they stay Terminating >5 min:

```bash
# Check Longhorn volumes
kubectl -n longhorn-system get volumes.longhorn.io | grep <cluster-name>

# If the Longhorn volume is detached but PVC is stuck, it's a K8s finalizer —
# last resort, remove finalizer manually:
kubectl -n cloudnative-pg patch pvc <pvc-name> --type=merge -p '{"metadata":{"finalizers":[]}}'
```

### ExternalSecret says Synced but the actual Secret is missing

The ExternalSecret status lags when the Secret was deleted externally.
Force a re-sync:

```bash
kubectl -n cloudnative-pg annotate externalsecret <name> \
  force-sync="$(date +%s)" --overwrite
```

If the ES itself has a stuck deletion finalizer:

```bash
kubectl -n cloudnative-pg patch externalsecret <name> \
  --type=merge -p '{"metadata":{"finalizers":[]}}'
```

### Polluted S3 lineage after a failed DR attempt

If post-DR scheduled backups wrote empty base backups to the wrong
`serverName`, the cleanest fix is:

1. Leave the known-good recovery source alone.
2. Bump `base/cluster.yaml` `spec.plugins[0].parameters.serverName` to the next
   clean forward lineage.
3. Let the next scheduled backup populate the clean prefix.

Only wipe an abandoned RustFS prefix after confirming no live Cluster points at
it as a write target or recovery source.

---

## Deprecation / forward migration

### `spec.monitoring.enablePodMonitor` deprecated

Used by all DBs. A future CNPG release removes it. Migration: replace with a
manually-managed `PodMonitor` resource per cluster. Not urgent, but note the
warning in CNPG logs.
