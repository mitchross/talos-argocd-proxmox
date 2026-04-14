# Homelab Storage Reference

This document answers a practical question:

> What is the simplest declarative, set-and-forget, low-brain storage and restore model for a homelab Kubernetes cluster?

It is written for two common setups:

- **One big Proxmox host** running multiple Talos/Kubernetes VMs
- **Three mini PCs** or other modest physical nodes

The goal is not generic storage theory. The goal is an end-to-end answer that covers:

- automatic provisioning
- backups
- restores
- safe rebuilds
- no UI-only workflows
- human-browsable file storage where it matters

## Executive Summary

For this repo's goals, the recommended pattern is:

1. **NFS/SMB for human-browsable named data**
   - AI models
   - media
   - exported files
   - anything users may want to inspect directly on the NAS
2. **Longhorn for opaque app-private PVC state**
   - internal app data that should restore correctly but does not need human browsing
3. **VolSync + Kopia for PVC backup/restore**
4. **pvc-plumber + Kyverno for conditional restore and fail-closed behavior**
5. **ArgoCD sync waves for bootstrap order**
6. **Prometheus + Alertmanager webhooks for operations**

If you want a single sentence:

> For modest homelab hardware, there is not currently a simpler declarative stack that preserves automatic provisioning, conditional restore, fail-closed behavior, named NAS storage where needed, and no manual restore ritual.

## The Three Data Classes

Do not treat all data as one problem.

### 1. Human-browsable file data

Use **NFS or SMB** with stable, obvious paths.

Examples:

- `comfyui`
- `llamacpp`
- `jellyfin`
- `paperless`
- model libraries
- media libraries

Why:

- people coming from Docker Compose expect to browse files directly
- recovery is easier when folder names are meaningful
- this avoids hiding user-owned content behind opaque CSI volume IDs

### 2. Opaque app-private state

Use **PVCs on a CSI block backend**.

Examples:

- Karakeep application state
- internal app data directories
- caches that matter to the app but do not need direct browsing

Why:

- apps get normal Kubernetes PVC behavior
- storage lifecycle is automated
- restore can be policy-driven

### 3. Databases

Use **database-native backup and restore** where possible.

Examples:

- CloudNativePG / Barman for Postgres

Why:

- filesystem-level backup is not the full recovery story for real databases
- point-in-time recovery and lineage management are database problems, not generic PVC problems

## Option Comparison

| Option | Declarative | Auto Provision | Conditional Restore at PVC Create | Fail-Closed | Named/Browsable Data | Good on 1 Proxmox Host | Good on 3 Mini PCs | Ops Simplicity | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| **Longhorn + NFS/SMB + VolSync/Kopia + pvc-plumber + Kyverno + Argo waves** | High | Yes | **Yes** | **Yes** | **Yes** | **Yes** | **Yes** | Medium | **Recommended default** |
| Longhorn built-in backups only | Medium | Yes | No practical automatic existence check | No | No | Yes | Yes | Medium | Incomplete for safe rebuilds |
| Longhorn + Velero | Medium | Yes | No | No | No | Yes | Yes | Medium | Good backup tool, not restore-intent layer |
| Longhorn + VolSync without pvc-plumber | High | Yes | No | No | No | Yes | Yes | Medium | Restore races and fresh-boot risk remain |
| OpenEBS LocalPV | Medium | Yes | No | No | No | Somewhat | Somewhat | Medium | Simple local storage, weak rebuild model |
| OpenEBS Mayastor | High | Yes | No native support | No native support | No | No | Yes, with real nodes/disks | Low-Medium | More demanding, not simpler |
| democratic-csi / TrueNAS CSI | High | Yes | No native support | No native support | Mixed | Yes | Yes | Low-Medium | Good NAS-centric backend, not a full solution |
| Proxmox CSI | High | Yes | No native support | No native support | No | **Yes** | N/A / maybe | Medium | Best backend alternative for single Proxmox host |
| Kasten K10 + storage backend | Policy-driven | Yes | Not this exact create-time pattern | Not this exact fail-closed pattern | No | Maybe | Maybe | High, if you accept product/UI model | Strong product, different workflow |

## Why the Recommended Pattern Wins

The following requirements are what make the answer non-trivial:

- plain declarative PVC creation
- automatic check for whether a backup exists
- restore if it exists, create empty if it does not
- deny if backup truth is unknown
- no UI restore ritual
- ability to rebuild often without accidentally bootstrapping fresh state over good backups

Most tools solve one or more of these:

- **Longhorn** solves provisioning, snapshots, backups, explicit restore
- **Velero** solves cluster backup/restore workflows
- **VolSync** solves data movement and asynchronous replication
- **democratic-csi / Proxmox CSI / OpenEBS** solve storage provisioning
- **Kasten K10** solves policy-driven enterprise backup/restore

What none of them cleanly solve out of the box is:

> When a PVC is created from Git, decide at admission time whether it should restore from backup or start fresh, and fail closed if that truth is unavailable.

That is the gap filled by `pvc-plumber`.

## Topology Recommendations

### Single Proxmox host with many VMs

**Recommended:**

- NFS/SMB for named data
- Longhorn for opaque app PVCs
- VolSync + Kopia for backup/restore
- pvc-plumber + Kyverno for restore intent
- Alertmanager for notifications

Why:

- the real physical failure domain is still the single Proxmox host
- Ceph does not buy meaningful HA in this topology
- Proxmox CSI is the only serious backend alternative if Longhorn becomes the pain point
- the restore-intent layer is still required no matter which block backend you choose

### Three mini PCs / modest physical nodes

**Recommended:**

- NFS/SMB for named data
- Longhorn for opaque app PVCs
- VolSync + Kopia
- pvc-plumber + Kyverno
- Alertmanager

Why:

- Longhorn is a practical fit for modest hardware
- Ceph is still heavier than most home users want
- democratic-csi is viable if you want a more NAS-centric model, but it still does not replace the restore gate

### Three stronger bare-metal nodes with dedicated disks and better network

At this point you may choose to reevaluate the block backend:

- Longhorn if operational simplicity still wins
- Ceph if you deliberately want a more enterprise-style distributed storage platform

Even here, the restore-intent problem does not disappear on its own.

## Backend Notes

### Longhorn

Strengths:

- strong Kubernetes integration
- snapshots, backups, recurring jobs, topology options
- workable on modest homelab hardware

Limitations:

- built-in restore still requires explicit backup selection
- `fromBackup` is declarative, but only if the exact backup URL is already known
- does not natively answer restore-or-empty at PVC creation time

### OpenEBS

Strengths:

- multiple engines for different use cases
- LocalPV is simple
- Mayastor is a serious replicated engine

Limitations:

- does not remove the need for a restore-intent layer
- Mayastor is not a simplicity win for modest homelab hardware

### democratic-csi / TrueNAS CSI

Strengths:

- excellent provisioning flexibility for TrueNAS/ZFS/NFS/iSCSI backends
- snapshots, clones, resizing
- strong fit if you are already deeply NAS-centric

Limitations:

- more node/server prep than many users expect
- still no native conditional restore primitive

### Proxmox CSI

Strengths:

- aligns well with a hypervisor-centric single-host setup
- PVs live on the Proxmox side rather than inside guest VM storage layers
- supports snapshots, topology, migration features

Limitations:

- still not a restore-intent engine
- best seen as a backend alternative, not as a full replacement for this repo's restore flow

### Kasten K10

Strengths:

- polished backup/restore platform
- policy-driven
- strong enterprise integrations

Limitations:

- different operating model than the plain-PVC GitOps flow used here
- does not eliminate the need for create-time restore intent if that is your hard requirement

## Alerts and Diagnostics

### Core operational requirement: Alertmanager webhooks

This is not optional for a low-brain setup.

Alert on at least:

- pvc-plumber readiness failures
- backup age too old
- VolSync job failures
- restore failures
- Longhorn degraded or faulted volumes
- backup target unreachable
- low free space on backup storage

Suggested receivers:

- Slack
- Discord
- ntfy
- email
- generic webhook receiver

### Optional diagnostic helper: K8sGPT

K8sGPT is useful for:

- cluster triage
- explaining broken PVC/pod/webhook states
- troubleshooting bad days faster

It is **not**:

- a storage platform
- a backup engine
- a restore orchestrator

Treat it as a troubleshooting assistant, not part of the storage control plane.

## What To Change Only If Necessary

If the current stack is working and drill results are good, keep it.

Reconsider the backend only if the backend is the actual pain.

### If Longhorn is the pain on a single Proxmox host

Evaluate **Proxmox CSI** as the first serious alternative.

### If you want stronger NAS-first provisioning

Evaluate **democratic-csi**.

### If you want productized enterprise backup/restore workflows more than plain-PVC GitOps restore intent

Evaluate **Kasten K10**.

## Bottom Line

For a homelab that wants:

- low-brain operations
- declarative workflows
- safe rebuilds
- no manual restore ritual
- named data where it makes sense
- opaque PVC restore where it makes sense

the current repo architecture is the recommended answer:

- **NFS/SMB for named data**
- **Longhorn for opaque app PVCs**
- **VolSync + Kopia for backup/restore**
- **pvc-plumber + Kyverno for conditional restore**
- **Argo sync waves for order**
- **Alertmanager for operational visibility**

That is not the smallest stack.

But today it is the best overall fit for the full problem being solved here.