# Future idea: tiered storage (not implemented)

!!! warning "Status: idea only"
    Nothing here is built. Do not change any storage class, PVC, or CSI driver
    based on this doc. Today's model is unchanged: Longhorn (V1) is the default
    CSI and backups are [kopiur → Kopia → S3](kopiur-backup-architecture.md),
    declared per-PVC. See [storage architecture](../../storage-architecture.md).

## The idea

Split storage responsibilities so most apps stop depending on distributed block
storage just to run:

- The CSI layer provisions and mounts live volumes, nothing else.
- The backup layer (kopiur) owns DR through restore-before-bind (`dataSourceRef → Restore`).

Because those are independent, "local storage" does **not** mean "no DR". A plain
local volume still restores from S3 through the backup layer.

## Proposed tiers

| Tier | Storage | For |
|------|---------|-----|
| **1, default** | local CSI (OpenEBS/ZFS LocalPV) + kopiur restore-based DR | most non-DB apps |
| **2, replicated** | Longhorn replicated | only apps needing live failover (a few config/state PVCs) |
| **3, database** | plain Postgres + kopiur daily/6-hourly schedule | crash-consistent snapshot + WAL recovery |

Tier 1 trade-off: if the node hosting a local volume dies, that app is down until
the PVC is recreated and restored. Most homelab apps can accept that. The failure
mode is simple and explicit, unlike distributed-storage churn.

## If this is ever revisited

Classify each PVC as needing live HA, restorable from backup, disposable, or
database-native. Then define storage classes by intent. One real design item:
kopiur's `copyMethod: Snapshot` assumes Longhorn snapshots, so a
non-snapshotting local CSI would need a different mover strategy.
