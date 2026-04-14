# The Missing Primitive: Conditional PVC Restore for Zero-Touch GitOps Disaster Recovery

*How a 500-line Go microservice fills a gap that Velero, VolSync, Longhorn, and Kasten K10 all leave open*

---

## The Problem Nobody Talks About

Take a concrete example: Karakeep's `data-pvc` comes back during a rebuild.

There are only three acceptable outcomes:

1. a backup exists → restore from it
2. no backup exists because this is the first deploy → create empty
3. the platform cannot tell whether a backup exists → deny the PVC and stop the app from booting into empty state

That sounds obvious. Kubernetes still doesn't have a native primitive for it.

If you run stateful workloads on Kubernetes with GitOps, you've hit this wall in some form. A Helm upgrade goes sideways. A Kustomize merge drops a PVC from the resource list. You nuke a namespace to start fresh. You upgrade Talos and rebuild the cluster. ArgoCD syncs your manifests. PVCs get created. Pods bind to empty volumes. Your data is gone.

This article is about the **full rebuild path**: a cluster comes back from Git and stateful apps restore automatically if backups exist. It is **not** a claim that every targeted point-in-time restore is zero-touch.

The obvious answer is "just use a backup tool." But here's the thing — every backup tool in the Kubernetes ecosystem makes the same assumption: **a human will decide when to restore.**

Velero needs `velero restore create`. Kasten K10 needs a RestoreAction. Longhorn needs you to pick a backup and trigger the restore — via UI, CLI, or CRD, but always an explicit human decision. Even VolSync, which gets closest to declarative restore via its Volume Populator integration, will hang indefinitely if you set a `dataSourceRef` pointing to a backup that doesn't exist yet — because you're deploying the app for the first time.

None of them answer the question that GitOps actually needs answered:

> At PVC creation time, does a backup exist for this volume? If yes, restore from it. If no, provision empty. If we can't tell, don't provision at all.

Kubernetes has restore plumbing, but not a native conditional restore primitive. There's no `spec.dataSourceRef.conditionalRestore`. There's no admission-time backup oracle. VolumePopulators, which just graduated to GA in Kubernetes 1.33, provide the plumbing — "populate this PVC from that source" — but have zero decision-making capability. If the source doesn't exist, the PVC hangs in Pending forever.

So I built one.

## Evidence This Gap Is Real

Before diving into the solution, let me show you I'm not solving an imaginary problem.

**Longhorn Issue #6748** — In September 2023, a user named astranero opened an issue requesting exactly this: *"I want that before longhorn creates a new PV it checks backups for PV that has a name and namespace of this PVC that I am creating and then restores this PV binding it with new PVC."* The issue was closed as invalid. No implementation.

**VolSync Issue #627** — When GitOps applies a ReplicationSource to a fresh cluster, VolSync immediately tries to back up the empty data, potentially overwriting the good backup you're about to need. The community works around this with manual triggers and careful ordering.

**The Kubernetes Data Protection Working Group white paper** discusses VolumePopulators as the mechanism for restore but never mentions conditional restore, fail-closed gating, or admission-time backup checking. Every restore workflow described is user-initiated.

**The home-operations community** — the largest GitOps homelab community (~9,000 members on Discord, centered around the [onedr0p/cluster-template](https://github.com/onedr0p/cluster-template)) — uses VolSync with `dataSourceRef` always set on PVCs. On cluster rebuild, VolSync populates from the latest snapshot and apps come online. It works for rebuilds. But deploy a brand-new app with no backup history, and the PVC hangs forever. Their workaround: be careful. Don't deploy new apps during a rebuild. Accept the limitation.

I didn't want to accept the limitation.

## What I Actually Built

The solution is embarrassingly thin: a ~500-line Go microservice called [pvc-plumber](https://github.com/mitchross/pvc-plumber) and ~200 lines of Kyverno policy YAML. Zero custom CRDs.

Here's the entire flow:

```
Developer adds to Git:
  PVC with label: backup: "hourly"

ArgoCD syncs the PVC manifest
  ↓
Kyverno intercepts the CREATE via admission webhook
  ↓
Rule 0: GET http://pvc-plumber/readyz
  → If unreachable → DENY PVC creation (fail-closed)
  ↓
Rule 1: GET http://pvc-plumber/exists/{namespace}/{pvc-name}
  → Backup exists?
    Yes → Kyverno injects dataSourceRef → VolSync restores from backup
    No  → No mutation → PVC provisions empty → app starts fresh
  ↓
Rules 2-4: Kyverno generates backup infrastructure:
  → ExternalSecret (Kopia credentials from 1Password)
  → ReplicationSource (backup schedule: hourly or daily)
  → ReplicationDestination (restore target)
```

That's it. The app developer writes one label. Everything else is automatic.

Everything below pvc-plumber is off-the-shelf: VolSync handles data movement, Kopia handles deduplication and encryption, Longhorn handles block storage and snapshots, and ArgoCD handles sync ordering. I didn't build a backup engine. I built a decision layer that answers one boolean question.

## The Fail-Closed Design

Here's the part I'm actually proud of.

Most backup systems fail open. If the backup infrastructure is down during a rebuild, apps deploy with empty volumes. Nobody notices until someone asks "where's my data?" — usually at 3am during an incident that's already bad enough.

This system fails closed. If pvc-plumber is unreachable, Kyverno **denies PVC creation entirely**. The app doesn't deploy. ArgoCD shows it as degraded and retries with exponential backoff. You notice immediately because half your apps are in a retry loop instead of silently running with empty data.

```yaml
# Kyverno validation rule — if pvc-plumber is down, PVC creation is denied
context:
  - name: plumberHealth
    apiCall:
      method: GET
      service:
        url: "http://pvc-plumber.volsync-system.svc.cluster.local/readyz"
validate:
  deny:
    conditions:
      all:
        - key: "{{ plumberHealth || 'unavailable' }}"
          operator: Equals
          value: "unavailable"
```

The logic is simple: during a disaster recovery rebuild, if we can't verify whether a backup exists, we refuse to provision the volume. It's better to have an app that won't start than an app that starts with empty data.

In the current pvc-plumber implementation, `/readyz` is not just process liveness: it `stat`s the repository path and runs `kopia repository status --json` before returning healthy. That detail matters. A fake readiness probe would turn "fail-closed" into "silently provision empty volumes when the backup system is down," which defeats the whole point.

This required a deliberate architectural choice. The cluster bootstraps in strict sync wave order:

| Wave | Component | Why This Order |
|------|-----------|----------------|
| 0 | Cilium, ArgoCD, 1Password, External Secrets | Networking, GitOps, secrets foundation |
| 1 | Longhorn, Snapshot Controller, VolSync | Storage and backup engine |
| 2 | **pvc-plumber** | **Backup oracle must be healthy before any PVC decisions** |
| 3 | Kyverno | Policy engine registers webhooks |
| 4-6 | Infrastructure, monitoring, apps | Everything that creates PVCs |

Custom Lua health checks in ArgoCD enforce that each wave reports Healthy before the next begins. By the time any app PVC hits the API server, pvc-plumber and Kyverno are guaranteed to be running.

## The Magic Label

What makes this practical is that the app developer's entire interaction with the backup system is one label:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: data-pvc
  namespace: karakeep
  labels:
    backup: "hourly"    # ← this is the entire backup configuration
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 10Gi
  storageClassName: longhorn
```

From that single label, Kyverno generates:

1. An **ExternalSecret** that pulls the Kopia repository password from 1Password
2. A **ReplicationSource** with the backup schedule (`0 * * * *` for hourly, `0 2 * * *` for daily) and retention policy (24 hourly, 7 daily, 4 weekly, 2 monthly)
3. A **ReplicationDestination** for restore capability
4. A separate Kyverno policy **injects the NFS mount** into every VolSync mover Job automatically — no per-app NFS configuration needed

Remove the label? A cleanup policy runs every 15 minutes and deletes the orphaned resources.

Compare this to the community standard: manually defining a ReplicationSource, ReplicationDestination, and ExternalSecret per app — three extra YAML files per PVC, each with namespace-specific configuration. At 40+ apps, that's 120+ files of backup boilerplate eliminated.

## Why Not Just Use X?

A Git commit should fully describe the desired state of the cluster, including whether a PVC should be restored from backup or created fresh. No manual `kubectl` commands. No out-of-band orchestration script.

That's the constraint. Here's why everything else fails against it:

**Velero** — Restores are imperative CLI operations (`velero restore create`). You can schedule backups declaratively, but the restore decision requires a human. A fully rebuilt cluster from Git doesn't know it needs to restore anything.

**VolSync alone** — VolSync's Volume Populator integration hangs indefinitely if the ReplicationDestination has no snapshot yet. First deploy of any new app = infinite pending PVC. This is by design — VolSync handles data movement, not decision-making. As I'd put it to the VolSync maintainers: "VolSync is excellent. Our admission controller adds the decision layer that VolSync intentionally doesn't provide." They're complementary, not competing.

**Init Containers** — "Just add an init container that checks for a backup." This works if you control every workload definition. I run 40+ apps, many from upstream Helm charts I don't maintain. Modifying every chart to add restore logic is a maintenance nightmare. Init containers also can't fail-closed — if the init container crashes or can't reach the backup system, the pod starts with an empty volume. Silent data loss. The admission webhook approach is transparent to the application *and* denies creation on unknown state.

**Longhorn built-in** — Longhorn has backup to S3/NFS with restore via UI, CLI, or CRD. But restore still requires knowing *which backup* to restore and triggering it explicitly. There's no mechanism that says "when this PVC is created, automatically check if a backup exists and restore from it." A blogger named Merox [documented restoring 6 apps from Longhorn backups](https://merox.dev/blog/longhorn-backup-restore/) after rebuilding with Flux. It worked. It took hours. Per volume. One at a time.

**CSI Snapshots / VolumePopulators** — You can create a PVC from a VolumeSnapshot declaratively via `dataSourceRef`. But you need to know the snapshot name in advance (breaks GitOps), and it fails immediately if no snapshot exists (breaks first deploy). VolumePopulators provide the plumbing but not the conditional logic.

**Custom Operator** — The architecturally "correct" long-term answer. A single reconciliation loop that manages PVC lifecycle, backup scheduling, and conditional restore with continuous reconciliation. Also 10x the development effort for what is fundamentally a boolean decision. Kyverno + pvc-plumber is ~700 lines total. A proper operator with CRDs, RBAC, leader election, and reconciliation logic is a multi-month project. At ~40 PVCs with staggered backup schedules, the Kyverno fire-and-forget trade-off is acceptable. At 500+ PVCs, the operator becomes necessary. I'm honest about where that line is.

**Commercial tools (Portworx, Kasten K10, Trilio)** — Strong products, different operating model, and they cost more than the entire homelab. None of them implement this exact create-time conditional restore pattern in a declarative GitOps flow anyway.

## The Storage Architecture

Three classes of data, three storage approaches:

**Human-browsable data** — AI models, media libraries, exported files — lives on **NFS/SMB** with stable, obvious paths on a TrueNAS NAS. People coming from Docker Compose expect to browse files directly. Recovery is easier when folder names are meaningful.

**Opaque app-private state** — internal app data that should restore correctly but doesn't need human browsing — lives on **Longhorn PVCs** with Kyverno-managed backup.

**Databases** — CloudNativePG with Barman to S3. Filesystem-level snapshots of a running Postgres database are inconsistent without the WAL stream. Database backup is a database problem, not a PVC problem. Excluded from this system entirely.

Backup data goes to a separate TrueNAS appliance over NFS, into a single shared Kopia repository with content-defined chunking. All PVCs share the same repository, so Kopia deduplicates across applications. Delete an app and redeploy it? Kopia finds all the chunks already exist — near-instant backup, almost zero new storage.

## The Hard-Won Guardrails

This is the part that generic architecture diagrams always skip. These guardrails exist because I hit the failure modes they prevent.

### Kyverno fire-and-forget

The backup policy runs with `background: false`, `synchronize: false`, and `mutateExistingOnPolicyUpdate: false`. These sound like they reduce functionality. They do. Here's why:

- `background: true` causes Kyverno to re-evaluate every matching PVC every ~30 seconds, generating hundreds of UpdateRequests that hammer the API server. With 70+ workloads, this caused an API server overload that lasted 23 hours.
- `synchronize: true` makes Kyverno watch every generated resource for drift. With ~114 generated resources, controllers updating their status fields generate hundreds of thousands of API calls per cycle.
- `mutateExistingOnPolicyUpdate: true` re-evaluates every matching resource cluster-wide when the policy YAML changes — even a comment edit.

The trade-off: if a generated ReplicationSource is accidentally deleted, Kyverno won't recreate it. Backups stop silently until someone toggles the PVC label. A proper operator would reconcile. I accept this at ~40 PVCs because VolSync metrics in Prometheus catch it.

### Kyverno webhook blast radius

On 2026-04-08, a Renovate auto-merge of a kube-prometheus-stack chart upgrade restarted too many pods simultaneously. Kyverno's admission controller crashed with a cache sync failure. Its webhook was still registered with `failurePolicy: Fail`. Every Deployment, StatefulSet, and DaemonSet creation was rejected. Longhorn couldn't restart. ArgoCD couldn't mount PVCs. Full cluster deadlock. Even rebooting all nodes didn't fix it because webhook configs survive in etcd.

The fix: infrastructure namespaces (longhorn-system, argocd, volsync-system) are now excluded from Kyverno's webhook `namespaceSelector`. A [one-line emergency script](https://github.com/mitchross/talos-argocd-proxmox/blob/main/scripts/emergency-webhook-cleanup.sh) deletes all webhook configurations if it happens again. Kyverno recreates them when healthy.

### Backup timing safeguards

Two preconditions prevent bad backup behavior:

1. ReplicationSource is only generated after the PVC is `Bound` — prevents backing up during an active restore (when the PVC is Pending)
2. ReplicationSource requires the PVC to be at least 2 hours old — prevents backing up empty data immediately after a fresh provision or restore

Without these, a freshly restored PVC could immediately trigger a backup of its still-populating state, overwriting the good backup. This is the same problem VolSync Issue #627 describes, solved at the policy layer.

## What The Community Actually Does

I spent time researching what the broader homelab and Kubernetes community actually does for PVC backup and restore. Three patterns show up repeatedly.

**1. The home-operations pattern:** VolSync + Kopia, usually with Flux, often with `dataSourceRef` always set on restoreable PVCs. This is the most sophisticated public homelab pattern I found. It works well for cluster rebuilds, but it still assumes the restore source exists. New apps with no backup history hang. There is no admission-time "restore if present, create empty if not" decision.

**2. The Longhorn-native pattern:** Longhorn handles snapshots and backups to S3/MinIO/NFS, GitOps brings the manifests back, and a human restores the volumes explicitly via UI, CLI, or CRDs. It is a valid DR workflow. It is not zero-touch conditional restore.

**3. The NAS-first pattern:** important data lives outside Kubernetes on NFS/SMB/ZFS datasets. Rebuild the cluster, re-mount the shares, and move on. This is simple and often smart, but it sidesteps the PVC restore-intent problem rather than solving it.

I could not find a widely adopted community pattern for **admission-time conditional restore** or **fail-closed PVC gating**. The gap is real. Most people either accept explicit restore steps, push state outside Kubernetes, or rely on scripts and careful sequencing.

## The Trade-Offs I Accept

**Single backup domain.** TrueNAS hosts NFS shares, S3 storage, and the Kopia backup repository. That's concentration, not 3-2-1. A second Kopia target to cloud S3 or remote ZFS replication is the right next step.

**Database temporal drift.** CNPG databases use Barman to S3 with WAL-based PITR on independent schedules. Applications using both database and filesystem state will experience temporal drift on restore. Reconciliation on startup is the app's responsibility.

**Targeted restore is still manual.** The full rebuild path is zero-touch. A single-PVC point-in-time restore is not. You still need an explicit VolSync or Longhorn restore action if you want to rewind one workload to a chosen recovery point.

**Sync wave fragility.** The bootstrap guarantee depends on ArgoCD sync waves and custom Lua health checks. If ArgoCD behavior changes or health check semantics drift, the wave guarantee can silently weaken. This is load-bearing infrastructure, not cosmetic ordering.

**Cache TTL.** pvc-plumber has a 5-minute cache TTL. A backup can complete and a PVC can be created shortly after, but the cache may still report the old answer. For hourly or daily schedules this is usually irrelevant. For tightly-timed backup-and-recreate workflows, it's worth knowing.

## Where This Should Go

This is a stopgap. The right long-term answer is a native Kubernetes primitive.

The most natural path is a **conditional VolumePopulator** — a controller that implements the VolumePopulator contract with conditional logic built in. The PVC references a custom resource via `dataSourceRef`, the populator checks for backup existence, restores if found, provisions empty if not. No admission webhook needed. No external HTTP calls during PVC creation.

VolumePopulators graduated to GA in Kubernetes 1.33. The plumbing exists. What's missing is the decision logic. pvc-plumber is a proof-of-concept for functionality that CSI provisioners or backup operators should adopt natively.

If you're running GitOps with stateful workloads and you've ever had to explain to someone why their app came up empty after a cluster rebuild, this problem is real. The ecosystem will solve it eventually. In the meantime, [pvc-plumber](https://github.com/mitchross/pvc-plumber) is a thin decision layer on top of standard storage and backup tooling.

---

*If you're thinking "why didn't you just use X," you're asking the right question. The answer is almost always: "X solves backup, but not the conditional restore decision at PVC creation time in a fully declarative GitOps pipeline." We didn't build a backup tool. We built a 500-line Go microservice that answers one question: "Is there a backup for this PVC?" Everything else is off-the-shelf components doing what they're good at. You're right that eight components to answer one question is excessive. The ideal solution is a native Kubernetes API field — something like `spec.dataSourceRef.conditionalRestore` — that CSI provisioners could implement. Until that exists upstream, we're composing primitives to bridge the gap.*
