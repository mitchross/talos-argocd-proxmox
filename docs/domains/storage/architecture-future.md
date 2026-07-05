# Future idea — tiered storage (not implemented)

!!! warning "Status: idea only"
    Nothing here is built. No storage class, PVC, or CSI driver should change
    based on this doc. Today's model is unchanged: Longhorn (V1) is the default
    CSI and backups are [kopiur → Kopia → S3](kopiur-backup-architecture.md),
    declared per-PVC. See [storage architecture](../../storage-architecture.md).

## The idea

Split storage responsibilities so most apps stop depending on distributed block
storage just to run:

- **CSI layer** — provisions and mounts live volumes, nothing else.
- **Backup layer (kopiur)** — owns DR via restore-before-bind (`dataSourceRef → Restore`).

Because those are independent, "local storage" does **not** mean "no DR" — a plain
local volume still restores from S3 through the backup layer.

## Proposed tiers

| Tier | Storage | For |
|------|---------|-----|
| **1 — default** | local CSI (OpenEBS/ZFS LocalPV) + kopiur restore-based DR | most non-DB apps |
| **2 — replicated** | Longhorn replicated | only apps needing live failover (a few config/state PVCs) |
| **3 — database** | native (CNPG → Barman → S3) | never generic CSI snapshot/restore |

Tier 1 trade-off: if the node hosting a local volume dies, that app is down until
the PVC is recreated and restored. For most homelab apps that's acceptable, and the
failure mode is simple and explicit instead of distributed-storage churn.

## If this is ever revisited

Classify each PVC by whether it needs live HA, is restore-from-backup-OK, is
disposable, or is database-native, then define storage classes by intent. One real
design item: kopiur's `copyMethod: Snapshot` assumes Longhorn snapshots, so a
non-snapshotting local CSI would need a different mover strategy.
