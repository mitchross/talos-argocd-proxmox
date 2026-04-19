# Database Guidelines (CNPG CloudNativePG)

> **Required reading before performing DR or modifying database backups:**
> - [`docs/cnpg-disaster-recovery.md`](../../docs/cnpg-disaster-recovery.md) — canonical DR runbook, overlay pattern, troubleshooting

Databases use **CloudNativePG** with Barman backups to RustFS S3 — a **separate backup path** from the PVC/VolSync system.

- **PVC backups**: Kopia on NFS via VolSync (automated by Kyverno)
- **Database backups**: Barman to S3 (SQL-aware base backup + WAL archiving for PITR)

See [`docs/backup-restore.md`](../../docs/backup-restore.md#why-two-backup-systems-nfs-for-pvcs-s3-for-databases) for why both exist.

## Repo layout per DB

Each CNPG DB uses a Kustomize **overlay pattern** where the active bootstrap
mode is a one-line feature flag in git.

```
infrastructure/database/cloudnative-pg/<db>/
├── kustomization.yaml              ← FEATURE FLAG — picks one overlay
├── externalsecret.yaml             ← 1Password-backed app credentials
├── scheduled-backup.yaml           ← daily Barman ScheduledBackup
├── base/
│   ├── kustomization.yaml
│   └── cluster.yaml                ← no bootstrap; serverName = current write target
└── overlays/
    ├── initdb/
    │   ├── kustomization.yaml
    │   └── bootstrap-patch.yaml    ← merge-patch adds bootstrap.initdb
    └── recovery/
        ├── kustomization.yaml
        └── bootstrap-patch.yaml    ← merge-patch adds bootstrap.recovery + externalClusters
```

The root `kustomization.yaml`:

```yaml
resources:
  - overlays/initdb           # ← normal operation (fresh DB or already-running)
  # - overlays/recovery       # ← flip here for disaster recovery
  - externalsecret.yaml
  - scheduled-backup.yaml
```

**Why overlays instead of editing `cluster.yaml` in place:**
- `bootstrap.initdb` and `bootstrap.recovery` are mutually exclusive at the
  CRD level. Keeping only ONE active in the rendered manifest avoids the
  CNPG webhook rejection.
- Feature flag (one commented line) is a clean git diff. Easy to review.
- No need for `cnpg.io/validation: disabled` annotation.

## Current lineage per DB

The `serverName` values below live in each DB's `base/cluster.yaml` and
`overlays/recovery/bootstrap-patch.yaml` — bump both when you recover.

| Database  | Current write target (base)  | Prior lineage (recovery source) |
|-----------|------------------------------|---------------------------------|
| gitea     | `gitea-database-v1`          | `gitea-database-v1`             |
| immich    | `immich-database-v1`         | `immich-database-v1`            |
| paperless | `paperless-database-v1`      | `paperless-database-v1`         |
| temporal  | `temporal-database-v1`       | `temporal-database-v1`          |

All DBs reset to `-v1` baseline on 2026-04-19 after S3 was wiped — prior
lineages (`-v2` through `-v7`) no longer exist on RustFS. Next DR event bumps
to `-v2`.

## Normal operation (add a new CNPG DB)

1. Copy an existing DB directory (e.g. `gitea/`) to `<newapp>/`.
2. Update names, owner, image, postInitApplicationSQL, resource sizes in `base/cluster.yaml` and `overlays/initdb/bootstrap-patch.yaml`.
3. Set `base/cluster.yaml` `backup.barmanObjectStore.serverName` to `<newapp>-database-v1`.
4. Set `overlays/recovery/bootstrap-patch.yaml` to reference `<newapp>-database-v1` as the prior lineage (placeholder until a real DR event bumps both).
5. Commit + push. Database AppSet auto-discovers `infrastructure/database/*/*` — no appset edits needed.

## Disaster recovery (bump lineage + flip to recovery)

See the full runbook in [`docs/cnpg-disaster-recovery.md`](../../docs/cnpg-disaster-recovery.md#runbook-restore-from-barman-recovery). Short version:

1. Bump `base/cluster.yaml` `serverName` to next `-vN`.
2. Set `overlays/recovery/bootstrap-patch.yaml` `externalClusters.serverName` to the now-prior `-v(N-1)`.
3. Flip root `kustomization.yaml` → `overlays/recovery`.
4. Commit, push.
5. Delete live Cluster + PVCs so CNPG re-evaluates bootstrap on fresh creation:
   ```bash
   kubectl -n cloudnative-pg delete cluster <db>-database
   kubectl -n cloudnative-pg delete pvc -l cnpg.io/cluster=<db>-database
   ```
6. Trigger ArgoCD sync on the `<db>` application.
7. Watch `*-full-recovery-*` pod logs for Barman base + WAL replay.

## Critical rules (from prior incidents)

- **Never set `recoveryTarget.targetTime` beyond the last archived WAL.**
  Postgres FATALs with "recovery ended before configured recovery target was reached." If uncertain, omit the target entirely to restore to latest-WAL.
- **Always delete PVCs after deleting the Cluster.** CNPG leaves them as
  data protection. Stale PVCs cause the new Cluster to hang "Setting up primary" forever.
- **Keep `.spec.bootstrap` and `.spec.externalClusters` OUT of the database
  AppSet's `ignoreDifferences`.** `RespectIgnoreDifferences=true` + SSA will
  silently strip those fields during apply, producing a Cluster with no
  bootstrap → CNPG defaults to initdb → empty DB despite git saying recovery.
- **Rolling-restart consumer apps after a DB rebuild.** Pods connected to the
  old DB won't re-run their migrations against the new empty one until restarted.
- **Specify `database` + `owner` + `secret` in recovery bootstrap.** CNPG
  defaults to `database: app, owner: app` if omitted.
- **Don't add CNPG PVCs to Kyverno backup labels.** They use Barman, not Kopia.

## Deprecation warnings

- **Native `spec.backup.barmanObjectStore`** — will be removed in CNPG 1.30.0.
  Migrate to the Barman Cloud Plugin (already installed at
  `infrastructure/database/cnpg-barman-plugin/`). Not urgent; track release notes.
- **`spec.monitoring.enablePodMonitor`** — deprecated, replace with manually-
  managed `PodMonitor` resources per cluster.

## Monitoring

Use `kubectl cnpg status <cluster>` CLI plugin for best single-view health.
See [`docs/cnpg-disaster-recovery.md` § Monitoring & Tools](../../docs/cnpg-disaster-recovery.md#monitoring--tools) for Grafana dashboards, Headlamp, K8sGPT, and a copy-paste state-check script.
