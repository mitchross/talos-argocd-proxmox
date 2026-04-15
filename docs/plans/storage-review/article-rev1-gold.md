# The Missing Primitive: Conditional PVC Restore for Zero-Touch GitOps Disaster Recovery

*A 500-line Go microservice that answers one question: "Is there a backup for this PVC?"*

---

## The Problem

I run 40+ stateful apps on Kubernetes with ArgoCD. I nuke namespaces regularly. I Helm-upgrade things wrong. I rebuild the cluster after Talos upgrades. Every time, ArgoCD syncs my manifests, PVCs get created, and pods bind to empty volumes.

The application state is effectively lost unless I intervene manually.

Every backup tool in the ecosystem — Velero, VolSync, Longhorn, Kasten K10 — can back up a PVC. They can also restore one. But none of them answer the question that a GitOps rebuild actually needs answered:

> When this PVC is created from Git, does a backup exist?  
> If yes → restore from it.  
> If no → create empty.  
> If we can't tell → **don't create it at all.**

That third outcome is the one I could not find implemented in any public GitOps PVC workflow. And it's the one that matters most during a disaster recovery rebuild — when the backup system might be coming up alongside everything else.

## Fail-Open vs Fail-Closed

These terms get thrown around loosely. Here's what they mean concretely for PVC provisioning:

```
┌─────────────────────────────────────────────────────────────┐
│                      FAIL-OPEN                              │
│                                                             │
│  PVC Created ──→ Can we reach backups?                      │
│                      │                                      │
│                  Yes │        No                            │
│                      │         │                            │
│               Restore from     └──→ Create empty PVC        │
│               backup                App boots with          │
│                                     NO DATA                 │
│                                     Nobody notices          │
│                                     until it's too late     │
│                                                             │
│  This is the common failure mode when restore happens       │
│  after PVC creation instead of before it.                   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                      FAIL-CLOSED                            │
│                                                             │
│  PVC Created ──→ Can we reach backups?                      │
│                      │                                      │
│                  Yes │        No                            │
│                      │         │                            │
│               Does backup      └──→ DENY PVC creation       │
│               exist?                App doesn't deploy      │
│                │                    ArgoCD retries with     │
│            Yes │    No              exponential backoff     │
│                │     │              You notice immediately  │
│         Restore  Create                                     │
│         from     empty                                      │
│         backup   PVC                                        │
│                                                             │
│  This is what pvc-plumber does.                             │
└─────────────────────────────────────────────────────────────┘
```

Fail-open is dangerous because it's silent. Your app comes up, looks healthy, passes readiness probes — but it's running on empty data. You might not discover this for hours or days. By then, the next scheduled backup may have overwritten your good backup with the empty state.

Fail-closed is noisy on purpose. Half your apps stuck in a retry loop is impossible to miss. And it's self-healing: once the backup system comes up, Kyverno re-evaluates, PVCs get created with the correct restore decision, and everything converges.

## Why I Needed pvc-plumber

Kubernetes has mature tools for every piece of the backup story — except the decision.

```
 Backup:    VolSync + Kopia  ✓  (scheduled, incremental, deduplicated)
 Storage:   Longhorn         ✓  (CSI snapshots, replicated block storage)
 Secrets:   External Secrets ✓  (1Password → K8s Secret)
 Ordering:  ArgoCD waves     ✓  (infrastructure before apps)
 Restore:   VolumePopulator  ✓  (populate PVC from snapshot before bind)

 Decision:  ???              ✗  "Should this PVC restore or start empty?"
```

That missing decision layer is pvc-plumber. It is not a backup engine. It is an admission-time intent resolver for PVC creation.

It is a ~500-line Go microservice with two endpoints:

- **`/readyz`** — Is the Kopia backup repository accessible? (stats the NFS mount, runs `kopia repository status`)
- **`/exists/{namespace}/{pvc-name}`** — Does a backup exist for this specific PVC? Returns `{"exists": true/false, "snapshots": N}`

That's the entire API. Kyverno calls it during PVC admission and uses the answer to decide what to do.

## End-to-End: Karakeep From Git to Running

Here's what actually happens when Karakeep deploys. This is a real app in my cluster — a bookmark manager with a web UI, Chrome for crawling, and Meilisearch for full-text search.

### Step 1: The YAML in Git

The only storage-related thing the app developer writes:

```yaml
# my-apps/media/karakeep/karakeep/pvc-data.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: data-pvc
  namespace: karakeep
  labels:
    app: karakeep
    backup: "hourly"          # ← the entire backup configuration
spec:
  accessModes:
  - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
  storageClassName: longhorn
  # dataSourceRef is added dynamically by Kyverno if a backup exists
```

No ReplicationSource. No ReplicationDestination. No ExternalSecret. No backup schedule configuration. One label.

### Step 2: ArgoCD Syncs

ArgoCD discovers `my-apps/media/karakeep/` via an ApplicationSet that scans for directories. No manual Application resource needed. Karakeep deploys at Wave 6 — after all infrastructure is healthy.

### Step 3: Kyverno Intercepts the PVC CREATE

```
                          PVC CREATE: data-pvc
                          namespace: karakeep
                          labels: backup=hourly
                                │
                                ▼
                    ┌───────────────────────┐
                    │  Kyverno Admission    │
                    │  Webhook              │
                    └───────────┬───────────┘
                                │
                    Rule 0: Readiness Gate
                                │
                                ▼
              GET http://pvc-plumber.volsync-system/readyz
                                │
                     ┌──────────┴──────────┐
                     │                     │
                 200 OK              Unreachable/503
                     │                     │
                     ▼                     ▼
              Continue             DENY PVC creation
              to Rule 1            (fail-closed)
                     │             ArgoCD retries
                     │             with backoff
                     │
                    Rule 1: Backup Check
                     │
                     ▼
    GET http://pvc-plumber.volsync-system/exists/karakeep/data-pvc
                     │
          ┌──────────┴──────────┐
          │                     │
    {"exists": true}      {"exists": false}
          │                     │
          ▼                     ▼
    Mutate PVC:           No mutation.
    Add dataSourceRef     PVC creates empty.
    pointing to           App starts fresh.
    ReplicationDest       (first deploy path)
          │
          ▼
    PVC waits for
    VolSync Volume
    Populator to fill
    it from backup
    before binding.
    (atomic restore)
          │
          ▼
    App starts with
    all data intact.
    (rebuild path)
```

### Step 4: Kyverno Generates Backup Infrastructure

On the same PVC CREATE event, three more Kyverno rules fire:

```yaml
# Generated: ExternalSecret (pulls Kopia password from 1Password)
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: volsync-data-pvc         # auto-named from PVC
  namespace: karakeep            # same namespace as PVC
spec:
  secretStoreRef:
    kind: ClusterSecretStore
    name: 1password
  data:
  - secretKey: KOPIA_PASSWORD
    remoteRef:
      key: rustfs
      property: kopia_password
```

```yaml
# Generated: ReplicationSource (backup schedule)
apiVersion: volsync.backube/v1alpha1
kind: ReplicationSource
metadata:
  name: data-pvc-backup
  namespace: karakeep
spec:
  sourcePVC: data-pvc
  trigger:
    schedule: "0 * * * *"         # hourly (from label value)
  kopia:
    repository: volsync-data-pvc
    compression: zstd-fastest
    copyMethod: Snapshot           # Longhorn CSI snapshot, app keeps running
    storageClassName: longhorn
    volumeSnapshotClassName: longhorn-snapclass
    retain:
      hourly: 24
      daily: 7
      weekly: 4
      monthly: 2
```

```yaml
# Generated: ReplicationDestination (restore target)
apiVersion: volsync.backube/v1alpha1
kind: ReplicationDestination
metadata:
  name: data-pvc-backup
  namespace: karakeep
spec:
  trigger:
    manual: restore-once
  kopia:
    repository: volsync-data-pvc
    copyMethod: Snapshot
    storageClassName: longhorn
    accessModes: ["ReadWriteOnce"]
    capacity: "10Gi"
```

None of this YAML exists in Git. Kyverno generates all of it from the `backup: "hourly"` label.

### Step 5: VolSync Takes Over

A separate Kyverno policy injects the NFS mount (`192.168.10.133:/mnt/BigTank/k8s/volsync-kopia-nfs`) into every VolSync mover Job automatically. No per-app NFS configuration.

On the hourly schedule, VolSync:
1. Asks Longhorn to take a VolumeSnapshot (copy-on-write, app keeps running)
2. Creates a temporary PVC from the snapshot
3. Spins up a mover pod that runs Kopia backup against the temp PVC
4. Ships the data to the shared Kopia repository on TrueNAS
5. Cleans up the temp PVC and snapshot

```
  ┌──────────────┐   Longhorn    ┌──────────────┐
  │  data-pvc    │──snapshot──→  │  temp PVC    │
  │  (live app)  │               │  (frozen)    │
  └──────────────┘               └──────┬───────┘
                                        │
                                  VolSync mover
                                   pod (Kopia)
                                        │
                                        ▼
                              ┌──────────────────┐
                              │  TrueNAS NFS     │
                              │  Kopia repo      │
                              │  (deduplicated,  │
                              │   encrypted,     │
                              │   compressed)    │
                              └──────────────────┘
```

### Step 6: The Rebuild

I nuke the cluster. Or just the karakeep namespace. ArgoCD re-syncs from Git.

The PVC manifest hits the API server again. Kyverno intercepts. pvc-plumber checks the Kopia repository — the backup exists. Kyverno injects `dataSourceRef`. The PVC stays in Pending while VolSync's Volume Populator restores the data. Only after the restore completes does the PVC bind. The app pod starts and finds all its data intact.

```
  Git push ──→ ArgoCD sync ──→ PVC CREATE
                                    │
                              Kyverno + pvc-plumber
                              "backup exists"
                                    │
                              inject dataSourceRef
                                    │
                              PVC Pending
                              (waiting for data)
                                    │
                              VolSync restores
                              from Kopia repo
                                    │
                              PVC Bound
                              (data restored)
                                    │
                              App pod starts
                              with all data ✓
```

Zero manual intervention. No restore commands. No Taskfiles. No UI. Git is the only input.

## The Bootstrap Order

This flow depends on infrastructure being ready before apps deploy. The cluster bootstraps in strict sync wave order:

```
  Wave 0   Cilium ─── ArgoCD ─── 1Password ─── External Secrets
           (networking)  (GitOps)   (secret store)
                │
  Wave 1   Longhorn ─── Snapshot Controller ─── VolSync
           (block storage)  (CSI snapshots)    (backup engine)
                │
  Wave 2   pvc-plumber (2 replicas, anti-affinity, PDB)
           (backup oracle — must be healthy before any PVC decisions)
                │
  Wave 3   Kyverno
           (policy engine — webhooks register here)
                │
  Wave 4   Infrastructure: cert-manager, GPU operators, gateway
           Database: CNPG operators and instances
                │
  Wave 5   Monitoring: Prometheus, Grafana, OTEL
                │
  Wave 6   Apps: Karakeep, Immich, Jellyfin, and 40+ others
```

Custom Lua health checks in ArgoCD enforce that each wave reports Healthy before the next begins. By the time Karakeep's PVC hits the API server at Wave 6, pvc-plumber and Kyverno have been running for minutes.

## Why Not Just Use X?

Every alternative fails against one constraint:

> A Git commit should fully describe the desired state of the cluster, including whether a PVC should restore from backup or start fresh. No manual commands. No out-of-band scripts.

**Velero** — Restores are imperative (`velero restore create`). A rebuilt cluster from Git doesn't know it needs to restore anything.

**VolSync alone** — VolSync moves data. It doesn't make decisions. If you hardcode `dataSourceRef` on every PVC, first deploy of a new app hangs forever because there is no backup to restore from. If you skip `dataSourceRef`, the PVC binds empty before the restore finishes.

**Init Containers** — Requires modifying every upstream Helm chart. Can't fail-closed — if the init container crashes, the pod starts with empty data.

**Longhorn built-in** — Restore requires knowing which backup and triggering it explicitly. No admission-time automation.

**VolumePopulators** — GA in Kubernetes 1.33. They provide the plumbing ("populate this PVC from that source") but have zero conditional logic. The source must exist or the PVC hangs forever.

**Custom Operator** — The architecturally correct long-term answer. Also 10x the development effort for what is fundamentally a boolean decision. At ~40 PVCs, Kyverno + pvc-plumber at ~700 lines total is the right trade-off.

## The Hard-Won Guardrails

These exist because I hit the failure modes they prevent.

**Kyverno fire-and-forget.** The policy runs with `background: false` and `synchronize: false`. With `background: true`, Kyverno re-evaluates every matching PVC every ~30 seconds — that caused a 23-hour API server overload with 70+ workloads. The trade-off: if a generated ReplicationSource is accidentally deleted, Kyverno won't recreate it until someone toggles the PVC label.

**Webhook blast radius.** On 2026-04-08, a Renovate auto-merge crashed Kyverno's admission controller. Its webhook was still registered with `failurePolicy: Fail`. Every resource creation outside kube-system was rejected. Full cluster deadlock. Fix: infrastructure namespaces are excluded from Kyverno's webhook scope. An emergency script deletes all webhook configs if it happens again.

**Backup timing safeguards.** Two preconditions prevent backing up empty data: the ReplicationSource only generates after the PVC is `Bound`, and only after the PVC is 2+ hours old. Without these, a freshly restored PVC could immediately back up its still-populating state, overwriting the good backup.

**Orphan cleanup.** A ClusterCleanupPolicy runs every 15 minutes. If you remove the `backup` label or delete the PVC, it deletes the orphaned ReplicationSource, ReplicationDestination, and ExternalSecret. No stale backup jobs.

## The Trade-Offs

**Single backup domain.** TrueNAS hosts the Kopia repository, NFS shares, and S3 storage. That's concentration, not 3-2-1. A second Kopia target to cloud S3 is the right next step.

**Databases are separate.** CloudNativePG uses Barman to S3 with WAL-based PITR. Filesystem snapshots of a running Postgres are inconsistent. Database backup is a database problem.

**Targeted restore is manual.** The full rebuild path is zero-touch. Rewinding one PVC to a specific point in time still requires a `kubectl patch` on the ReplicationDestination.

**Cache TTL.** pvc-plumber caches backup existence checks for 5 minutes. A backup can complete and a PVC can be created shortly after with a stale cache answer. For hourly schedules this is irrelevant. For tightly-timed workflows, it's worth knowing.

## Where This Should Go

The current architecture composes standard primitives: pvc-plumber provides the conditional decision, Kyverno wires it into admission, VolSync's Volume Populator provides atomic restore. That combination works today.

The right long-term answer is a **conditional VolumePopulator** — a controller that checks for backup existence at provisioning time, restores if found, provisions empty if not. No admission webhook needed. VolumePopulators are GA in Kubernetes 1.33. The plumbing exists. What's missing is the decision logic.

pvc-plumber is a proof-of-concept for functionality that CSI provisioners or backup operators should adopt natively. The admission webhook is the stopgap. The Volume Populator is the destination.

Until that exists upstream, [pvc-plumber](https://github.com/mitchross/pvc-plumber) is 500 lines of Go that answers one question.

---

*If you're thinking "why didn't you just use X," you're asking the right question. The answer is almost always: "X solves backup, but not the conditional restore decision at PVC creation time in a fully declarative GitOps pipeline." We didn't build a backup tool. We built a thin decision layer that answers one boolean question. Everything else is off-the-shelf. The ideal solution is a native Kubernetes API field — something like `spec.dataSourceRef.conditionalRestore` — that CSI provisioners could implement. Until that exists upstream, we're composing primitives to bridge the gap.*
