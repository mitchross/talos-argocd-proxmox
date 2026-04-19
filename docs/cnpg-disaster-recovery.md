# CloudNativePG Disaster Recovery

This doc is the canonical reference for backing up, restoring, and managing
CloudNativePG (CNPG) Postgres clusters in this repository.

## Quick links

- [Concepts](#concepts) — what each piece does
- [Repo layout per DB](#repo-layout-per-db) — overlay pattern
- [Runbook: fresh DB](#runbook-fresh-db-initdb)
- [Runbook: restore from Barman](#runbook-restore-from-barman-recovery)
- [Runbook: cluster nuke rebuild](#runbook-cluster-nuke-rebuild)
- [Monitoring & tools](#monitoring--tools)
- [Troubleshooting / gotchas](#troubleshooting--gotchas)

## Concepts

CNPG databases live in two layers:

| Layer | What | Backup mechanism | Restore mechanism |
|-------|------|------------------|-------------------|
| **Postgres data** | inside the CNPG `Cluster` CR | Barman Cloud → RustFS S3 | `spec.bootstrap.recovery` + `externalClusters` |
| **App state** | outside (ExternalSecret, ScheduledBackup) | committed to Git as declarative state | ArgoCD sync |

**Barman ≠ PVC backups.** The PVC/Kopia system (Kyverno + VolSync + pvc-plumber)
handles *file-level* PVC backups to NFS. CNPG has its own SQL-aware backup
path: Barman Cloud → RustFS S3. The two never touch each other. See
[docs/backup-restore.md](backup-restore.md) for why both exist.

### How recovery works (the 30-second version)

- Normal operation → `Cluster` has `bootstrap.initdb`, Postgres comes up empty, Barman writes WAL + scheduled base backups to S3.
- DR event → flip the feature flag to `bootstrap.recovery` + specify `externalClusters` pointing at the prior backup lineage, CNPG runs `barman-cloud-restore` on first boot to pull base backup + replay WAL.

### Why "lineage" (`-v1`, `-v2`, ...)

CNPG requires a **clean WAL archive** for every new cluster. After a recovery,
the new cluster cannot write WAL to the same S3 directory that the previous
cluster wrote to. So every recovery bumps the `serverName` by one:

```
s3://postgres-backups/cnpg/<app>/
├── <app>-database-v1/     ← original / day-0 lineage
│   ├── base/              (full backups)
│   └── wals/              (WAL archive — append-only)
├── <app>-database-v2/     ← lineage created after first DR
│   ├── base/
│   └── wals/
└── <app>-database-v3/     ← current write target (after second DR)
    ├── base/
    └── wals/
```

During DR, you restore FROM one lineage (e.g., v2) and point new backups AT
the next (v3). The prior lineage stays untouched as a PITR source for future
DR events.

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
│   └── cluster.yaml                ← NO `spec.bootstrap`; serverName = current write target
└── overlays/
    ├── initdb/
    │   ├── kustomization.yaml
    │   └── bootstrap-patch.yaml    ← strategic merge: adds bootstrap.initdb
    └── overlays/recovery/
        ├── kustomization.yaml
        └── bootstrap-patch.yaml    ← strategic merge: adds bootstrap.recovery + externalClusters
```

### Root kustomization.yaml — the feature flag

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: cloudnative-pg
commonLabels: { ... }
resources:
  # Comment one, uncomment the other. That IS the DR switch.
  - overlays/initdb           # ← fresh DB, no restore
  # - overlays/recovery       # ← pull from Barman on first boot
  - externalsecret.yaml
  - scheduled-backup.yaml
```

### `base/cluster.yaml` — everything except bootstrap

The base Cluster manifest contains all immutable spec (image, resources,
storage, monitoring, backup target). `backup.barmanObjectStore.serverName` in
base is always the **write target for new backups** — bump this when you bump
the lineage.

### `overlays/initdb/bootstrap-patch.yaml`

Strategic-merge patch adding `spec.bootstrap.initdb` with database, owner,
secret, and any `postInitApplicationSQL` (extensions, grants, initial data).

### `overlays/recovery/bootstrap-patch.yaml`

Adds `spec.bootstrap.recovery` pointing at a named `externalClusters` entry,
which in turn points at the **prior lineage** on S3. Optionally includes
`recoveryTarget.targetTime` for point-in-time recovery. **Do not set a
targetTime beyond the last archived WAL** — Postgres will FATAL with
"recovery ended before configured recovery target was reached."

---

## Runbook: fresh DB (initdb)

New day-zero app, no data to restore:

1. Edit root `kustomization.yaml` → `overlays/initdb` active.
2. Ensure `base/cluster.yaml` `backup.barmanObjectStore.serverName` = `<db>-database-v1`.
3. Ensure `overlays/initdb/bootstrap-patch.yaml` has your database name, owner, secret, postInitApplicationSQL.
4. `git add / commit / push`.
5. ArgoCD syncs, CNPG operator creates Cluster with `bootstrap.initdb`, Postgres comes up empty, scheduled backups start writing to `<db>-database-v1/` on S3.

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
backup:
  barmanObjectStore:
    serverName: <db>-database-vN     # N = new lineage, e.g. v2 → v3

# overlays/recovery/bootstrap-patch.yaml — point externalClusters at the PRIOR lineage
spec:
  bootstrap:
    recovery:
      source: <db>-recovery-source
      database: <db>                 # required — CNPG defaults to "app" otherwise
      owner: <owner>
      secret:
        name: <db>-app-secret
      # Optional PITR — ONLY if you know WAL exists at that timestamp
      # recoveryTarget:
      #   targetTime: "2026-04-17T23:59:59Z"
  externalClusters:
    - name: <db>-recovery-source
      barmanObjectStore:
        serverName: <db>-database-v(N-1)   # N-1 = the lineage with good data
        destinationPath: s3://postgres-backups/cnpg/<db>
        endpointURL: http://192.168.10.133:30293
        s3Credentials: { ... same as backup ... }
        wal: { compression: gzip }
```

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

**4. Delete the live Cluster + PVCs (forces CNPG to re-evaluate bootstrap).**

```bash
kubectl -n cloudnative-pg delete cluster <db>-database
kubectl -n cloudnative-pg delete pvc -l cnpg.io/cluster=<db>-database
# Wait for Longhorn to finish terminating the PVCs (~30–90s)
kubectl -n cloudnative-pg get pvc -l cnpg.io/cluster=<db>-database
```

**5. Trigger ArgoCD sync.**

```bash
kubectl -n argocd patch application <db> --type merge \
  -p '{"operation":{"sync":{"revision":"HEAD"}}}'
```

**6. Watch the recovery.**

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

**7. Verify data.**

```bash
kubectl exec -n cloudnative-pg <db>-database-1 -c postgres -- \
  psql -U postgres -d <db> -c "\dt"   # should show restored tables
```

**8. Restart the consumer app** so it picks up the fresh DB connection.

```bash
kubectl -n <db> rollout restart deployment/<app>
```

**9. (Optional) Flip back to initdb.** Once the Cluster exists and is running
with the recovered data, `spec.bootstrap` is a no-op — CNPG ignores it on
existing Clusters. You can leave the overlay on `recovery` forever, or flip
the root `kustomization.yaml` back to `overlays/initdb` for a tidier "steady
state" git declaration. Both are valid.

---

## Runbook: cluster nuke rebuild

Entire K8s cluster was rebuilt, ArgoCD bootstrapping fresh, CNPG DBs need to
come back:

- If Barman S3 still has usable backups → set root `kustomization.yaml` to
  `overlays/recovery` **before ArgoCD first-syncs** the DB. The AppSet will
  create each Cluster with `bootstrap.recovery` on initial creation — no
  delete/recreate dance needed.
- If Barman S3 is empty or unreliable → use `overlays/initdb` and rebuild
  the DB fresh. Apps will re-migrate their schemas on first connect.

**Post-bootstrap app rollout.** After DBs come up, the apps that talk to
them may still be pointing at stale connections and need a rolling restart:

```bash
for ns in gitea immich paperless-ngx temporal; do
  kubectl -n "$ns" get deploy --no-headers | awk '{print $1}' | \
    xargs -I {} kubectl -n "$ns" rollout restart deployment/{}
done
```

---

## Monitoring & tools

**Currently deployed (use these first):**

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
    -o jsonpath='  mode={.spec.bootstrap.*}{"\n"}  serverName={.spec.backup.barmanObjectStore.serverName}{"\n"}  ready={.status.readyInstances}/{.spec.instances}{"\n"}  phase={.status.phase}{"\n"}'
  echo
done
```

---

## Future improvements (ideas to come back to)

Unfinished work — revisit when DR becomes a routine drill (quarterly) or when
this is painful enough the tools are worth building. Rough-ordered by
effort-vs-payoff.

### Tier 1 — quick wins (do first when you have 30 min)

- **Import the official CNPG Grafana dashboards.** Upstream publishes
  ready-made JSON at https://github.com/cloudnative-pg/grafana-dashboards.
  Drop into `monitoring/prometheus-stack/` as ConfigMaps with the Grafana
  sidecar label so they auto-import. Covers: backup age per cluster, WAL
  archiving lag, connection count, checkpoint stats. One-time commit, forever-on
  visibility.

- **Install the `kubectl cnpg` plugin locally.** Single best tool for CNPG
  state. Already referenced above — pin this as prerequisite in onboarding.

- **Committed state-check script** in `scripts/` that prints a summary table
  of all CNPG DBs: current serverName, last successful backup, last WAL
  archive age, Cluster phase. Just expands the inline script above into a
  standalone tool with nicer formatting. ~30 lines of bash.

### Tier 2 — DR wizard CLI (weekend project, ~1-2 days)

A thin local CLI (`scripts/dr-wizard`) that turns the full DR runbook into
guided steps. Minimum viable feature set:

- `dr-wizard status` — reads git + live state, prints "here's each DB's
  current lineage, mode flag, backup age."
- `dr-wizard plan <db>` — dry-run: "you want to restore `<db>`. Available
  lineages on S3: v1 (WAL ends 2026-04-16). Proposed changes: base.serverName
  v1 → v2; recovery overlay serverName → v1. Here's the diff, ready to open
  a PR?"
- `dr-wizard execute <db>` — after PR merged, performs the destructive
  kubectl delete cluster + PVC + sync step with y/N confirmations.
- `dr-wizard validate <db>` — post-recovery, runs SQL sanity check (counts
  rows in a few tables, reports vs. previously-known counts).

Why it's worth it IF DR becomes routine: collapses a 30-minute copy-paste
dance into ~3 commands with built-in guardrails (WAL range check, lineage
math, consumer-app restart). Not worth building for a once-a-year use case.

**Scope creep to avoid:** don't try to build a web UI. CLI + GitHub PR
checkout is already a UI. Just make the CLI nice.

### Tier 3 — proper state-management UI (only if scale grows)

If the cluster grows to 10+ CNPG DBs, revisit with a real web interface:

- **Adopt an existing tool first.** Check if CNPG has an upstream dashboard
  project by the time this matters (they had hints of one in 2025). If yes,
  use that.
- **Custom web UI (last resort).** Only build if nothing upstream exists
  AND DR is happening monthly+. A Next.js dashboard reading the Cluster
  CRDs, showing backup lineage timelines per DB, offering the same wizard
  actions the CLI has. Weekend project × several. Huge maintenance tax.

### Tier 4 — backup-plugin migration (mandatory before CNPG 1.30.0)

Separate deprecation work, not a DR feature — tracked here for visibility.

CNPG is removing native `spec.backup.barmanObjectStore` in 1.30.0. We
already have the Barman Cloud Plugin installed at
`infrastructure/database/cnpg-barman-plugin/` but no DB uses it yet. Before
upgrading CNPG past 1.29:

1. Each DB's `base/cluster.yaml` moves from `spec.backup.barmanObjectStore`
   to `spec.plugins[]` referencing an `ObjectStore` CR.
2. Same for `overlays/recovery/bootstrap-patch.yaml` `externalClusters`.
3. Each DB gets an `ObjectStore` CR (shared ones OK — bucket + creds are
   the same).
4. Test migration on one DB first (e.g. paperless), verify backups continue
   flowing, migrate the rest.

Budget: probably 1 evening per DB. Schedule when CNPG 1.30.0 is announced
(watch https://cloudnative-pg.io/releases/).

### Explicitly NOT worth building

- **General-purpose Postgres management GUI** (pgAdmin, Adminer, DBeaver
  server, etc.). They operate at the SQL layer, not the CNPG Cluster
  lifecycle you actually care about during DR. Install locally as a client
  tool if useful for ad-hoc queries — but they add zero value for DR.
- **Lua / Helm-hook automation** around the delete-cluster-PVC step. The
  manual `kubectl` sequence is already 2 commands and explicitly destructive;
  hiding it behind automation just makes "oops I meant the other DB"
  blastier.
- **Automated PITR-target guessing** (e.g. "restore to yesterday 23:59").
  Always specify targets explicitly or omit them entirely. Guesswork here
  produces the same "recovery ended before target" FATAL we hit on 2026-04-19.

---

## Troubleshooting / gotchas

### "recovery ended before configured recovery target was reached"

Your `recoveryTarget.targetTime` is AFTER the last archived WAL on S3.
Remove the target (restore to latest-WAL-available) OR pick an earlier
timestamp. Symptom: `full-recovery` pods CrashLoopBackOff with this FATAL in
the Postgres log.

### "relation does not exist" after a successful recovery

The restored DB is empty (or has a subset of data). Common causes:
- Barman base backup was taken BEFORE the app had populated its tables.
- WAL archive had a gap (archiving was broken for some period). Check with:
  ```bash
  kubectl exec -n cloudnative-pg <db>-database-1 -c postgres -- \
    psql -U postgres -c "SELECT count(*) FROM pg_tables WHERE schemaname='public';"
  ```
- Recovery ran, but the consumer app hasn't been restarted — its migration
  logic hasn't touched the new DB. Rolling-restart the app.

### New Cluster comes up with `bootstrap.initdb` despite git saying `recovery`

ArgoCD's `ignoreDifferences` on `.spec.bootstrap` + `RespectIgnoreDifferences=true`
will **strip** the bootstrap field during apply. We removed that from the
database AppSet (commit 61d4aef0) — verify `infrastructure/controllers/argocd/apps/database-appset.yaml`
does NOT have `.spec.bootstrap` in its `jqPathExpressions`. If it does, ArgoCD
is silently dropping your recovery config.

### Sync "Succeeded" but Cluster doesn't appear

The DB's ArgoCD Application may have a stuck `argocd.argoproj.io/skip-reconcile: "true"`
annotation (left over from old scripts). ArgoCD reports sync success but never
actually reconciles. Fix:

```bash
kubectl -n argocd annotate application <db> \
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

If post-DR scheduled backups wrote EMPTY base backups to the wrong `serverName`
(happened in our session), the cleanest fix is:

1. Wipe the polluted `serverName` directory on RustFS (`postgres-backups/cnpg/<db>/<serverName>/`).
2. Bump `base/cluster.yaml` `backup.barmanObjectStore.serverName` to the next
   lineage (e.g. `-v4`).
3. Let the next scheduled backup populate cleanly.

---

## Deprecation / forward migration

### Native `spec.backup.barmanObjectStore` will be removed in CNPG 1.30.0

We currently use the native (in-Cluster) Barman config. The upstream
replacement is the **Barman Cloud Plugin** (`infrastructure/database/cnpg-barman-plugin/`,
already installed as `cnpg-barman-plugin-app.yaml`). Migration is required
before CNPG 1.30.0.

Migration plan: each DB's `base/cluster.yaml` moves from
`spec.backup.barmanObjectStore` to a `spec.plugins[]` entry that references
an `ObjectStore` CR. Same for `overlays/recovery/bootstrap-patch.yaml`'s
`externalClusters`. Not urgent — track CNPG release notes for the 1.29 → 1.30
cutover.

### `spec.monitoring.enablePodMonitor` deprecated

Currently used by all DBs. CNPG 1.30.0 will remove it. Migration: replace with
a manually-managed `PodMonitor` resource per cluster. Also not urgent but note
the warning in CNPG logs.
