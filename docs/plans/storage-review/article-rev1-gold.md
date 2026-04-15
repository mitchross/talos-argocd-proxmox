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

### Why not Velero?

Velero backs up entire namespaces — Kubernetes resources and PV data together — and restores them via `velero restore create`. That's an imperative CLI operation. Someone has to decide to run it. A fully rebuilt cluster syncing from Git doesn't know it needs to restore anything. Velero also backs up the Kubernetes manifests, which in a GitOps cluster are already in Git — redundant work. VolSync only backs up the data, which is the part Git can't track.

### Why not Longhorn's built-in backup?

Longhorn has backup to S3/NFS with scheduled snapshots and a full restore workflow. The problem is the restore side. To restore a Longhorn volume, you need to:

1. Know that a backup exists for this specific volume
2. Know which backup to restore from (by URL or backup name)
3. Trigger the restore explicitly — via UI, CLI, or by setting `fromBackup` on a Volume CR

There is no mechanism in Longhorn that says "when this PVC is created, automatically check if a backup exists and restore from it." The `fromBackup` field is declarative, but only if the exact backup URL is already known — and in a GitOps rebuild, it isn't, because the backup URL changes with every snapshot. Someone still has to look up the right backup and provide the URL. At 40+ PVCs, that's hours of manual work per rebuild.

### Why not VolSync alone?

VolSync is excellent at data movement. I use it. It's the backup engine in my stack. But VolSync doesn't make the restore decision — it does what it's told.

There are two ways to use VolSync for restore, and both have a gap:

**Option A: Hardcode `dataSourceRef` on every PVC pointing to a ReplicationDestination.** VolSync's Volume Populator kicks in and populates the PVC from the latest snapshot before it binds. Atomic restore. But on first deploy of a new app — before any backup exists — the ReplicationDestination has no snapshot. The PVC stays in Pending forever. The app never starts. You have to manually intervene to remove the `dataSourceRef`, let the PVC create empty, then add it back after the first backup runs.

**Option B: Deploy a ReplicationDestination alongside the PVC without `dataSourceRef`.** VolSync tries to restore on ReplicationDestination creation. If no backup exists, it finds nothing and the PVC starts empty — first deploy works. But the PVC binds immediately (empty) and the restore fills it after. If the app pod starts fast and writes before the restore finishes, you get mixed state. And if the backup target is unreachable, the restore silently fails and the app boots with empty data. No fail-closed gate.

pvc-plumber gives you Option A's atomicity with Option B's first-deploy behavior — plus fail-closed. Kyverno only injects `dataSourceRef` when pvc-plumber confirms a backup exists. No backup → no `dataSourceRef` → PVC creates empty → app starts fresh. Backup exists → `dataSourceRef` injected → Volume Populator fills PVC before bind → atomic restore. Backup system unreachable → PVC creation denied → app retries.

### Why not VolumePopulators directly?

VolumePopulators graduated to GA in Kubernetes 1.33. They solve the plumbing: a PVC declares `dataSourceRef` pointing to a custom resource, and a populator controller fills the volume with data before the PVC binds.

But VolumePopulators have zero conditional logic. The PVC must know its data source at creation time. If the referenced resource doesn't exist, the PVC hangs in Pending forever. There's no built-in way to say "populate from this source if it exists, otherwise create empty." That conditional decision is exactly what pvc-plumber provides. The Volume Populator handles the restore mechanics. pvc-plumber decides whether to invoke them.

### Why not init containers?

"Just add an init container that checks for a backup and restores before the app starts." This works if you control every workload definition. I run 40+ apps, many from upstream Helm charts I don't maintain. Modifying every chart to add restore logic is a maintenance nightmare — every chart upgrade risks losing the modification.

Init containers also can't fail-closed. If the init container crashes, times out, or can't reach the backup system, Kubernetes starts the main container anyway — with an empty volume. Silent data loss. The admission webhook approach is transparent to the application (Helm charts are unmodified) and denies PVC creation entirely on unknown state rather than letting the pod start empty.

### Why not a custom operator?

A custom Kubernetes operator is the architecturally correct long-term answer. A single reconciliation loop that watches PVCs, checks backup existence, manages ReplicationSource/Destination lifecycle, and continuously reconciles drift. Full control.

Also 10x the development effort. A proper operator needs: custom CRDs, RBAC, leader election, reconciliation logic, status reporting, health checks, and tests. That's a multi-month project for a team of one. Kyverno + pvc-plumber is ~700 lines total (500 Go + 200 YAML) using existing Kyverno infrastructure for resource generation, lifecycle management, and TLS certificate handling.

At ~40 PVCs with staggered backup schedules, the Kyverno fire-and-forget trade-off is acceptable. At 500+ PVCs, the probability of undetected backup loss from a deleted generated resource becomes high enough that the operator becomes necessary. I know where that line is.

## The Label System

The entire backup interface is two label values:

| Label | Schedule | When to use |
|-------|----------|-------------|
| `backup: "hourly"` | `0 * * * *` | App state that changes frequently (bookmarks, uploads, configs) |
| `backup: "daily"` | `0 2 * * *` | App state that changes slowly (model caches, large datasets) |

Both get the same retention: 24 hourly, 7 daily, 4 weekly, 2 monthly snapshots.

**What NOT to label:**
- CNPG database PVCs — they use Barman to S3, not VolSync. Filesystem snapshots of a running Postgres are inconsistent without the WAL stream.
- System namespace PVCs (kube-system, volsync-system, kyverno) — auto-excluded by the policy.
- PVCs on non-Longhorn storage classes — VolumeSnapshot support is required for the copy-on-write backup method.

Kyverno matches PVCs with a label selector:

```yaml
selector:
  matchExpressions:
    - key: backup
      operator: In
      values: ["hourly", "daily"]
```

If the label is present, the full pipeline fires. If it's absent, the PVC is invisible to the backup system.

## The Kyverno Policy: How It Actually Works

The backup/restore system is a single `ClusterPolicy` with five rules. The policy settings are critical and non-obvious:

```yaml
spec:
  mutateExistingOnPolicyUpdate: false   # don't re-evaluate all PVCs on policy edit
  background: false                      # don't continuously re-scan matching resources
  rules:
    - name: require-pvc-plumber-available     # Rule 0: fail-closed gate
    - name: add-datasource-if-backup-exists   # Rule 1: conditional restore
    - name: generate-kopia-secret             # Rule 2: ExternalSecret
    - name: generate-replication-source        # Rule 3: backup schedule
    - name: generate-replication-destination    # Rule 4: restore target
```

**Rules 0-1** are admission-time: they run synchronously during the PVC CREATE and must complete before the PVC is persisted to etcd.

**Rules 2-4** are generate rules: they create new resources asynchronously after the PVC is admitted. The generated resources are labeled `app.kubernetes.io/managed-by: kyverno` and `volsync.backup/pvc: {pvc-name}` so the orphan cleanup policy can find them later.

Every generate rule uses `synchronize: false`. This is critical. With `synchronize: true`, Kyverno watches every generated resource for drift and creates an UpdateRequest whenever a controller updates the resource's status field. With ~114 generated resources across the cluster (ReplicationSources, ReplicationDestinations, ExternalSecrets), controllers updating status fields generate hundreds of thousands of API calls per cycle. The API server buckles.

## The Hard-Won Guardrails

These exist because I hit the failure modes they prevent.

**23-hour API server overload (2026-03-25).** The original policy used `background: true` and `synchronize: true`. With 70+ workloads, Kyverno re-evaluated every matching PVC every ~30 seconds, generating hundreds of UpdateRequests that hammered the API server. The fix was `background: false` and `synchronize: false`. The trade-off: if a generated ReplicationSource is accidentally deleted, Kyverno won't recreate it until someone toggles the PVC label. VolSync metrics in Prometheus catch silent backup failures.

**Full cluster deadlock (2026-04-08).** A Renovate auto-merge of a kube-prometheus-stack chart upgrade restarted too many pods simultaneously. Kyverno's admission controller crashed with a cache sync failure. Its webhook was still registered with `failurePolicy: Fail`. Every Deployment, StatefulSet, and DaemonSet creation outside kube-system was rejected. Longhorn couldn't restart its pods. ArgoCD couldn't mount PVCs. Even rebooting all nodes didn't fix it — webhook configurations persist in etcd. Fix: infrastructure namespaces (longhorn-system, argocd, volsync-system, cert-manager, external-secrets) are now excluded from Kyverno's webhook `namespaceSelector`. An [emergency script](https://github.com/mitchross/talos-argocd-proxmox/blob/main/scripts/emergency-webhook-cleanup.sh) deletes all webhook configurations to break the deadlock. Kyverno recreates them once healthy.

**Backup timing safeguards.** Two preconditions prevent backing up empty data:

1. ReplicationSource only generates after the PVC status is `Bound` — prevents backing up during an active restore (when PVC is Pending waiting for the Volume Populator)
2. ReplicationSource requires the PVC to be at least 2 hours old — prevents immediately backing up empty or partially-restored data after a fresh provision

Without these, the sequence would be: PVC created → VolSync starts restoring → Kyverno generates ReplicationSource → ReplicationSource fires immediately → backs up partially-restored data → overwrites the good backup in the Kopia repository. This is the same problem described in VolSync Issue #627, solved at the policy layer.

**Orphan cleanup.** A `ClusterCleanupPolicy` runs every 15 minutes. If the `backup` label is removed from a PVC, or the PVC is deleted entirely, the policy deletes the orphaned ReplicationSource, ReplicationDestination, and ExternalSecret. No stale backup jobs accumulate.

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
