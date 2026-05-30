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
| Shipped fixes (rc6→rc7, now in v4.0.0) | RS/RD watch + child→PVC reverse-map + periodic self-heal requeue + partial-inline-argo guard + `/audit` staleness. Closes the rc6 reconcile-trigger gap (the 2026-05-28 15h backup gap). |
| Watch proof | Synthetic `pvc-plumber-watch-smoke`: managed RS *and* RD deleted → recreated in <5s, no PVC poke. |
| nginx-example/storage canary | **Functionally complete.** Inline Argo RS/RD removed from Git (`50a84cc9`), Argo pruned them, rc7 recreated `RS/storage` + `RD/storage-dst` as `managed-by=pvc-plumber`, and the operator-managed RS produced a **Successful** initial backup (`lastSyncTime=2026-05-29T04:04:29Z`, kopia EXIT_CODE 0). `/audit`: `already-matches` / `managed-by-pvc-plumber` / `stale=false`. |
| nginx canary caveat | The first **cron-driven** recurrence (`nextSyncTime=2026-05-30T02:58:00Z`) is an optional, read-only follow-up — the create-time initial sync already proved the mechanism. |
| homepage-dashboard/config migration | **Complete (2026-05-29).** Commit 1 RBAC RoleBinding `df0d47a4`; Commit 2 handoff `48d342f8` (single-file: added v4 fuse + `ServerSideApply=false`, removed inline RS/RD). Argo pruned the inline `argocd`-owned RS/RD; rc7's RS/RD watch recreated `RS/config` + `RD/config-dst` as `managed-by=pvc-plumber` in <20s. Schedule rewritten `9 2 * * *` → `36 2 * * *` (deterministic). Initial backup **Successful**: `lastSyncTime=2026-05-29T18:42:44Z`, `latestMoverStatus.result=Successful`, `nextSyncTime=2026-05-30T02:36:00Z`. PVC UID unchanged (`078aff64-…`), Bound, `dataSourceRef=config-dst`. `/audit`: `label_source=v4` / `already-matches` / `managed-by-pvc-plumber` / `stale=false`. |
| karakeep migration (Gate 3) | **Complete (2026-05-30).** Both PVCs handed off in one commit (`93b2b5cb`): RBAC pre-existed (`df0d47a4`); added v4 fuse `tier=hourly` + `ServerSideApply=false`, removed inline RS/RD. Operator recreated all four (`RS/data-pvc`+`RD/data-pvc-dst`, `RS/meilisearch-pvc`+`RD/meilisearch-pvc-dst`) as `managed-by=pvc-plumber`. **Hourly cadence preserved** via `tier=hourly` (deterministic `data-pvc 10 * * * *`, `meilisearch 0 * * * *`). **Mover UID 1001→568 normalization proven safe** — both initial backups **Successful** (`meilisearch-pvc 2026-05-30T03:26:12Z`, `data-pvc 2026-05-30T03:27:20Z`) reading the 1001-owned data via snapshot-clone fsGroup. PVC UIDs unchanged (`data-pvc 90070779-…`, `meilisearch-pvc 24bdda38-…`). `/audit`: both `already-matches`/`managed-by-pvc-plumber`/`v4`/`stale=false`. Preceded by the data-pvc immutable-dsr repair (Option R). |
| karakeep cleanup TODO | Old retained PV **`pvc-4cb90a74-e7df-4fc3-a967-1ab8603ffdd4`** (`Released`/`Retain`, the pre-repair data-pvc volume) **must NOT be deleted until explicitly approved** — it is the data-pvc repair rollback net. |
| tubesync migration | **Complete (2026-05-30).** Handoff `5ed1e67b`, `tier=daily`. Second Option-R repair (immutable `config-pvc-backup`→`config-pvc-dst`); hardened the corrected Argo-unlock sequence + stale-cache learnings (see §3). Operator RS backup **Successful** (`lastSync=17:24:19Z`, `nextSync=2026-05-31T02:05:00Z`, `5 2 * * *`), RD `latestImage=…20260530172156`, both `managed-by=pvc-plumber`. New PVC UID `ce76e0b9…`; old PV `pvc-3f4378d9-…` `Released`/`Retain` (rollback, do not delete). |
| **Managed namespaces** (`pvc-plumber.io/managed-namespace=true`; RBAC via cluster-wide CRB) | `nginx-example`, `homepage-dashboard`, `karakeep`, `fizzy`, `frigate`, `project-nomad`, `tubesync` (7) |
| **Operator-managed PVCs** (`managed-by=pvc-plumber` RS/RD) | `nginx-example/storage`, `homepage-dashboard/config`, `karakeep/data-pvc`, `karakeep/meilisearch-pvc`, `fizzy/data`, `frigate/frigate-config`, `project-nomad/{flatnotes-data,qdrant-data,nomad-storage,mysql-data}`, `tubesync/config-pvc` (11) |

### Known caveats / fleet-wide gaps
- **RBAC is the universal blocker.** The per-namespace `RoleBinding pvc-plumber:volsync-writer` exists **only in `nginx-example`, `homepage-dashboard`, and `karakeep`** (the three migrated namespaces). Every other candidate namespace needs it created **before** any inline RS/RD removal — otherwise Argo prunes the chain and the operator cannot recreate it (the exact 15h-gap failure mode).
- All 18–19 candidate namespaces already have `volsync.backube/privileged-movers: "true"` and a materialized `volsync-kopia-repository` Secret. Those two prerequisites are met fleet-wide.
- No candidate PVC carries the v4 fuse labels yet — migration requires **adding** `pvc-plumber.io/enabled=true` + `manage-volsync=true` + `tier` to the PVC.
- Only **`n8n`** is currently in Argo `ComparisonError` (immutable-dataSourceRef SSA wedge). Other apps with live `dataSourceRef` drift (e.g. copyparty) are still `Synced/Healthy` because the my-apps AppSet `ignoreDifferences` masks the PVC dataSource fields. **For a drift PVC that is merely going to be migrated (RS/RD handoff, PVC stays Bound), `ServerSideApply=false` is NOT needed and not recommended** — the bound PVC's spec is immutable, so any apply to it (incl. SSA=false) re-validates and can throw an isolated SyncError. The fuse-label handoff (labels + remove inline RS/RD) syncs fine because Argo only *applies* the labels/annotations, never the immutable `dataSourceRef`. SSA=false is only relevant when you must force ArgoCD to *apply a changed PVC field*, which the drift PVCs do not require until/unless their `dataSourceRef` is wrong (see Option-R below).
- **RBAC is no longer per-namespace.** v4.0.1 (`a1916d61`) replaced the per-namespace `RoleBinding pvc-plumber:volsync-writer` model with a **single cluster-wide `ClusterRoleBinding pvc-plumber:volsync-writer`** (subject `ServiceAccount/pvc-plumber/pvc-plumber`, RS/RD verbs only). tubesync migrated with **no namespace RoleBinding step** — the CRB covers every namespace. The "RBAC first" step in §4 is now satisfied fleet-wide by that one CRB; verify `kubectl get clusterrolebinding pvc-plumber:volsync-writer` instead of a per-ns RoleBinding. The §1 "RBAC is the universal blocker" caveat is superseded.
- **Cadence is set by `tier`, not forced to daily.** v4 rewrites each RS schedule to a deterministic per-PVC minute **within the chosen tier's window** (`tier=hourly` → `MM * * * *`, `tier=daily` → `MM 2 * * *`, etc.). Karakeep ×2 migrated at **`tier=hourly`** and kept their hourly cadence (proven: `data-pvc 10 * * * *`, `meilisearch 0 * * * *`). The remaining hourly apps (home-assistant, n8n, paperless-ngx ×2) should likewise use `tier=hourly` to preserve cadence — only a wrong tier choice (hourly→daily) would reduce frequency.
- **mover UID change — proven safe.** v4 normalizes `moverSecurityContext` to `568/568/568`. Karakeep ×2 (inline `1001`) migrated and **backed up successfully** as 568 — the snapshot-clone `fsGroup` makes the 1001-owned data group-readable to the 568 mover. Remaining non-568 inline movers (n8n `1000`, gitea `1000`) get the same ownership change; the Karakeep result indicates this is low-risk, but still confirm the first backup succeeds per app.

## 2. PVC readiness table

**21 remaining** candidate PVCs (excludes the completed `nginx-example/storage`, `homepage-dashboard/config`, and `karakeep/{data-pvc,meilisearch-pvc}`, CNPG/Barman DB PVCs, and infra redis). Except where noted, every row is `owner=inline-argo`, `privileged-movers=true`, kopia Secret present, **RBAC RoleBinding missing**, **v4 labels absent in Git**. Columns below capture the discriminating factors.

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

## 3. Recommended next 3 candidates

> ~~#1 `homepage-dashboard/config`~~ — **MIGRATED 2026-05-29** (operator-managed, backup Successful). The next routine candidates below remain low-risk single-PVC handoffs. **Do not start any of these without explicit per-PVC authorization.**

**#1 — `copyparty/copyparty-data`**. Single 20Gi PVC, daily, mover 568, file-share scratch/uploads (rebuildable). Has live dsr drift (`…-backup`) but the app is `Synced/Healthy`; add `sync-options: ServerSideApply=false` to the PVC (nginx/homepage recipe). Prereq: `volsync-writer` RoleBinding in `copyparty`.

~~**#2 — `tubesync/config-pvc`**~~ — **MIGRATED 2026-05-30** (`5ed1e67b`; Option-R dsr repair + handoff). Next config-PVC candidate is **`jellyfin/config`** (single config PVC, daily, 568, rebuildable; live dsr drift `null` → needs Option-R repair like tubesync). No per-ns RoleBinding prereq anymore (cluster-wide CRB).

**#3 — `fizzy/data`**. Single 10Gi PVC, daily, mover 568, **no dsr drift** (`data-dst`) — same zero-SSA-wedge profile as homepage. Board data is the product but rebuildable-ish; slightly higher value than the config volumes above. Prereq: `volsync-writer` RoleBinding in `fizzy`.

### Karakeep — MIGRATED (2026-05-30)
Karakeep was the highest-risk migration (two PVCs, hourly, non-568 mover, plus a data-pvc immutable-`dataSourceRef` defect). It is now **complete and operator-managed** (commit `93b2b5cb`): both PVCs at `tier=hourly` (cadence preserved), mover normalized 1001→568 with both initial backups **Successful**, after the data-pvc immutable-dsr repair (Option R: refresh RD → PV `Retain` → quiesce → one-shot backup → delete/recreate). It validated the destructive repair + handoff path end-to-end. **Cleanup pending:** the old retained PV `pvc-4cb90a74-e7df-4fc3-a967-1ab8603ffdd4` (`Released`/`Retain`) must NOT be deleted until explicitly approved.

### tubesync — MIGRATED (2026-05-30)
`tubesync/config-pvc` is **complete and operator-managed** (handoff commit `5ed1e67b`, `tier=daily`). It is the **second Option-R repair** and the one that hardened the sequence. The live PVC had an immutable `dataSourceRef=config-pvc-backup` (created before the `-dst` rename) vs Git `config-pvc-dst`. Repaired destructively (quiesced backup `…160611` → delete → recreate from quiesced snapshot with the correct `config-pvc-dst` dsr → handoff). New PVC UID `ce76e0b9…` (was `4722c1aa…`); **old PV `pvc-3f4378d9-c5d6-479c-9b65-e41626d01065` is `Released`/`Retain` and retained as rollback — do not delete until approved.** Operator RS first backup **Successful** (`lastSync=2026-05-30T17:24:19Z`, `nextSync=2026-05-31T02:05:00Z`, schedule `5 2 * * *`); operator RD `latestImage=volsync-config-pvc-dst-dest-20260530172156`; both `managed-by=pvc-plumber`. Sibling `media-pvc` (SMB, `backup-exempt`) untouched.

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

## 4. Per-PVC migration checklist (proven nginx recipe)

Order is load-bearing — **RBAC first, inline removal last**. Reversing strands the PVC with no backup chain.

1. **RBAC first.** Add a `RoleBinding pvc-plumber:volsync-writer` stanza for the target namespace to `infrastructure/controllers/pvc-plumber/rbac-volsync-writer.yaml`. Commit → **sync the `pvc-plumber` Argo app** → verify `kubectl get rolebinding pvc-plumber:volsync-writer -n <ns>`.
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
- Missing `volsync-writer` RoleBinding in the target namespace.
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

---

## Appendix — Ready-to-run prompt for the NEXT migration (DO NOT auto-execute)

Target: **`homepage-dashboard/config`** · file `my-apps/media/homepage-dashboard/pvc.yaml` · RS `config` / RD `config-dst` · 5Gi · daily · mover 568 · no dsr drift.

```
Migrate homepage-dashboard/config to pvc-plumber rc7 operator management.

Scope: Talos repo + the homepage-dashboard namespace only. Do not touch any other app/PVC.
Do not touch Karakeep. No /pvc-plumber-adopt. No manual RS/RD. No manual PVC patch/label/annotate.

Preconditions to verify (read-only): pvc-plumber rc7 pod Ready/restarts 0; my-apps-homepage-dashboard
Synced/Healthy, no ComparisonError; live RS/storage... (config) + RD config-dst both managed-by=argocd;
PVC config Bound, dataSourceRef.name=config-dst (no drift), no v4 labels yet; namespace has
privileged-movers=true + volsync-kopia-repository Secret; RoleBinding pvc-plumber:volsync-writer
is ABSENT (will be added). Capture PVC UID.

Step 1 (RBAC first): add a RoleBinding pvc-plumber:volsync-writer stanza for namespace
homepage-dashboard to infrastructure/controllers/pvc-plumber/rbac-volsync-writer.yaml. Commit
"chore(pvc-plumber): grant volsync-writer in homepage-dashboard". Push, wait CI green, sync the
pvc-plumber Argo app, verify the RoleBinding exists.

Step 2 (labels + annotations + inline removal, one commit): edit my-apps/media/homepage-dashboard/pvc.yaml:
add PVC labels pvc-plumber.io/enabled="true", manage-volsync="true", tier="daily"; the
compare-options: ServerSideDiff=false annotation is ALREADY present — ADD only
sync-options: ServerSideApply=false; remove the inline
ReplicationSource/config and ReplicationDestination/config-dst documents (keep PVC + dataSourceRef).
kustomize build to validate. Commit "chore(homepage-dashboard): hand off config VolSync to pvc-plumber rc7".
Push, wait CI green, sync only my-apps-homepage-dashboard (hard-refresh if stale-Synced).

Step 3 (verify within 60s): RS/config + RD/config-dst recreated as managed-by=pvc-plumber, no '/'
in labels, backup-identity annotation, shape correct, RD capacity 5Gi; PVC UID unchanged/Bound/
dataSourceRef unchanged/v4 labels present; /audit owner=managed-by-pvc-plumber, already-matches,
stale=false; operator RS latestMoverStatus.result=Successful; operator logs clean; Argo Synced/Healthy.

Hard-stop + rollback per docs/pvc-plumber-v4-migration-readiness.md §5/§6. Stop after report.
```
