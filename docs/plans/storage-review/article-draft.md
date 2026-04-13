# The Missing Primitive: Conditional PVC Restore in Declarative Kubernetes

## The Problem Nobody Talks About

If you run stateful workloads on Kubernetes with GitOps, you've hit this wall: what happens when you need to rebuild your cluster?

ArgoCD syncs your manifests. PVCs get created. Pods bind to empty volumes. Your data is gone.

The obvious answer is "just use a backup tool." But here's the thing — every backup tool in the Kubernetes ecosystem makes the same assumption: a human will trigger the restore. Velero needs `velero restore create`. Kasten needs you to bind a RestorePoint. Longhorn needs you to pick a backup and click restore. Even VolSync, which gets closest to declarative restore, will hang indefinitely if you set a `dataSourceRef` pointing to a backup that doesn't exist yet (because you're deploying the app for the first time).

None of them answer the question that GitOps actually needs answered:

**"At PVC creation time, does a backup exist? If yes, restore from it. If no, provision empty."**

That conditional logic doesn't exist anywhere in the Kubernetes API. There's no `spec.dataSourceRef.conditionalRestore`. There's no admission-time backup oracle. There's nothing.

So I built one.

## What I Actually Built

The solution is embarrassingly thin: a 500-line Go microservice called [pvc-plumber](https://github.com/mitchross/pvc-plumber) and ~200 lines of Kyverno policy YAML.

Here's the entire flow:

1. ArgoCD syncs a PVC with a `backup: "hourly"` label
2. Kyverno intercepts the PVC creation via admission webhook
3. Kyverno calls pvc-plumber: `GET /exists/{namespace}/{pvc-name}`
4. pvc-plumber checks the Kopia backup repository (sub-millisecond from in-memory cache)
5. If backup exists → Kyverno injects `dataSourceRef` → VolSync restores data from backup
6. If no backup → no mutation → PVC provisions empty → app starts fresh

That's it. Everything else is off-the-shelf: VolSync handles data movement, Kopia handles deduplication and encryption, Kyverno handles resource generation (ExternalSecrets, ReplicationSource, ReplicationDestination), and ArgoCD handles sync ordering.

I didn't build a backup engine. I built a decision layer that answers one boolean question.

## The Fail-Closed Design

Here's the part I'm actually proud of.

Most backup systems fail open. If the backup infrastructure is down, apps deploy with empty volumes. Nobody notices until someone asks "where's my data?" — usually at 3am during an incident that's already bad enough.

This system fails closed. If pvc-plumber is unreachable, Kyverno **denies PVC creation entirely**. The app doesn't deploy. ArgoCD shows it as degraded. You notice immediately.

The logic is simple: during a disaster recovery rebuild, if we can't verify whether a backup exists, we refuse to provision the volume. It's better to have an app that won't start than an app that starts with empty data and silently overwrites the backup you're about to need.

This required a deliberate architectural choice — pvc-plumber sits at Wave 2 in the ArgoCD sync order, before Kyverno (Wave 3), before any application (Wave 4-6). The backup oracle must be healthy before any stateful workload can deploy.

## The Storage Architecture

Primary storage runs on Longhorn (NVMe drives local to each Proxmox node). Backups go to a separate TrueNAS appliance over NFS. This is a deliberate 3-2-1 trade-off:

- **3 copies**: Longhorn primary + Longhorn replica + Kopia backup on TrueNAS
- **2 media types**: NVMe (Proxmox) + spinning rust (TrueNAS)
- **1 offsite**: Not yet (this is the honest gap)

I'm paying ~40% write amplification for Longhorn's replica=2, and I'm paying network overhead for NFS backups. In exchange, if a Proxmox node dies, Longhorn rebuilds from the surviving replica in minutes. If the entire cluster burns, TrueNAS has the backups and pvc-plumber orchestrates the restore.

All PVC backups share a single Kopia repository with content-defined chunking. Delete an app and redeploy it? Kopia finds all the chunks already exist — near-instant backup, almost zero new storage. This is better than per-PVC Restic repositories where every delete/recreate means a full re-backup.

## Why Not Just Use X?

A Git commit should fully describe the desired state of the cluster, including whether a PVC should be restored from backup or created fresh. No manual `kubectl` commands. No out-of-band orchestration script. That's the constraint. Here's why everything else fails against it:

**Velero** — Restores are imperative CLI operations (`velero restore create`). You can put the schedule in Git, but the actual restore is a manual decision. A fully rebuilt cluster doesn't know it needs to restore anything.

**VolSync alone** — VolSync's `dataSourceRef` hangs indefinitely if the ReplicationDestination has no snapshot yet. First deploy of any new app = infinite pending PVC. VolSync handles data movement perfectly — it just can't make the "restore or empty?" decision.

**Init Containers** — "Just add an init container that checks for a backup." This works if you control every workload definition. I run 40+ apps, many from upstream Helm charts I don't maintain. Modifying every chart to add restore logic is a maintenance nightmare. The admission webhook approach is transparent — Helm charts don't know backups exist.

**CSI Snapshots** — You can create a PVC from a VolumeSnapshot declaratively. But you need to know the snapshot name in advance (breaks GitOps), and it fails if no snapshot exists (first deploy).

**Custom Operator** — The architecturally "correct" answer. A single reconciliation loop that manages PVC lifecycle, backup scheduling, and conditional restore. Also 10x the development effort for what is fundamentally a boolean decision problem. Kyverno + pvc-plumber is ~700 lines total. A proper operator with CRDs, RBAC, leader election, and reconciliation logic is a multi-month project for a team of one.

## What I Got Wrong (And Fixed)

I subjected this architecture to independent reviews from four LLMs acting as principal cloud architects. They found three implementation gaps:

**1. The readiness probe was lying.** `/readyz` returned 200 OK regardless of whether the Kopia repository was actually accessible. If TrueNAS went down, pvc-plumber would stay "Ready" but silently degrade to `exists: false` for every query — provisioning empty PVCs over lost backups. The fail-closed gate was an illusion.

**Fixed:** `/readyz` now performs an active health check — stats the NFS mount path and runs `kopia repository status`. If either fails, the probe returns 503, Kubernetes marks the pod NotReady, and the fail-closed gate becomes real.

**2. Single point of failure.** One pvc-plumber pod on one node. Node dies during DR = all stateful deployments blocked with no path to recovery except waiting for the node to come back.

**Fixed:** Two replicas with pod anti-affinity (forced to different nodes) and a PodDisruptionBudget preventing simultaneous eviction.

**3. Concurrent NFS access to shared Kopia repository.** Multiple VolSync backup jobs writing to the same repository simultaneously over NFS is outside Kopia's documented safe concurrency model. During a full-cluster restore with 40+ simultaneous operations, this is a corruption risk.

**Status:** Under evaluation. Options are deploying a Kopia Repository Server (serializes access via gRPC) or moving the backup repository to S3-compatible object storage. The current system works under normal staggered backup schedules; the risk manifests only during mass concurrent operations.

## The Trade-Offs I Accept

**Kyverno is fire-and-forget.** I run Kyverno with `background: false` and `synchronize: false` (required to avoid API server overload at scale). This means if a generated ReplicationSource is accidentally deleted, Kyverno won't recreate it. Backups stop silently until someone notices or toggles the PVC label. A proper operator would reconcile continuously. I accept this because the probability of silent backup loss at ~40 PVCs is low enough to monitor via Prometheus alerts rather than building a full controller.

**Database backups are separate.** CloudNativePG databases use Barman to S3 with WAL-based PITR. They're excluded from the PVC backup system entirely because filesystem snapshots of a running Postgres database are inconsistent without the WAL stream. This means filesystem restore timestamps and database restore timestamps can drift — applications using both must handle reconciliation on startup.

**Thundering herd during full DR is unthrottled.** A complete cluster rebuild triggers 40+ concurrent VolSync restore jobs. ArgoCD sync waves stagger deployment (infrastructure before apps), but within the application wave, everything hits simultaneously. TrueNAS has a 10Gbps link and 256 NFS threads configured, but I haven't measured worst-case RTO under full concurrent load.

## Measured Results

Single-namespace restore drill (delete namespace, ArgoCD re-syncs):
- PVC creation to pod Running: **47 seconds** (3Gi PVC with ~1.2Gi of data)
- Kyverno mutation + VolSync restore is the bulk of the time
- pvc-plumber cache hit: <1ms

RPO:
- Hourly backups: **maximum 59 minutes of data loss**
- Daily backups: **maximum 24 hours of data loss**

## Where This Should Go

This is a stopgap. The right long-term answer is a native Kubernetes primitive — something like a conditional VolumePopulator that checks for backup existence at provisioning time without requiring an admission webhook.

The Kubernetes VolumePopulator mechanism (`dataSourceRef` pointing to any custom resource) is the upstream path. A controller that implements the VolumePopulator contract with conditional logic built in would eliminate the need for admission webhooks entirely. Until that's mature and widely supported by CSI drivers, composing Kyverno + a thin microservice is the pragmatic bridge.

If you're running GitOps with stateful workloads and you've ever had to explain to someone why their app came up empty after a cluster rebuild, this problem is real. The ecosystem will solve it eventually. In the meantime, [pvc-plumber](https://github.com/mitchross/pvc-plumber) is 500 lines of Go that answers one question: "Is there a backup for this PVC?"

Everything else is off-the-shelf components doing what they're good at.

---

*If you're thinking "why didn't you just use X," you're asking the right question. The answer is almost always: "X solves backup, but not the conditional restore decision at PVC creation time in a fully declarative GitOps pipeline." Eight components to answer one boolean question is excessive. The ideal solution is a native Kubernetes API field that CSI provisioners could implement. Until that exists upstream, we're composing primitives to bridge the gap.*
