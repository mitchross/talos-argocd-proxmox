# Backup & Restore Architecture

A zero-touch, fully automated backup and restore system for Kubernetes persistent data.

## Overview

This cluster automatically backs up application data to S3 and restores it when needed - without any manual intervention. Whether you're starting fresh, rebuilding from a disaster, or just re-adding an app you removed, the system handles everything.

### The Goal

```
Add a label to your PVC → Backups happen automatically → Restores happen automatically
```

That's it. No clicking buttons. No running restore commands. No editing configs.

### How It Works (Simple Version)

When you deploy an app with `backup: "hourly"` on its PVC:

1. **If no backup exists** → App starts with fresh/empty storage, backups begin automatically
2. **If backup exists in S3** → App automatically restores from the latest backup

The system figures out which scenario you're in and does the right thing.

---

## What Problems Does This Solve?

### Problem 1: "My cluster died, how do I restore?"

**Old way:** Manually restore each app's data from backups, one by one.

**This system:** Rebuild your cluster, deploy apps, data restores automatically.

### Problem 2: "I removed an app and want it back with my old data"

**Old way:** Hope you have backups, manually restore them.

**This system:** Re-add the app to ArgoCD, your old data comes back automatically.

### Problem 3: "I don't want to add backup boilerplate to every app"

**Old way:** Copy-paste 100+ lines of backup configuration for each app.

**This system:** Add one label: `backup: "hourly"`. Done.

---

## The User Experience

### For App Developers

Just add this label to your PVC:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: my-app-data
  labels:
    backup: "hourly"  # <-- This is all you need
spec:
  accessModes: ["ReadWriteOnce"]
  resources:
    requests:
      storage: 10Gi
```

Everything else is automatic:
- Backups run hourly to S3
- If you delete and re-add the app, data restores automatically
- If you rebuild the cluster, data restores automatically
- If it's a fresh install, the app starts with empty storage (as expected)

### What You Should NEVER Have To Do

- Click "restore" in any UI
- Run restore commands manually
- Edit configuration to switch between "fresh" and "restore" modes
- Remember which apps have backups
- Manually trigger backup jobs

---

## Scenarios

### Scenario 1: Fresh Cluster (First Time Setup)

You're setting up a brand new cluster with no previous data.

**What happens:**
1. You deploy your apps via ArgoCD
2. Each app with `backup: "hourly"` starts with empty storage
3. Backups begin automatically in the background
4. S3 now has your data for future restores

**Result:** Apps work normally, backups are set up for the future.

### Scenario 2: Cluster Rebuild (Disaster Recovery)

Your cluster died. You rebuild it from scratch.

**What happens:**
1. You bootstrap ArgoCD and infrastructure
2. The system discovers your existing backups in S3
3. When apps deploy, they automatically restore from S3
4. Your data is back without any manual steps

**Result:** Full recovery with zero manual intervention.

### Scenario 3: Add a New App

You add a new app to an existing cluster.

**What happens:**
- Same as Scenario 1 - no backup exists for this app yet
- Starts fresh, backups begin automatically

### Scenario 4: Remove and Re-add an App

You remove an app from ArgoCD (maybe to test, maybe by accident). A week later, you want it back.

**What happens:**
1. When you removed the app, the S3 backup remained (backups are external)
2. When you re-add the app, the system finds the old backup
3. Your data is automatically restored

**Result:** Your bookmarks, settings, data - all back automatically.

---

## Architecture

### Components

```
                                 ┌─────────────────┐
                                 │                 │
                                 │  S3 (External)  │  Backups live here
                                 │                 │  Survives cluster death
                                 │                 │
                                 └────────┬────────┘
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    │                     │                     │
                    │              KUBERNETES CLUSTER           │
                    │                     │                     │
                    │    ┌────────────────┼────────────────┐    │
                    │    │                │                │    │
                    │    │    ┌───────────▼───────────┐    │    │
                    │    │    │                       │    │    │
                    │    │    │       VOLSYNC         │    │    │
                    │    │    │                       │    │    │
                    │    │    │  ReplicationSource    │    │    │
                    │    │    │  (backs up to S3)     │    │    │
                    │    │    │                       │    │    │
                    │    │    │  ReplicationDestination    │    │
                    │    │    │  (restores from S3)   │    │    │
                    │    │    │                       │    │    │
                    │    │    └───────────┬───────────┘    │    │
                    │    │                │                │    │
                    │    │    ┌───────────▼───────────┐    │    │
                    │    │    │                       │    │    │
                    │    │    │       KYVERNO         │    │    │
                    │    │    │    (Policy Engine)    │    │    │
                    │    │    │                       │    │    │
                    │    │    │  - Auto-creates       │    │    │
                    │    │    │    backup resources   │    │    │
                    │    │    │  - Auto-configures    │    │    │
                    │    │    │    restore            │    │    │
                    │    │    │                       │    │    │
                    │    │    └───────────┬───────────┘    │    │
                    │    │                │                │    │
                    │    │    ┌───────────▼───────────┐    │    │
                    │    │    │                       │    │    │
                    │    │    │      LONGHORN         │    │    │
                    │    │    │   (Storage Driver)    │    │    │
                    │    │    │                       │    │    │
                    │    │    │  - Provisions PVCs    │    │    │
                    │    │    │  - Restores from      │    │    │
                    │    │    │    snapshots          │    │    │
                    │    │    │                       │    │    │
                    │    │    └───────────────────────┘    │    │
                    │    │                                 │    │
                    │    └─────────────────────────────────┘    │
                    │                                           │
                    └───────────────────────────────────────────┘
```

### How the Pieces Fit Together

| Component | Role |
|-----------|------|
| **S3 (RustFS)** | External storage for backups. Survives cluster rebuilds. |
| **VolSync** | Kubernetes operator that handles backup/restore via restic |
| **Kyverno** | Policy engine that auto-generates backup resources when it sees the `backup` label |
| **Longhorn** | Storage driver that provisions volumes and supports restoring from snapshots |
| **ArgoCD** | GitOps controller that deploys apps (not backup-specific, but orchestrates everything) |

---

## Why VolSync Instead of Longhorn Backup?

Longhorn has built-in backup to S3, but it requires clicking "Restore" in the Longhorn UI. That violates our "zero manual intervention" principle.

VolSync can be fully automated through Kubernetes resources - no UI clicks needed.

---

## Storage Requirements

The storage system must support:

1. **Pod migration** - Pods can move between nodes without losing data
2. **CSI Volume Populator** - Ability to restore from external snapshots
3. **No UI dependency** - All operations via Kubernetes resources

Currently using **Longhorn**. Alternatives like OpenEBS or Rook-Ceph could work if they meet these requirements.

---

## Technical Details

For the technical deep-dive including:
- The timing challenges with Kubernetes admission webhooks
- Detailed sequence diagrams for each scenario
- Problems encountered and solutions
- Implementation steps

See: [volsync-implementation-plan.md](./volsync-implementation-plan.md)

---

## FAQ

### Q: What if I don't want an app to be backed up?

Don't add the `backup` label to its PVC. Simple.

### Q: How often do backups run?

With `backup: "hourly"`, backups run every hour. You can also use `backup: "daily"`.

### Q: How much storage do backups use?

Backups use restic which does deduplication. Only changed blocks are stored after the first backup.

### Q: Can I restore to a specific point in time?

Not automatically. The system always restores from the latest backup. For point-in-time recovery, you'd need manual intervention.

### Q: What happens if S3 is unavailable during restore?

The PVC will be stuck pending until S3 is available. The system doesn't fall back to fresh storage automatically (that could cause data loss).

### Q: Is database data safe to backup this way?

For simple databases, yes. For production databases like PostgreSQL, you should use database-native backup tools (like pgBackRest) that ensure consistency. This system is best for:
- Application config files
- Media libraries
- Simple SQLite databases
- User uploads

---

## Current Implementation Status

| Component | Status |
|-----------|--------|
| VolSync Operator | Deployed |
| Longhorn Storage | Deployed |
| Kyverno Policies | Partially implemented (needs work) |
| Pre-warm CronJob | Not yet implemented |
| S3 Bucket | Configured |

See the [implementation plan](./volsync-implementation-plan.md) for next steps.
