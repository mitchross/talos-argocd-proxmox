# pvc-plumber migration cleanup — RESUME HERE

**Status: PAUSED 2026-05-21 mid-cleanup. Operator decommissioned, per-app cutover ~1/28 done.**

This doc is the single source of truth for resuming. Read it top to bottom before touching anything. Don't re-do the audit; it already happened.

---

## Procedural guardrail while this is paused

Until the cleanup is resumed and completed, **do not**:

- Touch any PVC manifest under `my-apps/` (no edits, no `kubectl edit`, nothing that triggers a PVC re-create)
- Manually delete any PVC, ReplicationSource, or ReplicationDestination
- Delete or recreate ArgoCD Applications for any backup-labeled app
- Trigger an ArgoCD app-level "Refresh + Replace" or "Hard refresh + Sync with Replace=true" on any of the 27 unmigrated apps

Why: 27 PVCs in git still carry the `backup:` label without a static `dataSourceRef`. They run on orphan pvc-plumber-rendered RS/RD/ES objects (still in cluster, cached creds, working). The pvc-plumber mutating webhook is **gone**, so if any of those PVCs is recreated, no `dataSourceRef` gets injected and the new PVC silently binds empty — no restore from S3.

Backups continue firing on schedule via VolSync controller as long as no one touches the PVCs.

**Cluster API access is fine** (kubectl get/describe, ArgoCD UI reads, logs, port-forwards). Only the destructive write operations above are off-limits.

---

## §1 FAIL summary verbatim (the audit that triggered this pause)

### Critical (load-bearing)

1. **Chart not graduated.** Lives at `docs/research/pvc-backup-simplification/proposal/volsync-backup/`, NOT `infrastructure/storage/volsync-backup/`. This is the root cause of §2.a's `--load-restrictor LoadRestrictionsNone` workaround.

2. **Only karakeep got the chart migration. All other 27 PVCs are still configured for the old pvc-plumber pattern** — they have `backup:` labels, no `dataSourceRef`, no `restore-policy` labels. Their existing pvc-plumber-rendered RS/RD/ES objects still exist as orphans in the cluster, still running backups against the cached-cred secrets, but the apps' git manifests haven't been touched.

3. **`docs/research/.../proposal/`** still present without archival marker.

### Real issues

4. **`my-apps/home/n8n/workflows/daily-cluster-report.json`** has a hardcoded `http://pvc-plumber.volsync-system.svc.cluster.local/readyz` — that healthcheck is broken now. Workflow will error.

5. **Root `CLAUDE.md`** still instructs adding `backup:` label for pvc-plumber auto-backup. Stale.

6. **`infrastructure/CLAUDE.md`** has debug commands using `kubectl logs -l app.kubernetes.io/name=pvc-plumber`. Stale.

7. **Stale "dynamically by Kyverno" comments in 11 PVC files** (nginx, open-webui, home-assistant, paperless-ngx ×2, copyparty, n8n, fizzy, homepage-dashboard, immich, jellyfin).

8. **`my-apps/ai/perplexica/pvc.yaml`** has stale "pvc-plumber/Kyverno injects" comment.

### False positives (verified safe — do NOT re-flag)

- `my-apps/development/posthog/externalsecret.yaml` references `pvc-plumber-access-key` — that's the 1Password workload-credential property name per `docs/rustfs-credential-runbook.md`. Correct.
- `infrastructure/database/redis/redis-instance/pvc.yaml` has `backup:` label — Redis, not CNPG postgres, no Barman. Backup label is valid.
- Comment-only refs in `keda-app.yaml`, `volsync-backup-cluster-app.yaml`, karakeep's kustomization + pvc-data.yaml — historical context, fine.

---

## §2–§12 preview matrix verbatim

| § | Anticipated |
|---|---|
| 2.a | FAIL (`LoadRestrictionsNone` present in argocd values.yaml — added today as workaround) |
| 2.b | FAIL (karakeep's helmCharts path points at `docs/research/`) |
| 2.c | FAIL (proposal/ has no archival marker) |
| 2.d | FAIL (~29 `-backup`-suffixed RS/RD orphans in cluster) |
| 2.e | likely OK |
| 2.f | likely OK |
| 2.g | likely FAIL (busybox image not in Renovate scope) |
| 2.h | likely OK |
| 2.i | FAIL (`.claude/commands/add-backup.md` not updated) |
| 2.j | OK |
| 2.k | OK (in mink note already) |
| 3 | partial FAIL (orphan kyverno RSes; only 1/28 PVCs chart-managed) |
| 4 | partial PASS (T7a verified, but only on a few mover Jobs) |
| 5 | NOT RUN (T7b skipped) |
| 6 | NOT RUN (R5 SQLite burn skipped) |
| 7 | NOT RUN |
| 8 | FAIL (docs unwritten) |
| 9 | OK — verified during pause: MAP manifest uses `apiVersion: admissionregistration.k8s.io/v1`, no MAP-related patches in `omni/` |
| 10 | NOT RUN |
| 11 | PARTIAL (some mink notes saved, more needed — see below) |
| 12 | (sign-off questions) |

---

## What's already done (do NOT redo)

### Runtime + git, both clean

- pvc-plumber Deployment + RBAC + SA + Application + MutatingWebhookConfiguration + ValidatingWebhookConfigurations: **deleted from cluster**
- `infrastructure/controllers/pvc-plumber/` directory + `core-dependencies/pvc-plumber-app.yaml`: **removed from git** (commits 4484e2c3 + d0d92b20)
- `volsync-backup-cluster` Application: deployed, Synced + Healthy; MutatingAdmissionPolicy + Binding live (`apiVersion: admissionregistration.k8s.io/v1`)
- T7a passed: MAP injects `wait-for-rustfs` init container into mover Jobs; backup against `homepage-dashboard/config` completed Successful

### Karakeep partial migration

- Two `helmCharts:` entries added to `my-apps/media/karakeep/kustomization.yaml` (data-pvc + meilisearch-pvc)
- Chart-rendered RS/RD/ES exist in `karakeep` namespace (`data-pvc`, `data-pvc-dst`, `volsync-data-pvc`, etc.)
- Old pvc-plumber-rendered objects manually deleted
- **karakeep `my-apps-karakeep` Application is currently OutOfSync** because ArgoCD wants to change `data-pvc.spec.dataSource` (immutable). The PVC's `dataSource` was set by pvc-plumber's mutating webhook at PVC creation time to `data-pvc-backup`; chart wants `data-pvc-dst`. **Resolution path: leave the existing PVC alone (the `dataSource` field doesn't matter while PVC is Bound); ArgoCD's ComparisonError on this immutable field is cosmetic. Add `ignoreDifferences` for `.spec.dataSource` on karakeep's Application, or just suppress the error.**

### Cluster prep tuning

- `monitoring/loki-stack/values.yaml`: retention 30d→24h + `compactor: { retention_enabled: true, retention_delete_delay: 2h, compaction_interval: 10m, delete_request_store: s3 }` (committed to main)
- `infrastructure/storage/volsync/kopia-maintenance-cronjob.yaml`: schedule `37 3 * * *` → `37 */6 * * *` (committed to main)
- Loki bucket wiped at filesystem level on TrueNAS host (165k objects → 465). Filesystem path: `/mnt/BigTank/k8s/rustfs/loki/{1,index,self-monitoring}` deleted (keep `loki_cluster_seed.json`)
- kopia maintenance ran successfully from TrueNAS shell (manual one-off)
- `loki-write` StatefulSet currently 3/3 Running but config may still be old retention if ArgoCD hasn't re-rendered — verify on resume

### Talos / MAP

- MAP feature gate is GA on K8s 1.34+ (cluster is 1.36) — no Talos patch needed, no `omni/` change
- `infrastructure/storage/volsync-backup-cluster/talos-patch.yaml` retained as historical documentation only (not in kustomization.yaml resources)

---

## 27 apps to migrate

Inventory captured 2026-05-21 from `my-apps/`. Karakeep's two PVCs already chart-managed (commit 4484e2c3) but need `restore-policy:` label added.

| # | File | PVC | NS | Freq | Capacity | StorageClass | dataSourceRef | restore-policy | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `my-apps/ai/perplexica/pvc.yaml` | perplexica-data | perplexica | daily | 10Gi | longhorn | no | no | stale Kyverno comment |
| 2 | `my-apps/ai/open-webui/pvc.yaml` | storage | open-webui | daily | 10Gi | longhorn | no | no | stale Kyverno comment |
| 3 | `my-apps/development/gitea/values.yaml` | (helm-rendered) | gitea | daily | helm | helm | no | no | **Helm chart values — not a raw PVC manifest. Backup label is on a value passed to gitea Helm chart. Different migration path: chart-managed-via-chart-values, may need different handling than other 27.** |
| 4 | `my-apps/development/posthog/data-layer/postgres.yaml` | postgres-data | posthog | daily | 20Gi | longhorn | no | no | NOT CNPG — standalone posthog postgres |
| 5 | `my-apps/development/posthog/data-layer/redis.yaml` | redis7-data | posthog | daily | 10Gi | longhorn | no | no |  |
| 6 | `my-apps/development/posthog/data-layer/kafka.yaml` | redpanda-data-kafka-0 | posthog | daily | 20Gi | longhorn | no | no | Kafka/redpanda — be careful with restore semantics |
| 7 | `my-apps/ai/swarmui/pvc.yaml` | swarmui-data | swarmui | daily | 5Gi | longhorn | no | no |  |
| 8 | `my-apps/development/nginx/pvc.yaml` | storage | nginx | daily | 5Gi | longhorn | no | no | low-stakes test app — good T7b candidate |
| 9 | `my-apps/home/frigate/pvc.yaml` | frigate-config | frigate | daily | 10Gi | longhorn | no | no |  |
| 10 | `my-apps/home/home-assistant/pvc.yaml` | config | home-assistant | hourly | 10Gi | longhorn | no | no | SQLite-bearing — good R5 burn-test candidate |
| 11 | `my-apps/home/project-nomad/flatnotes/pvc.yaml` | flatnotes-data | project-nomad | daily | 5Gi | longhorn | no | no |  |
| 12 | `my-apps/home/paperless-ngx/pvc.yaml` (data) | data | paperless-ngx | hourly | 10Gi | longhorn | no | no | also has `media` PVC, both labeled — multi-PVC kustomization entry |
| 13 | `my-apps/home/paperless-ngx/pvc.yaml` (media) | media | paperless-ngx | hourly | (check file) | longhorn | no | no | sibling of #12 |
| 14 | `my-apps/home/project-nomad/mysql/pvc.yaml` | mysql-data | project-nomad | daily | 20Gi | longhorn | no | no | SQL — careful with restore consistency |
| 15 | `my-apps/home/project-nomad/kolibri/pvc.yaml` | kolibri-data | project-nomad | daily | 20Gi | longhorn | no | no |  |
| 16 | `my-apps/home/project-nomad/qdrant/pvc.yaml` | qdrant-data | project-nomad | daily | 20Gi | longhorn | no | no | vector DB |
| 17 | `my-apps/home/project-nomad/nomad/pvc.yaml` | nomad-storage | project-nomad | daily | **120Gi** | longhorn | no | no | LARGE — first run will take a while |
| 18 | `my-apps/media/copyparty/config-pvc.yaml` | config | copyparty | daily | 5Gi | longhorn | no | no |  |
| 19 | `my-apps/media/copyparty/data-pvc.yaml` | copyparty-data | copyparty | daily | 20Gi | longhorn | no | no |  |
| 20 | `my-apps/media/copyparty/media-pvc.yaml` | copyparty-media | copyparty | daily | 10Gi | longhorn | no | no |  |
| 21 | `my-apps/home/n8n/pvc.yaml` | data | n8n | hourly | 10Gi | longhorn | no | no | also clean up the broken `pvc-plumber.volsync-system.svc.cluster.local/readyz` URL in `my-apps/home/n8n/workflows/daily-cluster-report.json` |
| 22 | `my-apps/utility/fizzy/pvc.yaml` | data | fizzy | daily | 10Gi | longhorn | no | no |  |
| 23 | `my-apps/media/homepage-dashboard/pvc.yaml` | config | homepage-dashboard | daily | 5Gi | longhorn | no | no | already used as T7a smoke-test target — backup proven |
| 24 | `my-apps/home/project-zomboid/pvc.yaml` | zomboid-data | project-zomboid | daily | 20Gi | longhorn | no | no | also has unlabeled `zomboid-server-files` PVC — don't add labels to that |
| 25 | `my-apps/media/jellyfin/pvc.yaml` | config | jellyfin | daily | 5Gi | longhorn | no | no |  |
| 26 | `my-apps/media/immich/library-pvc.yaml` | library | immich | daily | **300Gi** | longhorn | no | no | LARGEST. First chart-managed backup will be heavy on RustFS |
| 27 | `my-apps/media/tubesync/storage.yaml` | config-pvc | tubesync | daily | 10Gi | longhorn | no | no |  |

**Already partially migrated (need restore-policy label added):**

- `my-apps/media/karakeep/karakeep/pvc-data.yaml` — data-pvc, hourly, 10Gi, has dataSourceRef ✓, missing restore-policy
- `my-apps/media/karakeep/meilisearch/pvc-meilisearch.yaml` — meilisearch-pvc, hourly, 10Gi, has dataSourceRef ✓, missing restore-policy

Total: 27 fresh migrations + 2 karakeep label fixes = 29 file edits across ~25 directories.

---

## The 8-step sequence (with the 4.5 verification gate inserted)

1. **Graduate the chart.** `git mv docs/research/pvc-backup-simplification/proposal/volsync-backup infrastructure/storage/volsync-backup`. Unblocks step 3.

2. **Update karakeep's `helmGlobals.chartHome`** in `my-apps/media/karakeep/kustomization.yaml` to point at the graduated location (relative path from karakeep ns to `infrastructure/storage/`). Re-render with `kustomize build --enable-helm` and confirm chart inflates correctly.

3. **Revert the `LoadRestrictionsNone` workaround** in `infrastructure/controllers/argocd/values.yaml`. The line to revert: keep only `kustomize.buildOptions: "--enable-helm"`. The commit that introduced it: **`c0e0e2eb feat(argocd): kustomize --load-restrictor LoadRestrictionsNone for shared chart`**. Restart `argocd-repo-server` so the cm change is re-read. Then re-render karakeep — should succeed without the security workaround because the chart is now under the kustomization tree.

4. **Migrate the 27 remaining apps** — for each:
   - Edit the app's `kustomization.yaml`: add `helmGlobals.chartHome` (pointed at `infrastructure/storage/`) + a `helmCharts:` entry per backup-labeled PVC. Use `pvc_create: false`. Set `moverSecurityContext` to match the app's pod UID/GID (NOT the pvc-plumber-rendered 568 default — check each app's deployment spec).
   - Edit each backup-labeled PVC manifest: remove the `backup: "hourly"` (or daily) label OR move it to chart-only signal; add `restore-policy:` label; add static `dataSourceRef:` block pointing at `ReplicationDestination/<pvc>-dst`.
   - Remove the stale "dynamically by Kyverno" comment.
   - Special cases:
     - **gitea (#3)** — Helm-rendered PVC, may need to consume the chart via Helm values rather than a raw manifest edit. Investigate before bulk-applying.
     - **paperless-ngx (#12+13)** — two backup-labeled PVCs in one file, both need separate chart entries.
     - **copyparty (#18+19+20)** — three backup-labeled PVCs across three files, all in one kustomization.
     - **n8n (#21)** — also fix the broken pvc-plumber URL in the n8n workflow JSON.
     - **immich (#26)** — 300Gi, first run will be slow.
     - **project-nomad/nomad (#17)** — 120Gi, similar.

**4.5. VERIFICATION GATE (do not skip).** After editing the 27 apps but before any cluster cleanup:

   - Pick 3 representative apps spanning the diversity: **one SQLite-bearing** (e.g. home-assistant or jellyfin), **one large-data** (immich library or project-nomad/nomad), **one small-config** (homepage-dashboard or nginx).
   - Run `kustomize build --enable-helm <app-dir>` locally for each. Confirm: PVC manifest has both `dataSourceRef` and `restore-policy` label; rendered ES has the right `pvc-plumber-access-key`/`pvc-plumber-secret-key` 1P refs; rendered RS has `repository: volsync-<pvc>` (continuity); rendered RD name is `<pvc>-dst`; mover security context matches the app's pod UID.
   - Commit these 3 first; push; watch ArgoCD reconcile each. If anything errors loudly, **fix the bulk pattern before applying to the other 24**. If they reconcile clean, proceed to commit the remaining 24.
   - **STOP and report after this step** so the user can confirm before proceeding to destructive cleanup.

5. **Cleanup stale "dynamically by Kyverno/pvc-plumber" comments** in 11 PVC files (now covered by per-app edits in step 4).

6. **Cluster cleanup — destructive, requires explicit go-ahead.** Delete the orphan pvc-plumber-era + Kyverno-era objects:
   ```bash
   # Orphan -backup-suffixed RS/RD/ES — only after all 27 apps migrated
   kubectl delete replicationsource.volsync.backube -A -l 'app.kubernetes.io/managed-by=pvc-plumber'
   kubectl delete replicationsource.volsync.backube -A -l 'app.kubernetes.io/managed-by=kyverno'
   kubectl delete replicationdestination.volsync.backube -A -l 'app.kubernetes.io/managed-by=pvc-plumber'
   kubectl delete replicationdestination.volsync.backube -A -l 'app.kubernetes.io/managed-by=kyverno'
   # Old volsync-<pvc> ESes that the operator created (chart will own them now — same name, different content)
   kubectl get externalsecret -A -l app.kubernetes.io/managed-by=pvc-plumber
   # Review the list, then delete carefully — ArgoCD's next sync recreates the chart's version
   ```
   **STOP and report after this step** for explicit user go-ahead.

7. **T7b in production** — pick one low-stakes app (nginx is ideal, or homepage-dashboard) and run the live fail-closed test from `docs/research/pvc-backup-simplification/test-plan.md` §T7b: apply scoped CiliumNetworkPolicy egressDeny against RustFS for that ns; trigger manual backup; confirm pod stuck in `wait-for-rustfs` init; remove CNP; confirm mover proceeds.

8. **R5 SQLite burn test** — on home-assistant or jellyfin (both have embedded SQLite): record a known piece of state via the app's UI, delete the PVC, watch chart's populator restore from kopia, verify state intact.

Then move to §8 doc rewrites: `docs/volsync-storage-recovery.md`, root + nested `CLAUDE.md` backup sections, `.claude/commands/add-backup.md`, archive `docs/pvc-plumber-*.md`.

---

## Resumption prompt for the new session

```
Continue the pvc-plumber migration cleanup. Full context in
docs/research/pvc-backup-simplification/CLEANUP-IN-PROGRESS.md — read it
first. The audit already happened; the work is mechanical execution of
the 8-step sequence in that doc. Stop and report after step 4.5
(verification of bulk-migration pattern on 3 apps), step 6 (cluster
orphan cleanup — destructive, needs explicit go), and step 7 (T7b in
prod). Do not skip the verification gates.
```

---

## Key commit SHAs for resumption

| Purpose | SHA | Title |
|---|---|---|
| Revert in step 3 | `c0e0e2eb` | feat(argocd): kustomize --load-restrictor LoadRestrictionsNone for shared chart |
| Karakeep partial migration | `4484e2c3` | feat(karakeep): migrate to chart-managed VolSync backups + ArgoCD LoadRestrictionsNone |
| pvc-plumber operator decommission | `d0d92b20` | feat!: decommission pvc-plumber operator — Track B Phase 4 |
| Loki retention + kopia 6h schedule | `caf11e72` | fix: reduce sustained S3 load on RustFS |
| MAP at sync wave 2 | `0daaa56e` / `8b8141d6` | feat(volsync-backup-cluster): land MAP via ArgoCD at sync wave 2 / merge |
| Current main HEAD | `c0e0e2eb` | (verify with `git rev-parse origin/main` on resume) |
