# Managed PVC backup notes

Reference + history for the per-PVC backup wiring. Two purposes:

1. Explain **why application PVC manifests are terse** (no inline migration
   narrative) and where the canonical explanation of each field lives.
2. Preserve the **closed v4.0.1 handoff ledger** — the per-PVC facts that
   aren't recoverable from the live cluster (retained PV names, mover-UID
   normalization, disposable resets).

> This is a **notes/history** companion. The living how-to — the label
> contract, how to add/exempt/verify a backup, the restore-on-recreate
> mechanism, troubleshooting — is in **[storage-architecture.md](../../storage-architecture.md)**
> ("the one doc") and the `.claude/commands/add-backup.md` workflow. Do not
> duplicate that here.

---

## Comment convention (why the PVC YAML looks bare)

A managed PVC manifest carries three load-bearing pieces, a **two-line
`dataSourceRef` hint**, and **no migration narrative**. Each piece was
previously buried in a multi-line comment block repeated across ~25 files;
those blocks were trimmed (2026-06-17) to the minimal hint below — they had
restated documented patterns and logged one-time migration events. The
canonical hint (keep it terse and consistent on new managed PVCs):

```yaml
  # Static dataSourceRef → ReplicationDestination/<pvc>-dst.
  # RS/RD are operator-managed by pvc-plumber.
  dataSourceRef:
    apiGroup: volsync.backube
    kind: ReplicationDestination
    name: <pvc>-dst
```

What each piece means, and where it's documented:

| On the PVC | What it does | Canonical doc |
|------------|--------------|---------------|
| Fuse labels `pvc-plumber.io/enabled`, `…/manage-volsync`, `…/tier` | Opt the PVC into operator-managed VolSync backup at a cadence | [storage-architecture.md](../../storage-architecture.md) label contract |
| Annotation `argocd.argoproj.io/compare-options: ServerSideDiff=false` | Stops Argo's SSA dry-run from rejecting the immutable `dataSourceRef` on a Bound PVC and wedging sync. **Keep it** — `validate-volsync-wiring.py` (`pvc_has_ssdiff_shim`) fails the build if a PVC with a static `dataSourceRef` is missing it | [argocd.md](../argocd/argocd.md) "Server-Side Diff & Apply Strategy" |
| Static `dataSourceRef → <pvc>-dst` | On PVC re-creation (DR / namespace recreate) the VolSync volume populator restores from the operator-managed `ReplicationDestination`'s `latestImage`. No-op while Bound | [storage-architecture.md](../../storage-architecture.md), `.claude/commands/add-backup.md` |

**The operator owns RS/RD.** `pvc-plumber` creates and repairs the
`ReplicationSource`/`ReplicationDestination` pair (labeled
`app.kubernetes.io/managed-by: pvc-plumber`) from the fuse labels. Never add an
inline RS/RD to a managed PVC's manifest and never hand-edit RS/RD —
reconcile through the labels. (This is the rule behind every
`# … RS/RD were REMOVED … do not re-add` comment that was deleted; the rule
itself lives in the root `CLAUDE.md`.)

Exception: `my-apps/home/project-nomad/kolibri/pvc.yaml` keeps an **inline,
Argo-owned** RS/RD on purpose — the app is `argocd-inactive` (disabled) and was
never migrated to the operator. Leave its marker comment intact.

---

## Durable gotchas (extracted from the removed comments)

- **An exempt PVC must carry NO `dataSourceRef`.** An exempt PVC has no
  `ReplicationDestination`; a dangling `dataSourceRef` deadlocks the PVC
  `Pending` forever on namespace recreate (the volume populator waits for an RD
  that never appears). This bit `project-nomad/nomad-storage` when it was
  exempted — the fuse labels **and** the `dataSourceRef` were removed together.
- **Operator movers run as `568:568:568`.** Apps whose inline movers previously
  ran as `1000` (n8n, gitea) or `1001` (karakeep) were normalized to `568`.
  This is safe: Kopia preserves each file's original uid/gid inside the repo,
  so restored data keeps its original ownership regardless of the mover UID.
- **Disposable-reset apps** (`paperless-ngx/data`, `paperless-ngx/media`,
  `immich/library`): during the handoff these were recreated **empty** (no
  `dataSourceRef`) to avoid auto-restoring nuked data, then had the
  `dataSourceRef` re-added during a DR-completion drill once real data was
  rebuilt and backed up. They now match the standard managed pattern.
- **immich `library` restore is partial by design.** Restoring `library`
  restores the *current* (post-reset) working set only. Originals live on the
  exempt NFS `nfs-photos` volume, and the immich CNPG database still references
  pre-reset assets — a restore does **not** fix the prior DB-to-asset mismatch
  (accepted).
- **Retained old PVs are orphaned rollback safety.** The Option-R migrations
  recreated each PVC from a quiesced snapshot and left the pre-handoff PV behind
  with `persistentVolumeReclaimPolicy: Retain` (see ledger). They are unbound
  and reclaimable once you're confident the migration is settled.

---

## v4.0.1 DRY handoff ledger (CLOSED — 2026-05-28 … 06-01)

One-time migration that moved every managed PVC's RS/RD from inline
(Argo-owned) resources to operator-owned resources. The campaign is **closed**:
full-cluster restores passed unattended on 2026-06-02, 2026-06-12, and
2026-06-13. The detailed per-PVC mechanics (Option-R reset from a quiesced
snapshot, immutable-`dataSourceRef` repair from `*-backup` → `*-dst`) are in
**git history** around 2026-05-28…31. The table preserves only the facts that
can't be re-derived from the live cluster.

| Namespace | PVC | Tier | Retained old PV | Mover UID | Notes |
|-----------|-----|------|-----------------|-----------|-------|
| open-webui | storage | daily | `pvc-be2c62e1` | 568 | Option-R reset |
| perplexica | perplexica-data | daily | `pvc-18d3d2c7` | 568 | Option-R reset |
| swarmui | swarmui-data | daily | `pvc-47c2ae80` | 568 | Option-R reset |
| swarmui | swarmui-output | daily | `pvc-3dc7b545` | 568 | Option-R reset |
| jellyfin | config | daily | `pvc-045a3e7b` | 568 | Option-R reset |
| copyparty | copyparty-data | daily | `pvc-a157ad5f` | 568 | Option-R reset |
| project-zomboid | zomboid-data | daily | `pvc-d71b929e` | 568 | Option-R reset |
| tubesync | config-pvc | daily | `pvc-3f4378d9` | 568 | Option-R reset |
| home-assistant | config | hourly (`46 * * * *`) | `pvc-52fd99ba` | 568 | Option-R reset |
| n8n | data | hourly (`14 * * * *`) | `pvc-1608bca4` | 1000 → 568 | Option-R reset; UID normalized (approved) |
| karakeep | data-pvc | hourly | — | 1001 → 568 | Gate-3 handoff (v4.0.0); dsr repaired `*-backup`→`*-dst` |
| karakeep | meilisearch-pvc | hourly | — | 1001 → 568 | Gate-3 handoff (v4.0.0) |
| gitea | gitea-shared-storage | daily | — | 1000 → 568 | chart-rendered PVC; fused via Kustomize JSONPatch |
| frigate | frigate-config | daily | — | 568 | fuse-only (no reset) |
| fizzy | data | daily | — | 568 | fuse-only (no reset) |
| project-nomad | flatnotes-data | daily | — | 568 | fuse-only |
| project-nomad | mysql-data | daily | — | 568 | fuse-only |
| project-nomad | qdrant-data | daily | — | 568 | fuse-only |
| homepage-dashboard | config | daily | — | 568 | rc7 cutover (2026-05-29) |
| nginx-example | storage | daily | — | 568 | rc7 cutover (2026-05-28/29); first operator backup 2026-05-29T04:04:29Z |
| paperless-ngx | data | hourly | — | 568 | disposable reset → dsr re-added during drill |
| paperless-ngx | media | hourly | — | 568 | disposable reset → dsr re-added during drill |
| immich | library | daily | — | 568 | disposable reset → dsr re-added during drill (partial restore, see gotchas) |
| restore-canary | restore-canary-data | manual | — | 568 | DR drill canary; bootstrapped pre-create |

---

## Backup-exempt inventory

Each exempt PVC carries `backup-exempt: "true"` + the
`storage.vanillax.dev/backup-exempt-reason` annotation (the manifest annotation
is the source of truth; CI guard `backup-exempt-contract` enforces the
fully-qualified key). Summary:

| Namespace | PVC | Why exempt |
|-----------|-----|------------|
| swarmui | swarmui-dlbackend | ComfyUI + Python/torch venv, reinstallable on first run |
| swarmui | swarmui-comfyui-models | shared NFS model cache (non-snapshottable, rebuildable) |
| frigate | frigate-media | SMB-backed recordings; retention managed by Frigate/NAS |
| project-zomboid | zomboid-server-files | SteamCMD-installed game files, rebuildable |
| project-nomad | nomad-storage | bulk scratch; owner-declared disposable (exempted 2026-06-12) |
| tubesync | media-pvc | SMB-backed YouTube archive, re-fetchable |
| posthog | redpanda-data-kafka-0 | disposable; Redpanda log is ephemeral (`--unsafe-bypass-fsync`, ~1h retention) |
| posthog | postgres-data | disposable; use native `pg_dump` if preservation ever needed |
| posthog | redis7-data | Valkey LRU cache (no RDB/AOF) |
| posthog | (clickhouse) | regenerable from PostHog ingest; long Kopia window collided with RustFS IAM flaps |
| redis-instance | redis-master-0 | paperless Celery broker + redis-commander UI; system-of-record is paperless data/media + CNPG |
| searxng | (redis) | ephemeral search cache |
| vllm | (model weights) | read-only NFS weights, re-downloadable |

---

## See also

- **[storage-architecture.md](../../storage-architecture.md)** — the living backup/restore architecture and day-2 ops
- **[disaster-recovery.md](../../disaster-recovery.md)** — full-cluster destroy/rebuild runbook + restore canary
- **[argocd.md](../argocd/argocd.md)** — Server-Side Diff & Apply strategy (why `ServerSideDiff=false` on managed PVCs)
- `.claude/commands/add-backup.md` — the add-a-backup workflow
- `hack/validate-volsync-wiring.py`, `scripts/validate-restore-contract.sh` — the wiring/restore-contract validators
- **git history** (~2026-05-28…06-01) — full per-PVC migration mechanics
