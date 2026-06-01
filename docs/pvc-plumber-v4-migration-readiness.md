# pvc-plumber v4 — Fleet Migration Readiness

> Generated 2026-05-29 from a read-only fleet review (live cluster + Git) after the
> nginx-example/storage canary completed under rc7. **Two PVCs are now operator-managed**
> (`nginx-example/storage`, `homepage-dashboard/config`); the rest of this doc is the
> tracking/planning matrix for the remaining fleet. Migrating any production PVC requires
> **explicit per-PVC authorization** — no migration happens automatically from this doc.

## 1. Current system status

| Item | State |
|---|---|
| Operator image | `ghcr.io/mitchross/pvc-plumber:4.0.1@sha256:721d770330a535871cae33313d7cd336116697d2a6f9e5d91fc8cd3d21a26305` |
| Release | **v4.0.1** (commit `da40246`) — adds the namespace software write-gate (`pvc-plumber.io/managed-namespace: "true"`) + single cluster-wide `ClusterRoleBinding pvc-plumber:volsync-writer` (replaces per-ns RoleBindings, `a1916d61`). Supersedes v4.0.0. |
| Mode | **permissive** (writes_allowed=true), pod Ready, restartCount 0 |
| Shipped fixes (rc6→rc7, now in v4.0.1) | RS/RD watch + child→PVC reverse-map + periodic self-heal requeue + partial-inline-argo guard + `/audit` staleness. Closes the rc6 reconcile-trigger gap (the 2026-05-28 15h backup gap). |
| Watch proof | Synthetic `pvc-plumber-watch-smoke`: managed RS *and* RD deleted → recreated in <5s, no PVC poke. |
| nginx-example/storage canary | **Functionally complete.** Inline Argo RS/RD removed from Git (`50a84cc9`), Argo pruned them, rc7 recreated `RS/storage` + `RD/storage-dst` as `managed-by=pvc-plumber`, and the operator-managed RS produced a **Successful** initial backup (`lastSyncTime=2026-05-29T04:04:29Z`, kopia EXIT_CODE 0). `/audit`: `already-matches` / `managed-by-pvc-plumber` / `stale=false`. |
| nginx canary caveat | The first **cron-driven** recurrence (`nextSyncTime=2026-05-30T02:58:00Z`) is an optional, read-only follow-up — the create-time initial sync already proved the mechanism. |
| homepage-dashboard/config migration | **Complete (2026-05-29).** Commit 1 RBAC RoleBinding `df0d47a4`; Commit 2 handoff `48d342f8` (single-file: added v4 fuse + `ServerSideApply=false`, removed inline RS/RD). Argo pruned the inline `argocd`-owned RS/RD; rc7's RS/RD watch recreated `RS/config` + `RD/config-dst` as `managed-by=pvc-plumber` in <20s. Schedule rewritten `9 2 * * *` → `36 2 * * *` (deterministic). Initial backup **Successful**: `lastSyncTime=2026-05-29T18:42:44Z`, `latestMoverStatus.result=Successful`, `nextSyncTime=2026-05-30T02:36:00Z`. PVC UID unchanged (`078aff64-…`), Bound, `dataSourceRef=config-dst`. `/audit`: `label_source=v4` / `already-matches` / `managed-by-pvc-plumber` / `stale=false`. |
| karakeep migration (Gate 3) | **Complete (2026-05-30).** Both PVCs handed off in one commit (`93b2b5cb`): RBAC pre-existed (`df0d47a4`); added v4 fuse `tier=hourly` + `ServerSideApply=false`, removed inline RS/RD. Operator recreated all four (`RS/data-pvc`+`RD/data-pvc-dst`, `RS/meilisearch-pvc`+`RD/meilisearch-pvc-dst`) as `managed-by=pvc-plumber`. **Hourly cadence preserved** via `tier=hourly` (deterministic `data-pvc 10 * * * *`, `meilisearch 0 * * * *`). **Mover UID 1001→568 normalization proven safe** — both initial backups **Successful** (`meilisearch-pvc 2026-05-30T03:26:12Z`, `data-pvc 2026-05-30T03:27:20Z`) reading the 1001-owned data via snapshot-clone fsGroup. PVC UIDs unchanged (`data-pvc 90070779-…`, `meilisearch-pvc 24bdda38-…`). `/audit`: both `already-matches`/`managed-by-pvc-plumber`/`v4`/`stale=false`. Preceded by the data-pvc immutable-dsr repair (Option R). |
| karakeep cleanup TODO | Old retained PV **`pvc-4cb90a74-e7df-4fc3-a967-1ab8603ffdd4`** (`Released`/`Retain`, the pre-repair data-pvc volume) **must NOT be deleted until explicitly approved** — it is the data-pvc repair rollback net. |
| tubesync migration | **Complete (2026-05-30).** Handoff `5ed1e67b`, `tier=daily`. Second Option-R repair (immutable `config-pvc-backup`→`config-pvc-dst`); hardened the corrected Argo-unlock sequence + stale-cache learnings (see §3). Operator RS backup **Successful** (`lastSync=17:24:19Z`, `nextSync=2026-05-31T02:05:00Z`, `5 2 * * *`), RD `latestImage=…20260530172156`, both `managed-by=pvc-plumber`. New PVC UID `ce76e0b9…`; old PV `pvc-3f4378d9-…` was `Released`/`Retain` (rollback) but is **no longer present as of the 2026-05-31 fleet audit** — reclaimed/removed before the audit, not by it; tubesync is healthy and its live `config-pvc` operator-backed-up. |
| reset-batch (7 PVCs) | **Complete (2026-05-30).** Handoff `61044bf4`. Aggressive Option-R reset of all remaining low-risk drifted app PVCs in waves (quiesced backup per app → delete → recreate from quiesced snapshot → handoff): `copyparty/copyparty-data`, `jellyfin/config`, `open-webui/storage`, `perplexica/perplexica-data`, `project-zomboid/zomboid-data`, `swarmui/{swarmui-data,swarmui-output}` — all `tier=daily`, data restored, operator RS/RD `managed-by=pvc-plumber`, `/audit` `already-matches`/`v4`/`stale=false`. Old PVs retained (Retain/Released). **As of the 2026-05-31 fleet audit, still present (4):** `pvc-a157ad5f` (copyparty), `pvc-be2c62e1` (open-webui), `pvc-d71b929e` (zomboid), `pvc-47c2ae80` (swarmui-data). **No longer present (3 — reclaimed/removed before the audit, not by it; apps healthy + live PVCs operator-backed-up):** `pvc-045a3e7b` (jellyfin), `pvc-18d3d2c7` (perplexica), `pvc-3dc7b545` (swarmui-output). Only copyparty needed temp dsr alignment (it had a recent Git dsr change → manifest-generate-paths stale-render race on recreate; the other 6 had Git dsr always `-dst` → clean recreate). |
| n8n canary migration | **Complete (2026-05-31).** Handoff `ce634e66`, `tier=hourly`. First SAVE_FOR_END migration. Option-R reset (empty→`data-dst` dsr; recreated from quiesced snapshot). New PVC UID `213408c5…` (old `1608bca4…`); old PV `pvc-1608bca4-…` was `Retain`/`Released` (rollback) but is **no longer present as of the 2026-05-31 fleet audit** — reclaimed/removed before the audit, not by it; n8n is healthy and its live `data` operator-backed-up. Operator RS/RD `managed-by=pvc-plumber`, hourly `27 * * * *`, first operator backup **Successful** (`2026-05-31T07:19:38Z`, next `07:27`). **Mover UID normalized 1000→568 (explicitly approved) and validated** — the 568 mover backed up the 1000-owned data; kopia preserves uid/gid so restored data stays `node:node`/1000. Live dsr=`data-dst`. `/audit`: `already-matches`/`v4`/`stale=false`. |
| home-assistant migration | **Complete (2026-05-31).** SAVE_FOR_END Class C. Handoff `5f9d3988`, `tier=hourly`, mover 568 (already). Case-A dsr repair (dangling `config-backup`→`config-dst`); recreated from quiesced snapshot (new PVC `4a27e9db…`, old PV `pvc-52fd99ba…` retained). **Caveat:** the high-write recorder DB `home-assistant_v2.db` was corrupt on restore → HA quarantined it (`.corrupt.*`) + started fresh recorder; config/integrations/automations/.storage restored intact, sensor history lost. First migration **paused** mid-run by a cluster Longhorn outage (GPU node down) and resumed after recovery. |
| gitea migration | **Complete (2026-05-31).** SAVE_FOR_END Class C, **Helm `extraDeploy` special case**. Handoff `c1129533`, `tier=daily`. RS/RD lived in `values.yaml extraDeploy`; PVC is chart-generated with dsr/labels injected via `kustomization.yaml` JSONPatch. Case-A dsr repair (dangling `gitea-shared-storage-backup`→`-dst`); recreated from quiesced snapshot (new PVC `c4760d30…`, old PV `pvc-5f52c07b…` retained); **5 repos restored**. **Mover normalized 1000→568 (validated)** — 568 mover backed up 1000-owned rootless-gitea data; first operator backup Successful. **DB stayed native** (external CNPG `gitea-database`, untouched). |
| final disposable-reset batch (paperless ×2 + immich) | **Complete (2026-05-31).** Handoff `49b97920`, aggressive **empty-reset** (user-authorized disposable nuke; NO quiesced backup, NO restore — recreated EMPTY with NO `dataSourceRef`). `paperless-ngx/data` (uid→`d2d1340e`, tier=hourly `18 * * * *`), `paperless-ngx/media` (uid→`befbcfc8`, tier=hourly), `immich/library` (uid→`ba6ca359`, tier=daily `23 2 * * *`); all mover 568. All three first operator backups **Successful** (immich next `2026-06-01T02:23Z`). Apps healthy on empty PVCs: paperless 1/1, immich-server 1/1, immich-machine-learning 1/1. **immich required:** scaling BOTH `immich-server` and `immich-machine-learning` to 0 (ML also mounts library RWO) to release the PVC, flipping `immich-server` RollingUpdate→Recreate, and an `init-library-markers` initContainer that recreates the `.immich` folder-check markers (thumbs/upload/backups/library/profile/encoded-video) — without them immich-server crashloops on an empty library against the intact CNPG DB. **Caveat:** immich's CNPG DB still references the now-empty library → broken/missing assets in UI (accepted, disposable). No `dataSourceRef` by design → drift-free, but no auto-restore on future recreate. Old PVs reclaim=Delete (no rollback PV kept — empty reset). **UPDATE 2026-05-31: `paperless-ngx/data` later had `dataSourceRef → data-dst` ADDED (`b7052c30`) and its forward backup→restore chain validated by drill — see §8 row. `paperless-ngx/media` and `immich/library` still have NO dsr (no auto-restore) until similarly drilled.** |
| **Managed namespaces** (`pvc-plumber.io/managed-namespace=true`; RBAC via cluster-wide CRB) | `nginx-example`, `homepage-dashboard`, `karakeep`, `fizzy`, `frigate`, `project-nomad`, `tubesync`, `copyparty`, `jellyfin`, `open-webui`, `perplexica`, `project-zomboid`, `swarmui`, `n8n`, `home-assistant`, `gitea`, `paperless-ngx`, `immich` (18) |
| **Operator-managed PVCs** (`managed-by=pvc-plumber` RS/RD) | nginx-example/storage, homepage-dashboard/config, karakeep/{data-pvc,meilisearch-pvc}, fizzy/data, frigate/frigate-config, project-nomad/{flatnotes-data,qdrant-data,nomad-storage,mysql-data}, tubesync/config-pvc, copyparty/copyparty-data, jellyfin/config, open-webui/storage, perplexica/perplexica-data, project-zomboid/zomboid-data, swarmui/{swarmui-data,swarmui-output}, n8n/data, home-assistant/config, gitea/gitea-shared-storage, paperless-ngx/{data,media}, immich/library (**24**) |
| **Retained rollback PVs — present** (verified 2026-05-31 fleet audit; `Released`/`Retain`; do not delete until approved) | karakeep/data-pvc `pvc-4cb90a74`, home-assistant/config `pvc-52fd99ba`, gitea/gitea-shared-storage `pvc-5f52c07b`, swarmui/swarmui-data `pvc-47c2ae80`, copyparty/copyparty-data `pvc-a157ad5f`, open-webui/storage `pvc-be2c62e1`, project-zomboid/zomboid-data `pvc-d71b929e` (**7**) |
| **Retained rollback PVs — gone** (documented earlier, no longer present at the 2026-05-31 audit; **reclaimed/removed before the audit, not by it**; all apps healthy + live PVCs operator-backed-up) | tubesync `pvc-3f4378d9`, n8n `pvc-1608bca4`, jellyfin `pvc-045a3e7b`, perplexica `pvc-18d3d2c7`, swarmui-output `pvc-3dc7b545` (**5**) |

### Known caveats / fleet-wide gaps
- **RBAC is NOT a per-namespace gate (corrected 2026-05-31).** v4.0.1 uses a single **cluster-wide `ClusterRoleBinding pvc-plumber:volsync-writer`** (SA `pvc-plumber/pvc-plumber`, RS/RD verbs) that already covers every namespace. There are **no per-namespace `RoleBinding`s and none are needed** — verify `kubectl get clusterrolebinding pvc-plumber:volsync-writer`. The 13 migrated namespaces (incl. the 7-app reset batch) were all migrated with no per-ns RoleBinding step. The real per-namespace prerequisite is the **software write-gate** (`pvc-plumber.io/managed-namespace: "true"` on the namespace + fuse labels on the PVC); without it the operator emits `skipped-namespace-not-managed` / `skipped-not-opted-in`.
- All 18–19 candidate namespaces already have `volsync.backube/privileged-movers: "true"` and a materialized `volsync-kopia-repository` Secret. Those two prerequisites are met fleet-wide.
- No candidate PVC carries the v4 fuse labels yet — migration requires **adding** `pvc-plumber.io/enabled=true` + `manage-volsync=true` + `tier` to the PVC.
- Only **`n8n`** is currently in Argo `ComparisonError` (immutable-dataSourceRef SSA wedge). Other apps with live `dataSourceRef` drift (e.g. copyparty) are still `Synced/Healthy` because the my-apps AppSet `ignoreDifferences` masks the PVC dataSource fields. **For a drift PVC that is merely going to be migrated (RS/RD handoff, PVC stays Bound), `ServerSideApply=false` is NOT needed and not recommended** — the bound PVC's spec is immutable, so any apply to it (incl. SSA=false) re-validates and can throw an isolated SyncError. The fuse-label handoff (labels + remove inline RS/RD) syncs fine because Argo only *applies* the labels/annotations, never the immutable `dataSourceRef`. SSA=false is only relevant when you must force ArgoCD to *apply a changed PVC field*, which the drift PVCs do not require until/unless their `dataSourceRef` is wrong (see Option-R below).
- **Cadence is set by `tier`, not forced to daily.** v4 rewrites each RS schedule to a deterministic per-PVC minute **within the chosen tier's window** (`tier=hourly` → `MM * * * *`, `tier=daily` → `MM 2 * * *`, etc.). Karakeep ×2 migrated at **`tier=hourly`** and kept their hourly cadence (proven: `data-pvc 10 * * * *`, `meilisearch 0 * * * *`). The remaining hourly apps (home-assistant, n8n, paperless-ngx ×2) should likewise use `tier=hourly` to preserve cadence — only a wrong tier choice (hourly→daily) would reduce frequency.
- **mover UID change — proven safe.** v4 normalizes `moverSecurityContext` to `568/568/568`. Karakeep ×2 (inline `1001`) migrated and **backed up successfully** as 568 — the snapshot-clone `fsGroup` makes the 1001-owned data group-readable to the 568 mover. Remaining non-568 inline movers (n8n `1000`, gitea `1000`) get the same ownership change; the Karakeep result indicates this is low-risk, but still confirm the first backup succeeds per app.

## 2. PVC readiness table

**24 PVCs are now operator-managed** (see §1; paperless ×2 + immich/library are the latest — final disposable-reset batch, 2026-05-31). The low-risk file/SQLite cohort is fully migrated. What remains is the **SAVE_FOR_END tier** — databases, high-value app state, and special cases — classified in §8 below. Every candidate already has `volsync.backube/privileged-movers: "true"` + a materialized `volsync-kopia-repository` Secret + cluster-wide RBAC (the CRB); migration only requires adding the namespace gate label + PVC fuse labels and removing inline RS/RD. The historical table rows below are kept for reference but are **superseded by the §8 classification** for anything not yet migrated.

| Rank | App / namespace | PVC | Size | Cadence | Mover | Live dsr drift? | Argo | Shape handoff | Risk | Next action |
|---|---|---|---|---|---|---|---|---|---|---|
| ✅ | homepage-dashboard | config | 5Gi | daily | 568 | no (config-dst) | Synced | **DONE** | — | **MIGRATED 2026-05-29** (`df0d47a4`+`48d342f8`); operator-managed, backup Successful |
| 2 | copyparty | copyparty-data | 20Gi | daily | 568 | yes (…-backup) | Synced | no-op | low | RBAC → labels(+SSA=false) → handoff |
| ✅ | tubesync | config-pvc | 10Gi | daily | 568 | yes (…-backup) | Synced | **DONE** | — | **MIGRATED 2026-05-30** (`5ed1e67b`); operator-managed at tier=daily, backup Successful, dsr repaired first (Option-R, corrected Argo-unlock sequence) |
| 4 | jellyfin | config | 5Gi | daily | 568 | yes (null) | Synced | no-op | low | RBAC → labels(+SSA=false) → handoff |
| 5 | fizzy | data | 10Gi | daily | 568 | **no** (data-dst) | Synced | no-op | low-med | board data = the product; rebuildable-ish |
| 6 | swarmui | swarmui-data | 5Gi | daily | 568 | — | Synced | no-op | med | multi-PVC ns (data+output+exempt model cache) |
| 7 | swarmui | swarmui-output | 50Gi | daily | 568 | — | Synced | no-op | med | user-generated images |
| 8 | open-webui | storage | 10Gi | daily | 568 | — | Synced | no-op | med | chat history |
| 9 | perplexica | perplexica-data | 10Gi | daily | 568 | — | Synced | no-op | med | has its own SSDiff=false note |
| 10 | frigate | frigate-config | 10Gi | daily | 568 | **no** | Synced | no-op | med | NVR config/db (media exempt) |
| 11 | project-zomboid | zomboid-data | 20Gi | daily | 568 | — | Synced | no-op | med | game saves |
| 12 | project-nomad | flatnotes-data | 5Gi | daily | 568 | no | Synced | no-op | med | multi-PVC bundle |
| 13 | project-nomad | qdrant-data | 20Gi | daily | 568 | no | Synced | no-op | med | re-embeddable |
| 14 | posthog | redis7-data | 10Gi | daily | 568 | — | Synced | no-op | med | cache/queue |
| 15 | posthog | redpanda-data-kafka-0 | 20Gi | daily | 568 | — | Synced | no-op | med | queue |
| 16 | home-assistant | config | 10Gi | **hourly** | 568 | — | Synced | cadence↓ | high | hourly→daily reduction; high-value |
| 17 | n8n | data | 10Gi | **hourly** | **1000** | — | **ComparisonError** | mover+cadence change | high | fix Argo wedge + mover UID first |
| 18 | gitea | gitea-shared-storage | 10Gi | daily | **1000** | — | Synced | mover change | high | **Helm extraDeploy special case** (not a pvc.yaml) |
| 19 | paperless-ngx | data | 10Gi | **hourly** | 568 | — | Synced | cadence↓ | high | multi-PVC, hourly, docs |
| 20 | paperless-ngx | media | 20Gi | **hourly** | 568 | — | Synced | cadence↓ | high | scanned originals (irreplaceable) |
| 21 | project-nomad | nomad-storage | 120Gi | daily | 568 | no | Synced | no-op | high | large |
| 22 | project-nomad | mysql-data | 20Gi | daily | 568 | no | Synced | no-op | high | self-hosted MySQL (not CNPG) |
| 23 | posthog | postgres-data | 20Gi | daily | 568 | — | Synced | no-op | high | self-hosted PG (not CNPG) |
| 24 | immich | library | 300Gi | daily | 568 | — | Synced | no-op | high | irreplaceable photos; largest volume — migrate last |
| ✅ | karakeep | data-pvc / meilisearch-pvc | 10Gi ×2 | **hourly** | 568 (was 1001) | no | Synced | **DONE** | — | **MIGRATED 2026-05-30** (`93b2b5cb`); operator-managed at tier=hourly, both backups Successful, mover 1001→568 proven safe, data-pvc dsr repaired first (Option R) |

## 3. Recommended next candidate

> **All non-database app PVCs are MIGRATED (24 operator-managed, §1).** The low-risk cohort, the `n8n` canary, `home-assistant`, `gitea` (Helm special case), and the final disposable-reset batch (`paperless-ngx/{data,media}` + `immich/library`, `49b97920`, 2026-05-31) are all done.

The **only remaining candidate is `redis-instance/redis-master-0` — DEFERRED.** It is a Bitnami Helm StatefulSet (no clean GitOps `replicas:0` key for quiesce) under `infrastructure/database/`, and a non-critical cache (AOF replays on restart). Before touching it, confirm pvc-plumber should own database-namespace PVCs at all — otherwise leave it on inline RS/RD. **Do not start it without explicit authorization**, and observe the §8 NO-GO gates. No per-ns RoleBinding prereq (cluster-wide CRB). Everything else is either migrated, `backup-exempt` (posthog), or a permanent CNPG exclusion.

### Karakeep — MIGRATED (2026-05-30)
Karakeep was the highest-risk migration (two PVCs, hourly, non-568 mover, plus a data-pvc immutable-`dataSourceRef` defect). It is now **complete and operator-managed** (commit `93b2b5cb`): both PVCs at `tier=hourly` (cadence preserved), mover normalized 1001→568 with both initial backups **Successful**, after the data-pvc immutable-dsr repair (Option R: refresh RD → PV `Retain` → quiesce → one-shot backup → delete/recreate). It validated the destructive repair + handoff path end-to-end. **Cleanup pending:** the old retained PV `pvc-4cb90a74-e7df-4fc3-a967-1ab8603ffdd4` (`Released`/`Retain`) must NOT be deleted until explicitly approved.

### tubesync — MIGRATED (2026-05-30)
`tubesync/config-pvc` is **complete and operator-managed** (handoff commit `5ed1e67b`, `tier=daily`). It is the **second Option-R repair** and the one that hardened the sequence. The live PVC had an immutable `dataSourceRef=config-pvc-backup` (created before the `-dst` rename) vs Git `config-pvc-dst`. Repaired destructively (quiesced backup `…160611` → delete → recreate from quiesced snapshot with the correct `config-pvc-dst` dsr → handoff). New PVC UID `ce76e0b9…` (was `4722c1aa…`); **old PV `pvc-3f4378d9-c5d6-479c-9b65-e41626d01065` was `Released`/`Retain` (rollback) but is no longer present as of the 2026-05-31 fleet audit** (reclaimed/removed before the audit, not by it; tubesync healthy). Operator RS first backup **Successful** (`lastSync=2026-05-30T17:24:19Z`, `nextSync=2026-05-31T02:05:00Z`, schedule `5 2 * * *`); operator RD `latestImage=volsync-config-pvc-dst-dest-20260530172156`; both `managed-by=pvc-plumber`. Sibling `media-pvc` (SMB, `backup-exempt`) untouched.

### Option-R repair — corrected sequence + operational learnings (hardened on tubesync 2026-05-30)

The original Option-R (Karakeep) sequence had a **gap for already-wedged / drift PVCs**: it scaled the workload down before making Argo syncable, so the scale-down sync stalled behind the pre-existing immutable-dsr ComparisonError. Corrected order — **unlock Argo *before* scale-down**:

**Phase 0.5 — Argo unlock (NEW, do this first for any drift PVC).**
1. **Try `ServerSideApply=false` first** (`argocd.argoproj.io/sync-options: ServerSideApply=false` on the PVC). On tubesync this **did not clear the wedge** and even produced an isolated SyncError (applying *any* field to a Bound PVC re-validates its immutable spec). Do **not** keep retrying it.
2. **Fallback: temporary Git alignment to the live immutable value.** Set the desired `dataSourceRef.name` in Git to the live value (`config-pvc-backup`) so Argo computes a clean diff (the AppSet `ignoreDifferences` then masks `/spec/dataSourceRef`). Keep the `-dst` RD present. This is what actually made tubesync syncable. **It is temporary** — restored in Phase 5.

Then proceed: **1** confirm readiness (RS last backup Successful, RD latestImage refreshed, sourceIdentity matches, PV `Retain`, app syncable, operator healthy) → **2** scale workload 1→0 via Git → **3** quiesced backup (RS `schedule`→`manual: backup-<date>-quiesced`) → **4** refresh RD (`manual: restore-<date>-quiesced`; verify new latestImage + VolumeSnapshot `readyToUse`) → **5 restore the final desired Git `dataSourceRef` back to `-dst` *before* recreate** → **6** delete + recreate PVC (Argo/populator restores from the quiesced snapshot) → **7** scale up + restore RS `schedule` → **8** pvc-plumber handoff (managed-namespace + fuse labels, remove inline RS/RD).

**Critical ArgoCD stale-cache learnings (cost real time on tubesync — bake these in):**
- **A passive refresh does not apply spec changes here.** Setting `replicas`, an RS/RD `trigger`, etc. in Git and waiting showed `Synced` against a **stale server-side-diff cache** while the live object was unchanged. The reliable apply is **hard-refresh (`argocd.argoproj.io/refresh=hard`) → THEN an explicit sync operation**. Every phase used `kubectl -n argocd patch application <app> --type=merge -p '{"operation":{"sync":{"revision":"<sha>","prune":true}}}'` after a hard refresh.
- **Hard-refresh BEFORE deleting the PVC in Phase 6.** ArgoCD `selfHeal` recreates a deleted PVC from its **cached** desired manifest. On tubesync the Phase-5 commit (dsr→`config-pvc-dst`) had not been refreshed into cache, so selfHeal recreated the PVC with the **stale** `config-pvc-backup` dsr and the populator failed (`ReplicationDestination config-pvc-backup not found`). Fix: hard-refresh until `reconciledRev` == the Phase-5 SHA **before** deleting; then the recreate (selfHeal or explicit) uses the correct dsr. The wrongly-created PVC was `Pending` (no data) and was simply deleted + re-synced.
- **Terminating a stuck Argo sync op when there is no `argocd` CLI:** the `Application` CRD has **no `status` subresource** (`kubectl get crd applications.argoproj.io -o jsonpath='{.spec.versions[0].subresources}'` → `{}`), so `kubectl patch --subresource=status` returns a misleading `NotFound`. Patch `.status` via the **main resource**: `kubectl -n argocd patch application <app> --type=merge -p '{"operation":null,"status":{"operationState":null}}'`. A controller pod restart alone does **not** clear it — a `Running` op persisted in `.status.operationState` is resumed on startup.

**Empty-dsr unlock variant (hardened on n8n 2026-05-31).** When the **live** PVC `dataSourceRef` is *empty* (PVC created before the dsr pattern) but Git declares `<pvc>-dst`, the app can look `Synced` yet still **wedge during a sync operation**: Argo's SSA dry-run tries to apply `dataSourceRef: null → <pvc>-dst`, which is forbidden on a Bound PVC (immutable), even though the *comparison* is masked by `ServerSideDiff=false` + `ignoreDifferences`. On n8n this surfaced on the **quiesced-backup sync** (not scale-down — scale-down doesn't touch the PVC). The Phase-0.5 unlock for the empty case is to **temporarily REMOVE the `dataSourceRef` block from Git** (align to the live empty state) so the dry-run has no immutable change to make; then **restore `dataSourceRef: <pvc>-dst` in Phase 5/6, before the PVC delete/recreate** (the recreated PVC must carry `-dst` so the populator restores). `ServerSideApply=false` does **not** help here (client-side apply nulls `dataSource` → "must match dataSourceRef"). Note: empty-dsr apps in the 2026-05-30 reset batch happened not to hit this on their scale-down sync (timing), but n8n proves the general case needs the unlock — assume any empty→`-dst` PVC may wedge.

**Mover UID normalization — precedent (n8n 2026-05-31).** pvc-plumber v4.0.1 **forces mover `568/568/568`** (`PVC_PLUMBER_DEFAULT_{UID,GID,FSGROUP}=568`; no per-PVC override) — the handoff normalizes any inline non-568 mover to 568. This is now **proven safe on a `1000`-owned app**: n8n's `data` (owned `node:node`/1000) was backed up **Successfully** by the operator's 568 mover. Mechanism: the snapshot-clone mounts with `fsGroup: 568` (group-readable to the 568 mover) and **kopia stores each file's original uid/gid**, so restored data stays owned by 1000 and app-readable. This joins the Karakeep `1001→568` precedent. **UID 1000/1001 is no longer automatically a blocker** — but still **verify the first operator backup `Successful` per app** (the real test) and roll back (restore inline RS/RD at the original UID) if it fails. Remaining non-568 candidates: gitea (1000), redis-instance (1001).

## 4. Per-PVC migration checklist (proven nginx recipe)

Order is load-bearing — **namespace gate + fuse labels first, inline removal last**. Reversing strands the PVC with no backup chain.

1. **Namespace gate (RBAC is already satisfied cluster-wide — no RoleBinding step).** Confirm the cluster-wide `ClusterRoleBinding pvc-plumber:volsync-writer` exists (`kubectl get clusterrolebinding pvc-plumber:volsync-writer`; it covers all namespaces — there is **no per-namespace RoleBinding**). Then add the namespace software-gate label `pvc-plumber.io/managed-namespace: "true"` to the target namespace's manifest so the operator is allowed to write RS/RD there.
2. **v4 labels + Argo annotations on the PVC.** Add to the PVC: labels `pvc-plumber.io/enabled: "true"`, `pvc-plumber.io/manage-volsync: "true"`, `pvc-plumber.io/tier: "daily"`; annotations `argocd.argoproj.io/compare-options: ServerSideDiff=false` **and** `argocd.argoproj.io/sync-options: ServerSideApply=false`. (Can be the same commit as step 3.)
3. **Remove the inline RS/RD** documents from the app's `pvc.yaml` (keep the PVC + its `dataSourceRef`). Update any "defined below in this file" comment.
4. Commit → wait for **Cluster CI green** → **sync the app's Argo Application** (hard-refresh first if it shows a stale `Synced`).
5. **Confirm /audit** before removal showed `owner=inline-argo` / `already-matches` (operator observing), and **after** removal flips to `owner=managed-by-pvc-plumber` / `already-matches` within ~60s.
6. **Verify rc7 recreate** within 60s: `RS/<pvc>` + `RD/<pvc>-dst` exist, both `app.kubernetes.io/managed-by=pvc-plumber`, no label value contains `/`, `backup-identity` is an **annotation**, shape correct (repo/user/host/sc/vsc/cache/568/RD-capacity).
7. **Verify backup ran**: operator RS `latestMoverStatus.result=Successful` (initial sync on create) + `nextSyncTime` set.
8. **Verify PVC invariants**: UID unchanged, Bound, `dataSourceRef.name` unchanged, v4 labels present.

### 4a. Workflow gotcha — scoping the Git commit (observed 2026-05-29)
During the homepage-dashboard handoff, a **local hook auto-staged the entire dirty + untracked worktree** when `git add <file>` was run, so the first commit captured unrelated in-progress files (an ArgoCD-incident `values.yaml` + new prometheus alerts). It was caught **before push** and recovered with `git reset --soft HEAD~1`.

When the worktree contains unrelated local changes, a single-file migration commit must:
1. Inspect first: `git status --short` and `git diff --cached --name-only`.
2. Commit with an explicit pathspec: `git commit --only <intended-path> -m "..."` (`--only`/`-o` snapshots **only** that path regardless of what else is staged).
3. **Verify before push**: `git show --stat HEAD` must list **exactly** the intended file(s).

Do not rely on `git add <file>` alone to scope the commit here.

## 5. Hard-stop conditions (abort + roll back)
- Argo `ComparisonError` that does not self-clear after refresh.
- Missing namespace gate label `pvc-plumber.io/managed-namespace: "true"` (operator emits `skipped-namespace-not-managed`), or missing cluster-wide `ClusterRoleBinding pvc-plumber:volsync-writer`.
- Missing `volsync-kopia-repository` Secret.
- `/audit` stale (`stale=true`) or not reflecting live state.
- Operator logs show `forbidden` / `create-failed` / invalid-label / `panic` / crashloop.
- RS/RD not recreated within **60s** of the prune.
- Recreated RS/RD not `managed-by=pvc-plumber`.
- PVC UID / spec / `dataSourceRef` changes.
- VolSync backup fails (`latestMoverStatus.result != Successful`).

## 6. Rollback (pure GitOps, data-safe)
1. Restore the inline RS/RD documents into the app's `pvc.yaml` from the prior commit (`git show <pre-handoff>:<path>`).
2. Commit + push; sync the app.
3. Argo recreates the `managed-by=argocd` RS/RD; verify the inline chain is back and a backup runs.
4. **Do not strip the v4 labels** unless they cause a confirmed issue — they are inert while inline RS/RD are Argo-owned (operator observes, no ops).
RS/RD are orchestration CRs, not data; churn does not touch the PVC or the kopia repo (lineage is keyed by namespace/pvc identity).

## 7. Stale docs — status
These predated rc6/rc7. The **pure-doc / comment-only** fixes were applied in the `docs(pvc-plumber): consolidate rc7 canary state and next migration plan` commit (2026-05-29). The only remaining item is the gated deployment.yaml label, which rolls the pod and must wait for a deliberate sync.

**✅ Fixed (this commit, pure doc / comment-only):**
- `docs/pvc-plumber-v4-nginx-canary-incident.md` — terminal state corrected: rc7 shipped the watch fix and the canary is **complete / operator-managed / backup Successful**; "Current safe state" relabeled historical with a current-state block added.
- `docs/pvc-plumber-v4-cutover.md` — Status section updated to rc7/permissive; karakeep reframed as deferred (nginx was the first canary); per-PVC rollback points to the GitOps procedure; change-log entry added.
- `docs/pvc-plumber-v4-inventory.md` — staleness banner added noting nginx-example/storage is now operator-managed and the snapshot predates rc5–rc7.
- `docs/pvc-plumber-v4-roadmap.md` — visual-explainer gate corrected (nginx, not karakeep); rc6/rc7 added to Completed.
- `docs/pvc-plumber-v4-prd.md` — execution cross-notes added under the Status row and the Phase-6 "27 orphans" row (locked design body unchanged).
- `infrastructure/controllers/pvc-plumber/README.md` — rewritten for permissive rc7 (synced, RBAC, blast-radius bounds, nginx canary, next candidate).
- `infrastructure/controllers/pvc-plumber/{kustomization,rbac,rbac-volsync-writer,deployment}.yaml` — header/inline comments updated audit→permissive; deployment.yaml "zero write-eligible PVCs / Karakeep next gate" comment corrected.
- root `CLAUDE.md` — "re-adoption in planning / inline RS/RD is the only correct pattern" corrected: rc7 live in permissive, one PVC operator-managed; inline RS/RD still correct for not-yet-migrated PVCs.

**⏳ Gated (NOT applied — rolls the pod):**
- `infrastructure/controllers/pvc-plumber/deployment.yaml` — `pvc-plumber.io/mode: audit` LABEL (×2: Deployment metadata line ~60 + pod template line ~78) contradicts permissive mode. The runtime mode is set by the `PVC_PLUMBER_MODE` env var, so this is cosmetic, but editing the pod-template copy rolls the operator pod on sync. Apply with a deliberate sync, not as a doc-only change. (Legacy-label clarifying comments were added inline in this commit.)
- `docs/pvc-plumber-v4-prd.md` — Phase-6 "adopt 27 orphans" language contradicts the no-adoption-in-Phase-6 contract in the cutover doc; cross-note rather than rewrite (PRD is a locked design contract).

## 8. SAVE_FOR_END tier — classification (read-only plan, 2026-05-31)

The remaining (non-migrated) PVCs are databases, high-value app state, and special cases. Classified via an 8-agent read-only fan-out + adversarial safety review. **Classes:** **A** = leave on app/DB-native backup, don't pvc-plumber-migrate now · **B** = app-consistent dump/quiesce BEFORE recreate+handoff · **C** = Option-R quiesced volume snapshot acceptable · **D** = defer / human decision.

### Snapshot-safety rule (the key principle)
A scaled-to-0 **quiesced** Longhorn snapshot is crash-safe **only for files, SQLite, and AOF-at-rest** (the engine closes its file cleanly on shutdown and replays/truncates on start). It is **NOT** app-consistent for a **live multi-file RDBMS** (Postgres — torn WAL/heap if SIGKILL'd before the shutdown checkpoint) or a **fsync-disabled stream log** (Redpanda with `--unsafe-bypass-fsync` — on-disk durability was never guaranteed). Those require a **native dump/export (Class B)** or are **disposable/exempt (Class A)**. Never snapshot a live DB engine and label it a safe backup.

| ns / PVC | engine on PVC | mover | class | strategy |
|----------|---------------|-------|-------|----------|
| posthog/postgres-data | live Postgres 15 (self-hosted) | n/a | **A — ✅ EXEMPT 2026-05-31** | Disposable. `backup-exempt=true` set, inline RS/RD removed, dsr removed (`969a8e35`). PVC retained/Bound (not deleted). **Not** in Option-R queue, **not** pvc-plumber-migrated. If preservation ever needed: native `pg_dump`, never a raw PG_DATA snapshot. |
| posthog/redis7-data | Valkey, **no persistence** (`save ""`, no AOF) | n/a | **A — ✅ EXEMPT 2026-05-31** | Pure cache. `backup-exempt=true`, RS/RD removed (`969a8e35`). PVC retained/Bound. Never migrate. |
| posthog/redpanda-data-kafka-0 | Redpanda `--unsafe-bypass-fsync`, ~1h retention | n/a | **A — ✅ EXEMPT 2026-05-31** | Ephemeral/rebuildable (auto-create topics). `backup-exempt=true`, RS/RD removed (`969a8e35`). PVC retained/Bound. Never migrate. |
| home-assistant/config | SQLite recorder + secrets/tokens/HACS | 568 | **C — ✅ DONE 2026-05-31** | Migrated (`5f9d3988`, tier=hourly). Config/.storage/automations restored; **recorder DB was corrupt → quarantined + fresh recorder (sensor history lost, config intact)**. Paused mid-run by the Longhorn outage, resumed after recovery. |
| n8n/data | SQLite-at-rest | 1000→568 | **C — ✅ DONE 2026-05-31** | Migrated (`ce634e66`, tier=hourly `27 * * * *`). Empty→`data-dst` dsr repaired; restored from quiesced snapshot; first operator backup Successful. **Mover normalized 1000→568 (approved, validated).** Old PV `pvc-1608bca4` was retained but is **no longer present (2026-05-31 audit; not deleted by it)**. |
| paperless-ngx/data | files (index/thumbs, rebuildable) | 568 | **C — ✅ DONE + restore-validated 2026-05-31** | Migrated (`49b97920`, tier=hourly `18 * * * *`). Empty reset; first operator backup Successful. **Restore drill (`b7052c30`/`03d38113`): added `dataSourceRef → data-dst`, then delete→recreate→VolSync populator restore validated byte-identical (sha256 match).** New uid after drill→`e8f6e79c`. DB is external CNPG (native, untouched). NOTE: empty→`-dst` recreate hit the **manifest-generate-paths stale-render race** (first recreate came back empty/no-dsr; fixed by hard-refresh until reconciled rev = dsr commit, then delete/recreate again). |
| paperless-ngx/media | files (documents/originals/archive/thumbnails) | 568 | **C — ✅ DONE + restore-validated 2026-05-31** | Migrated (`49b97920`, tier=hourly `34 * * * *`). Empty reset; first operator backup Successful. **DR-completion drill (`6d5c9051`/`bb5b2970`): added `dataSourceRef → media-dst`, then delete→recreate→VolSync populator restore validated byte-identical (sha256 match), `documents/` restored.** New uid after drill→`5b1fae16`. **No double-recreate** (stale-render mitigation held: hard-refresh + wait reconciled rev == dsr commit before delete). Gotcha: dsr added *before* quiesce → bound-PVC ComparisonError until delete (expected); and the scale-back-up needed a clean hard-refresh-to-clear before sync (ArgoCD stale cluster-state cache no-opped the replicas:0→1 apply otherwise). |
| gitea/gitea-shared-storage | Git repos/LFS (files) | 1000→568 | **C — ✅ DONE 2026-05-31** | Migrated (`c1129533`, tier=daily). **Helm `extraDeploy` special case** handled — RS/RD removed from `values.yaml extraDeploy`, fuse labels added via `kustomization.yaml` JSONPatch on the chart-generated PVC. Mover normalized 1000→568 (validated). 5 repos restored. DB stayed native (CNPG, untouched). |
| immich/library | derived files (~6GiB actual / 300Gi prov.) | 568 | **C — ✅ DONE 2026-05-31** | Migrated (`49b97920`, tier=daily `23 2 * * *`). **Empty reset** (disposable, user-authorized) — recreated EMPTY, NO dsr; first operator backup Successful (next `2026-06-01T02:23Z`). uid→`ba6ca359`. Originals on exempt NFS `nfs-photos`; DB is CNPG (intact → broken/missing-asset UI, accepted). **Required:** scale BOTH `immich-server` + `immich-machine-learning` to 0 (ML co-mounts library RWO), flip server RollingUpdate→Recreate, and an `init-library-markers` initContainer to recreate the `.immich` folder-check markers (else server crashloops on empty library vs intact DB). |
| redis-instance/redis-master-0 | Redis AOF + RediSearch/ReJSON | **1001** | **C / D** | AOF replays on restart (torn tail truncated — may drop newest index writes; acceptable for a broker/cache). **Scope decision:** it lives under `infrastructure/database/` — confirm pvc-plumber should own database-namespace PVCs before touching; else defer. |
| cloudnative-pg/* (8: gitea/immich/paperless/temporal × data+WAL) | CNPG PG_DATA/WAL | n/a | **A — NEVER** | Operator-owned; Barman→S3 (RustFS) continuous WAL + daily ScheduledBackup. Never label / never RS/RD / never recreate. Permanent exclusion. |

### Per-tier NO-GO gates (all must hold before any SAVE_FOR_END recreate)
1. Longhorn robustness **healthy** (not degraded/rebuilding) on the target volume.
2. **RD `latestImage` refreshed after a fresh quiesced backup** — every RD is currently stale (~2026-05-21; `restore-once` never re-fired). Skipping the bump restores week-old data (the most pervasive landmine).
3. dataSourceRef drift reconciled-from-Git verified (several live-point at *nonexistent* `-backup` RDs; recreate fixes it only because the Git `-dst` RD exists).
4. PV reclaim is `Delete` — temp-patch to `Retain` for rollback margin, esp. immich/library + paperless/media.
5. Preserve non-568 mover UIDs (n8n 1000, gitea 1000, redis 1001).
6. immich: RollingUpdate→Recreate first. PostHog: if postgres-data kept, verify a clean shutdown log; note `skip-restore=true` suppresses restore.

### Execution order (when authorized — explicit per-PVC only)
~~n8n (canary)~~ ✅ DONE → ~~home-assistant~~ ✅ DONE → ~~gitea~~ ✅ DONE → ~~paperless data~~ ✅ DONE → ~~paperless media~~ ✅ DONE → ~~immich~~ ✅ DONE (`49b97920`, empty reset) → **redis-instance/redis-master-0 — DEFERRED** (only remaining; Bitnami Helm StatefulSet with no clean GitOps `replicas:0` key + lives under `infrastructure/database/` — confirm pvc-plumber should own database-namespace PVCs before touching; non-critical cache, AOF replays on restart). ~~posthog~~ ✅ **EXEMPT 2026-05-31** (disposable; backup-exempt, RS/RD removed, never migrate — `969a8e35`). **CNPG: never.** **All non-database app PVCs are now migrated; only the deferred redis-instance and the permanent CNPG/posthog exclusions remain.**

> **home-assistant** was paused mid-run on 2026-05-31 by a cluster Longhorn outage (GPU node `nfwh89` down → `ReplicaSchedulingFailure`), then **resumed and completed** after Longhorn recovered (faulted=0, rebuilding=0, clones healthy). Lesson: hard-stop migrations on `ReplicaSchedulingFailure`; resume only at 0 faulted / 0 degraded.

**Recommendation:** the campaign can pause here — no remaining hard repairs are outstanding (all candidates stable, drift masked, backups current). Resume only on explicit authorization, starting with the n8n canary under the gates above. Full reasoning in Mink: `projects/talos-argocd-proxmox/saveforend-pvc-plumber-migration-classification-2026-05-30-read-only-plan.md`.

---

## Appendix — Ready-to-run prompt for the NEXT migration (DO NOT auto-execute)

Target: **`homepage-dashboard/config`** · file `my-apps/media/homepage-dashboard/pvc.yaml` · RS `config` / RD `config-dst` · 5Gi · daily · mover 568 · no dsr drift.

```
> The original homepage-dashboard rc7 prompt here is **obsolete** (homepage-dashboard migrated 2026-05-29; operator is now `v4.0.1`; the per-namespace-RoleBinding "Step 1" no longer exists). Use the current-model template below for a SAVE_FOR_END candidate (start with the §8 canary, `n8n/data`).

Migrate <ns>/<pvc> to pvc-plumber v4.0.1 operator management.

Scope: Talos repo + the <ns> namespace only. Do not touch any other app/PVC. No /pvc-plumber-adopt.
No manual RS/RD. No image/RBAC changes. GitOps only; verify branch before each commit; git commit --only.

Preconditions (read-only): pvc-plumber v4.0.1 pod Ready; my-apps-<ns> Synced/Healthy; cluster-wide
ClusterRoleBinding pvc-plumber:volsync-writer present (NO per-ns RoleBinding needed); namespace has
privileged-movers=true + volsync-kopia-repository Secret; live RS/RD managed-by=argocd; capture PVC UID.
For a Class-C migration that also has live dataSourceRef drift, run the Option-R sequence (§3 of the
cutover doc / "Option-R" section above): heal Longhorn → fresh quiesced backup → refresh RD → restore
final Git dsr → delete+recreate PVC → bring up → handoff.

Handoff commit (the actual operator adoption): add namespace label pvc-plumber.io/managed-namespace="true";
add PVC fuse labels pvc-plumber.io/enabled="true", manage-volsync="true", tier="daily|hourly" (match
existing cadence — see the cadence caveat in §1); remove the inline ReplicationSource + ReplicationDestination
docs (keep PVC + dataSourceRef). kustomize build to validate. Push, wait CI green, sync only my-apps-<ns>
(hard-refresh first if stale-Synced). PRESERVE the existing mover UID (n8n 1000, gitea 1000, redis 1001).

Verify within 60s: RS/<pvc> + RD/<pvc>-dst recreated as managed-by=pvc-plumber; PVC UID unchanged/Bound/
dataSourceRef unchanged/fuse labels present; /audit owner=managed-by-pvc-plumber, already-matches, v4,
stale=false; operator RS latestMoverStatus.result=Successful; operator logs clean; Argo Synced/Healthy.

Hard-stop + rollback per §5/§6. Honor the §8 NO-GO gates. Stop after report.
```
