# Homelab Storage Reference

This document answers a practical question:

> What is the simplest declarative, set-and-forget, low-brain storage and restore model for a homelab Kubernetes cluster?

For supporting ecosystem research on whether this problem is already solved elsewhere, see [Conditional PVC Restore Ecosystem Research](conditional-restore-ecosystem-research.md).

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

That sentence is true for the **full cluster rebuild happy path**.

It is **not** the same as saying this stack is tiny, effortless, or free of sharp edges. The rest of this document now calls those sharp edges out explicitly.

## What This Document Is And Is Not

This is a **reference architecture document** for the storage and restore model used in this repo.

It is **not** a claim that:

- every restore scenario is zero-touch
- every failure mode is already eliminated
- the implementation is safe if copied loosely without the exact guardrails used here

The correct framing is:

> This architecture gives the simplest known declarative answer to the full homelab problem **if** its operational guardrails are preserved.

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
| **Longhorn + NFS/SMB + VolSync/Kopia + pvc-plumber + Kyverno + Argo waves** | High | Yes | **Yes** | **Yes** | **Yes** | **Yes** | **Yes** | Medium *(see guardrails)* | **Recommended default** |
| Longhorn built-in backups only | Medium | Yes | No practical automatic existence check | No | No | Yes | Yes | Medium | Incomplete for safe rebuilds |
| Longhorn + Velero | Medium | Yes | No | No | No | Yes | Yes | Medium | Good backup tool, not restore-intent layer |
| Longhorn + VolSync without pvc-plumber | High | Yes | No | No | No | Yes | Yes | Medium | Restore races and fresh-boot risk remain |
| OpenEBS LocalPV | Medium | Yes | No | No | No | Somewhat | Somewhat | Medium | Simple local storage, weak rebuild model |
| OpenEBS Mayastor | High | Yes | No native support | No native support | No | No | Yes, with real nodes/disks | Low-Medium | More demanding, not simpler |
| democratic-csi / TrueNAS CSI | High | Yes | No native support | No native support | Mixed | Yes | Yes | Low-Medium | Good NAS-centric backend, not a full solution |
| Proxmox CSI | High | Yes | No native support | No native support | No | **Yes** | N/A / maybe | Medium | Best backend alternative for single Proxmox host |
| Kasten K10 + storage backend | Policy-driven | Yes | Not this exact create-time pattern | Not this exact fail-closed pattern | No | Maybe | Maybe | High, if you accept product/UI model | Strong product, different workflow |

**Important nuance on "Ops Simplicity":** the recommended stack is only "medium" complexity because this repo already encodes several hard-won guardrails. Rebuilding the same idea without those settings is not low-brain — it is fragile.

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

## Hard-Won Guardrails And Sharp Edges

This is the part generic comparison tables usually miss.

### 1. Kyverno generate rules are intentionally fire-and-forget

This repo does **not** run Kyverno generate rules in a fully reconciling mode.

The core policy uses:

- `mutateExistingOnPolicyUpdate: false`
- `background: false`
- `synchronize: false`

These are not stylistic preferences. They are operational guardrails.

Why they exist:

- `background: false` avoids continuous re-evaluation of every matching PVC
- `mutateExistingOnPolicyUpdate: false` avoids cluster-wide reprocessing on every policy edit
- `synchronize: false` avoids drift watchers generating massive `UpdateRequest` load as generated resources change status

These settings were chosen because the opposite behavior caused a real API-server overload incident in this repo's history.

Trade-off:

> If a generated `ReplicationSource`, `ReplicationDestination`, or `ExternalSecret` is deleted later, Kyverno will **not** automatically recreate it.

That means this architecture is low-brain only if monitoring catches drift and failures.

### 2. Sync waves are load-bearing infrastructure, not just nice ordering

The bootstrap story depends on ArgoCD sync waves **and** custom Lua health checks.

ArgoCD is explicitly configured to wait for health on:

- `argoproj.io/Application`
- `kyverno.io/ClusterPolicy`
- `volsync.backube/ReplicationSource`
- `volsync.backube/ReplicationDestination`

That means the restore guarantee is not just "Wave 2 before Wave 3" in theory. It depends on ArgoCD continuing to evaluate those custom health checks correctly.

If ArgoCD behavior changes, Lua health checks are removed, or health semantics drift, the wave guarantee can silently weaken.

### 3. Kyverno is part of the solution and part of the blast radius

Kyverno is not just another controller here. It is on the critical path for stateful workloads.

This repo already documents a real Kyverno webhook deadlock incident from `2026-04-08`.

As a result, the Kyverno deployment now includes infrastructure namespace exclusions for:

- `longhorn-system`
- `argocd`
- `volsync-system`
- `snapshot-controller`
- `external-secrets`
- `1passwordconnect`
- other early-wave infrastructure namespaces

There is also an emergency recovery script:

- `scripts/emergency-webhook-cleanup.sh`

Without those exclusions, a Kyverno crash-loop can block the very infrastructure needed to recover the cluster.

### 4. The NFS repository mount is injected by a separate Kyverno policy

The backup flow does **not** work from the main backup/restore policy alone.

VolSync mover Jobs rely on a second policy:

- `infrastructure/controllers/kyverno/policies/volsync-nfs-inject.yaml`

That policy injects:

- NFS volume `repository`
- mount path `/repository`

into every VolSync-created Job.

This is a good design because apps do not need per-workload NFS repo config. But it is also a hidden dependency: if this policy is removed or broken, backups fail even if the rest of the stack looks healthy.

The failure mode here is especially dangerous because it can be quiet:

- VolSync Jobs may still be created
- Kopia may not see the repository at `/repository`
- backup/restore behavior can fail in ways that are not obvious from the app manifest alone

That makes this policy part of the critical backup path, not a convenience add-on.

### 5. Fail-closed depends on `/readyz` being truly authoritative

The architecture only deserves the label **fail-closed** if `pvc-plumber` readiness actually proves:

- the service is reachable
- the repository mount is reachable
- the Kopia repository is readable and authoritative

If `/readyz` merely checks process liveness, the whole guarantee collapses:

- Kyverno passes the gate
- `/exists` can degrade into false-negative behavior
- the cluster may create empty PVCs over restorable state

In the current `pvc-plumber` codebase, `/readyz` is intentionally cheap:

- startup Kopia connect must have succeeded
- `os.Stat()` on the repository path must still succeed

The authoritative per-PVC safety check is `/exists/{namespace}/{pvc}`. It now returns:

- `decision=restore`, `authoritative=true`, HTTP 200 when a backup exists
- `decision=fresh`, `authoritative=true`, HTTP 200 when no backup exists
- `decision=unknown`, `authoritative=false`, HTTP 503 for backend/query/parse uncertainty

Operational note: the deployment here is pinned to `ghcr.io/mitchross/pvc-plumber:1.5.1`. If the published image ever drifts from the checked-in code, re-verify that `/exists` returns HTTP 503 for unknown backup truth before relying on the fail-closed claim.

### 6. The 5-minute cache TTL is a real trade-off

`pvc-plumber` is configured with a `5m` cache TTL.

That is a reasonable operational optimization, but it creates a subtle edge case:

- a backup can complete
- a PVC can be created shortly afterward
- the cache may still report the old answer briefly

For hourly or daily schedules this is usually acceptable, but it means the system is not perfectly instantaneous. During tightly timed backup-and-recreate workflows, this is worth remembering.

### 7. Single-host and single-backup-domain concentration still exist

For a single Proxmox host setup, the physical blast radius is still the hypervisor host.

And for the backup path, there is still concentration in the external NAS / TrueNAS domain hosting:

- the Kopia repository
- NFS/SMB shares
- potentially other storage roles

This architecture is still a strong homelab answer, but it is not immunity from storage concentration.

Recommended next step if data matters:

- second Kopia copy to object storage
- remote ZFS replication
- offsite backup target
- or another durability domain outside the primary NAS

### 8. Full rebuild restore is automatic; targeted restore is not

For the primary design goal — **full GitOps rebuild after cluster loss** — the flow is zero-touch.

That does **not** mean every restore operation is automatic.

Examples that still require manual action:

- restore a single PVC to a specific historical point
- investigate corruption and choose a restore point intentionally
- re-run or adjust a failed restore outside the standard create-time path

So the correct claim is:

> No UI restore ritual is required for the full rebuild path.

Not:

> Every restore scenario is fully automatic.

### 9. Alerting is partly implemented and partly still your job

This repo already contains real Prometheus alert rules for:

- Longhorn backup/storage health
- VolSync controller, backup, restore, and maintenance health

Examples:

- `monitoring/prometheus-stack/longhorn-backup-alerts.yaml`
- `monitoring/prometheus-stack/volsync-alerts.yaml`

So alerting is **not** purely aspirational.

However, two caveats matter:

1. `pvc-plumber`-specific alerts are not yet first-class in the same way
2. Alertmanager receivers still need real delivery plumbing

The current Alertmanager config routes to a placeholder/local webhook by default. That means the rules exist, but low-brain operations still require you to connect them to something real:

- Slack
- Discord
- ntfy
- email
- a real webhook receiver

Without that last mile, you still have monitoring, but not reliable notification.

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

Additional caution:

- if the same NAS/TrueNAS domain also holds the backup repository, you still need a second copy elsewhere for meaningful disaster separation

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

And it is not "no brain" because the components are magically simple.

It is "low brain" only because this repo has already encoded the hard parts:

- sync-wave ordering
- custom Argo health checks
- Kyverno webhook exclusions
- fire-and-forget generate guardrails
- NFS injection policy
- emergency webhook cleanup path
- Prometheus alert rules for storage/backup failures

But today it is still the best overall fit for the full problem being solved here.
