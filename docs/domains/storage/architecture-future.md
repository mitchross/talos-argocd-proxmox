# Future storage architecture: tiered CSI + VolSync restore-based DR

> **Status: FUTURE IDEA — not implemented, do not act on this now.** This is a
> direction to revisit **after the current pvc-plumber v4 migration campaign
> stabilizes**. No storage classes, app PVCs, or CSI drivers should change based
> on this document yet. Current live model is unchanged: Longhorn is the default
> CSI; backups are VolSync→Kopia→S3 (RustFS) wired per-PVC and increasingly
> managed by pvc-plumber v4. See
> [pvc-plumber-v4-migration-readiness.md](../../pvc-plumber-v4-migration-readiness.md).

## Motivating incident (2026-05-31)

During the SAVE_FOR_END pvc-plumber migration of `home-assistant/config`, the
**GPU node `talos-prod-cluster-gpu-workers-nfwh89` was powered off**. The HA
*app* volume itself stayed `healthy`, but **new VolSync backup *clone* volumes
failed with Longhorn `ReplicaSchedulingFailure`** (the quiesced-backup snapshot
clone couldn't place replicas), which **blocked the Home Assistant quiesced
backup** and forced a hard-stop of that migration. Cluster-wide, Longhorn showed
several faulted/degraded volumes and a rebuild storm while the node was away.

The key observation: **a powered-off node and degraded replica/clone scheduling
blocked an unrelated backup/restore operation**, even though the app's own data
volume was fine. That is a failure mode created by making *every* PVC depend on
distributed block storage health (replica scheduling, clone scheduling, node
availability) — including transient operations like VolSync snapshot clones.

This raised a broader question: **should Longhorn remain the default CSI for
everything, or should most homelab apps use simpler local storage + VolSync
restore-from-backup?**

> **Update 2026-06-01 — restore-based DR is now empirically proven, but that does
> not make it equivalent to live availability.** Four end-to-end restore drills
> passed byte-identical (copyparty, paperless/data, paperless/media,
> immich/library): delete the PVC → Argo recreates it with `dataSourceRef` → the
> VolSync populator restores from the managed `ReplicationDestination`. All 24
> operator-managed PVCs are now DR_COMPLETE. **This validates the "restore-based
> DR" half of the tiered model below** — the recovery path works and is testable.
> **Caveat that keeps this a FUTURE idea, not a decision:** restore-based DR
> restores *data*, but during the restore window the app is **down** (PVC delete
> → populator restore → pod restart). Longhorn's replicated tier buys *live
> availability* (a node/replica can fail without the app going down) — a
> genuinely different property. So the tiering question is really "which apps
> need live availability vs. which only need recoverable data," and the drills
> only answer the second half. Decide per-app in the review below; do not act yet.

## Core principle: CSI layer and backup layer are separate responsibilities

| Layer | Responsibility |
|-------|----------------|
| **CSI** (Longhorn / OpenEBS LocalPV / ZFS LocalPV) | Provisions and mounts **live** volumes. Nothing else. |
| **VolSync + pvc-plumber** | Backs up data (→ Kopia/S3), restores data, and recreates PVCs cleanly from Git (`dataSourceRef` → `ReplicationDestination`). The DR layer. |

Important: **OpenEBS (or any local CSI) does not fetch from S3.** The CSI only
creates the empty PVC. **VolSync** then populates it from S3/Kopia via the volume
populator (`dataSourceRef`). pvc-plumber keeps that RS/RD wiring DRY and
GitOps-managed. So "local CSI" does **not** mean "no DR" — DR comes from the
backup layer, which is independent of the CSI.

## Proposed tiered storage model

### Tier 1 — Default: local restore-based storage
Use a simple local CSI (**OpenEBS LocalPV**, **ZFS LocalPV**, or similar) for
**most non-database homelab apps**.

Recovery model (restore-based DR, *not* live HA):
1. Kubernetes/CSI provisions a **fresh local PVC** (empty).
2. **VolSync restores** the PVC from S3/Kopia via `dataSourceRef` →
   `ReplicationDestination`.
3. **pvc-plumber** manages the RS/RD wiring and keeps the GitOps backup/restore
   contract DRY.

Trade-off accepted: if the node hosting a local PVC dies, those apps go **down**
until the PVC is recreated + restored elsewhere. For many homelab apps that
downtime is acceptable, and the failure behavior is **explicit and simple**:
recreate PVC + restore from backup. No distributed-storage drama (no replica
scheduling, no clone scheduling, no cross-node replica health) gating routine
operations.

### Tier 2 — Replicated: Longhorn only where live-ish availability matters
Keep **Longhorn replicated** storage for the **selected** apps where quick
failover / live availability is worth the added complexity. Candidates (to be
decided in the review, not fixed here):
- maybe Home Assistant
- maybe Paperless
- maybe a few small critical config/state PVCs

**Do not** use Longhorn replication as the default for every random app PVC
unless the app truly needs it.

### Tier 3 — Database: native backups (not generic CSI snapshot/restore)
Databases should **not** rely primarily on generic CSI snapshot/restore.
- **CNPG Postgres → Barman → S3** (already in use; continuous WAL + scheduled base backups).
- `pg_dump` / app-native dump where appropriate.
- Database-specific recovery plans.

**CNPG PVCs must not be migrated to pvc-plumber/VolSync as generic app PVCs** —
they are operator-owned and Barman-backed. (This is already the standing rule;
see the SAVE_FOR_END classification.)

## Why this might be better

Longhorn-as-default means **every** app depends on distributed block storage
health: replica scheduling, clone scheduling, node availability, rebuild
behavior. In a homelab — where nodes get powered off, GPUs get toggled, and
capacity is tight — that creates failure modes where a powered-off node or a
degraded replica/clone state can block **unrelated** backup/restore operations
(exactly the 2026-05-31 incident).

A local-storage-plus-restore default makes failure behavior **explicit**:
- if a node dies, apps using local PVCs may go down;
- recovery is **recreate PVC + restore from backup**;
- far less distributed-storage drama in the common path;
- **VolSync / pvc-plumber becomes the primary DR layer** (which is already the
  direction the migration campaign is heading).

## Potential future plan: a storage architecture review

When the pvc-plumber migration campaign stabilizes, run a review that classifies
**every PVC** along these dimensions:
- needs live HA / fast failover?
- restore-from-backup acceptable?
- disposable?
- database-native backup?
- too large for routine restore (e.g. immich library)?
- should remain Longhorn?
- candidate for OpenEBS LocalPV / local storage?

Then define explicit storage classes by intent:
- **`local-restore`** — local CSI, DR via VolSync restore (default tier).
- **`replicated-critical`** — Longhorn replicated (Tier 2, opt-in).
- **`database-native` / no-generic-VolSync** — DB tier; Barman/dump, never
  generic VolSync.

### Open questions to resolve in the review
- Which local CSI (OpenEBS LocalPV vs ZFS LocalPV vs Longhorn `strict-local`)?
  ZFS LocalPV adds snapshots/compression; OpenEBS LocalPV is simplest.
- How does VolSync `copyMethod` change for local PVCs? Longhorn snapshot-clone
  (`copyMethod: Snapshot`) won't apply to a non-snapshotting local CSI —
  may need `copyMethod: Direct`/`Clone` or a different mover strategy. **This is
  a real design item**: the current VolSync RS/RD shape assumes Longhorn
  snapshots.
- Does pvc-plumber's generated VolSync shape need a per-tier template?
- Migration path: which apps move off Longhorn, and in what order, without data
  loss (each move is itself a backup → recreate-on-local → restore cycle).
- Capacity/topology: local PVCs pin an app to a node; how does that interact
  with the GPU node and scheduling?

## Explicitly out of scope right now
- No CSI driver install/changes.
- No storage class changes.
- No app PVC migrations off Longhorn.
- No change to the in-flight pvc-plumber v4 campaign (finish that first).

Revisit after the pvc-plumber migration campaign stabilizes.
