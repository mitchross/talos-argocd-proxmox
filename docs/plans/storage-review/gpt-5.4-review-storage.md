# GPT-5.4 Storage and DR Review

Date: 2026-04-12

## Purpose

This document is a platform review of the current storage, PVC backup, and disaster recovery design in this repository. It is written to answer one question:

Is this architecture directionally correct for a serious self-hosted Kubernetes platform, or is it a dead end?

The answer is:

- The design is conceptually strong.
- The policy-driven restore model is a real platform contribution.
- The current implementation still has meaningful gaps before it can honestly claim bulletproof or enterprise-grade disaster recovery.

This is not a roast. It is an engineering review.

## Problem Statement

Use this with other LLMs or human reviewers if you want a consistent framing.

```text
Review this Kubernetes disaster recovery architecture as a senior platform engineer.

Context:
- Self-hosted Talos Kubernetes cluster on Proxmox.
- Proxmox VMs/nodes are considered disposable and rebuildable.
- Durable storage lives outside the cluster on TrueNAS.
- Longhorn provides primary live PVC storage.
- PVC backups are automated with Kyverno-generated VolSync resources.
- A custom service called pvc-plumber determines whether a PVC restore source exists and enables zero-touch restore on PVC recreation.
- Requirement: no per-workload backup YAML and no DRY violations.
- Databases use a separate native backup path to S3-compatible object storage.
- Other storage tiers include NFS, SMB, and RustFS/Garage S3.

Requirements:
1. Destroy or rebuild the cluster and all app data comes back automatically.
2. No extra backup manifests per workload.
3. Proxmox is ephemeral; TrueNAS is the durable layer.
4. Workloads should land on any node and still recover data.

Evaluate:
- Whether the architecture is sound.
- Whether it follows Kubernetes and platform best practices.
- Whether it resembles OpenShift, AKS, or GKE patterns.
- Which parts are strong.
- Which parts are risky or overstated.
- Whether Longhorn is the right fit.
- Whether the custom restore orchestration is a good abstraction or unnecessary complexity.
- What changes would most improve the design.
```

## Architecture Under Review

### Stated goals

The current design is clearly optimized for these properties:

1. GitOps-native rebuilds.
2. Zero per-app disaster-recovery manifests.
3. Externalized durability separate from Proxmox.
4. Automatic restore behavior when PVCs are recreated.
5. The ability to move workloads across nodes while preserving state.

### Current storage model

The repo currently implements a workload-tiered storage design:

- Longhorn: primary live block storage for application PVCs.
- NFS: shared Linux-native storage and the current Kopia filesystem repository for PVC backups.
- SMB: compatibility-oriented shared storage.
- RustFS/Garage S3: object storage for CNPG backups, Loki, Tempo, and other S3-native workloads.

Key repo references:

- `infrastructure/storage/longhorn/values.yaml`
- `infrastructure/controllers/kyverno/policies/volsync-pvc-backup-restore.yaml`
- `infrastructure/controllers/pvc-plumber/deployment.yaml`
- `docs/backup-restore.md`
- `docs/pvc-plumber-full-flow.md`
- `infrastructure/database/CLAUDE.md`
- `docs/network-topology.md`
- `monitoring/README.md`

### Current PVC backup flow

The implemented PVC disaster-recovery flow looks like this:

1. A PVC is labeled for backup.
2. Kyverno generates the required backup/restore support resources.
3. VolSync writes PVC backup data to a Kopia repository.
4. pvc-plumber acts as a restore oracle.
5. When a PVC is recreated, Kyverno asks pvc-plumber whether a backup exists.
6. If a backup exists, Kyverno mutates the PVC to restore from backup automatically.

This is the central idea in the platform. It is also the most novel part of the design.

### Current database backup flow

Databases are intentionally not treated as generic PVCs. They use engine-native backup and point-in-time recovery via CNPG and Barman to RustFS S3.

That separation is correct and should be preserved.

## What Is Strong

### 1. The platform solves a real problem that mainstream tools do not solve elegantly

Most Kubernetes backup products and patterns are backup-object driven.

This platform is restore-on-PVC-create driven.

That matters because the repository is clearly structured around GitOps application discovery. In that model, it is reasonable to want:

- directory in Git -> application exists
- PVC exists -> restore happens automatically if prior data exists

This is a legitimate platform abstraction. It is not just YAML cleverness.

### 2. The DRY requirement is valid and the Kyverno approach is justified

The requirement to avoid a second set of DR manifests per workload is strong. It is not cosmetic.

For that requirement, Kyverno is one of the best available ways to express platform policy.

This is a good use of policy:

- backup intent is attached to the PVC
- platform behavior is generated centrally
- applications stay simpler

That is a good internal-platform pattern.

### 3. Proxmox is correctly treated as disposable compute

This is good architecture.

The cluster is not depending on the hypervisor layer for state durability. That is exactly the right instinct for a rebuildable platform.

### 4. Longhorn is a reasonable primary storage choice for these requirements

Longhorn is not the embarrassing part of this design.

It gives you:

- Kubernetes-native PVC behavior
- RWO block storage for stateful apps
- node mobility for workloads
- snapshot and restore friendliness
- tolerable operational complexity for a self-hosted cluster

Would Ceph be more enterprise-like? Yes.
Would Ceph better satisfy your stated simplicity and GitOps goals by default? No.

Longhorn is a pragmatic choice here.

### 5. Database-native backup separation is absolutely correct

The platform explicitly keeps CNPG backup separate from the generic PVC path. That is one of the strongest signals in the repo that the design is thoughtful.

This avoids the common anti-pattern of pretending every stateful workload can be safely recovered through the same filesystem-oriented path.

### 6. Storage tiering is more mature than average

This platform does not force everything into one storage backend.

It distinguishes:

- live block state
- shared Linux-native content
- interoperability shares
- object-native backup and observability data

That is a good architectural instinct.

## Main Challenges And Critiques

### 1. The strongest DR guarantee is overstated today

The informal requirement is effectively:

> Destroy the cluster and everything comes back automatically, no matter what.

That is not true today.

What is closer to true is:

> If the external storage and secret systems remain healthy, the cluster can be rebuilt and PVC-backed application data can restore automatically.

That is still a strong property. It is just not the same thing.

The reason is simple: too much of the platform still depends on the health of the same external durability domain and control-plane prerequisites.

### 2. pvc-plumber readiness is not strong enough for a fail-closed DR claim

This is the most concrete implementation issue found during review.

The pvc-plumber source currently shows:

- `/healthz` always returns OK.
- `/readyz` is implemented the same way as `/healthz`.
- backend failures return `exists: false` rather than hard-failing readiness.

That means the platform can reach a state where:

- pvc-plumber is reachable
- readiness is green
- the backend repo is inaccessible or inconsistent
- the restore decision incorrectly becomes “no backup exists”

This weakens the fail-closed guarantee significantly.

This should be treated as a real defect in the current restore design.

### 3. Failure-domain separation is not sufficient for the strongest DR language

The architecture correctly separates Proxmox from state durability.

However, TrueNAS currently hosts too much of the platform’s durable and semi-durable storage surface:

- NFS
- SMB
- RustFS S3
- the current PVC backup repository

This means the platform is meaningfully resilient to node loss and hypervisor loss, but not sufficiently separated from appliance loss, repo corruption, or storage-admin error.

This is the largest gap between the current design and a truly strong enterprise-style DR story.

### 4. The restore path is elegant, but highly coupled to admission-time orchestration

The platform depends on several things all being correct at bootstrap time:

- ArgoCD sync order
- Kyverno admission
- pvc-plumber correctness
- External Secrets and 1Password connectivity
- VolSync functionality
- Longhorn snapshot/restore behavior
- backup repository availability

This is not an automatic disqualifier. It is the cost of the restore-on-create model.

But it is more coupled than typical productized enterprise backup systems, which are usually backup-plan and restore-object driven rather than webhook-driven.

### 5. The current PVC backup substrate is workable, but not ideal

The current evidence indicates PVC backups are being written to a Kopia filesystem repository on an NFS share.

This is not inherently wrong.

But it has downsides:

- mounted-share availability becomes part of restore correctness
- durability controls are weaker than in object storage systems with versioning/immutability
- failure and failover behavior are more complicated than object-backed designs
- it diverges from the object-backed repository expectations used by many mainstream backup systems

This is not a reason to throw it out. It is a reason to consider the next evolution.

### 6. The platform resembles enterprise patterns in abstraction, but not in operational shape

It is fair to say this platform behaves like a serious internal platform.

It is not fair to say it closely matches OpenShift, AKS, or GKE operational backup patterns.

Those ecosystems generally bias toward:

- CSI-native primary storage
- CSI snapshots where available
- object-backed backup repositories
- controller-driven backup/restore plans
- fewer admission-time restore decisions

This architecture is intentionally different because it optimizes for GitOps-native restore and DRY policy.

That is acceptable, but should be stated honestly.

## Comparison To Established Patterns

### Longhorn

Official Longhorn documentation confirms two important points:

1. Longhorn restore is not UI-only. It supports restore via custom resource/CLI as well as UI.
2. Longhorn explicitly says saving backups to object storage such as S3 is preferable because it generally offers better reliability and avoids mount/unmount complications.

Reference:

- https://longhorn.io/docs/latest/snapshots-and-backups/backup-and-restore/restore-from-a-backup/
- https://longhorn.io/docs/latest/snapshots-and-backups/backup-and-restore/set-backup-target/

This supports a nuanced conclusion:

- The current repo is right that Longhorn restore can be awkward at scale.
- It would be inaccurate to describe Longhorn restore as UI-only.
- Object-backed Longhorn backup targets are closer to Longhorn’s own preferred direction than NFS-mounted backup targets.

### Velero

Official Velero guidance makes the tradeoff clearer:

- File-system backup is capable and flexible, but it is less consistent than snapshot-based methods because it reads live filesystems.
- Object storage is the expected repository target.
- When CSI snapshot data movement is available, Velero says it should generally be used in preference because it is more consistent.

References:

- https://velero.io/docs/v1.18/file-system-backup/
- https://velero.io/docs/v1.18/csi-snapshot-data-movement/

This reinforces two points:

- Your separation of database-native backup is correct.
- Object-backed backup repositories are closer to mainstream best practice than mounted filesystem repositories.

### OKD / OADP

OADP in OKD/OpenShift uses a familiar enterprise pattern:

- Kubernetes objects are backed up to object storage.
- PVs are backed up via native cloud snapshots, CSI snapshots, or Restic/FSB when snapshots are unavailable.

Reference:

- https://docs.okd.io/latest/backup_and_restore/application_backup_and_restore/oadp-features-plugins.html

This means your platform is philosophically adjacent to enterprise Kubernetes backup, but operationally more bespoke.

## Additional Synthesis After Gemini Review

After comparing this review with Gemini's separate assessment in `docs/plans/storage-review/gemini-review-storage.md`, the merged conclusion is:

- Gemini is right about the existence of a real GitOps/stateful restore gap.
- Gemini is right that the current custom layer is an orchestration solution, not a reinvention of backup primitives.
- Gemini is right to worry about restore-surge or “thundering herd” behavior during a full-cluster rebuild.
- Gemini is right that the current cache behavior introduces a stale-negative edge case.
- Gemini is right that filesystem recovery and database-native recovery can drift apart in time and create cross-layer consistency problems.

However, Gemini misses or overstates several things that matter to the final architecture conclusion.

### Where Gemini Is Too Weak

#### 1. It misses the most important implementation defect

The most serious current issue is not the cache TTL edge case.

It is that pvc-plumber readiness is not authoritative enough. The service can remain “ready” while the actual backend is inaccessible or semantically broken, and backend errors can still degrade into a false negative restore decision.

That issue is more important than the TTL edge case because it weakens the fail-closed story under real backend failure.

#### 2. It describes TrueNAS too cleanly

Gemini describes TrueNAS as if it is strictly an archival tier.

That is not the real topology.

TrueNAS is currently serving several roles:

- NFS
- SMB
- RustFS S3
- the current PVC backup repository

That means the architecture has good separation from Proxmox, but not enough separation from the broader TrueNAS durability domain.

#### 3. It is too confident on Kopia Repository Server as the answer

Gemini suggests deploying a Kopia Repository Server to preserve deduplication while avoiding some NFS concerns.

This is a plausible direction, but not something the current repo evidence proves is the correct answer. It depends on:

- VolSync compatibility with the required mode
- restore-on-create behavior remaining intact
- operational complexity not rising too far
- repository server availability not becoming a new bottleneck

So this should be treated as an option to evaluate, not the default recommendation.

#### 4. Its 3-2-1 framing is too generous

The current platform has better separation from compute than many homelabs, but too much durability still converges on the same external appliance domain.

That is not a strong 3-2-1 posture yet.

### Where Gemini Strengthens The Final Review

The most useful additions from Gemini are:

1. The GitOps impedance-mismatch framing.
2. The restore-surge or thundering-herd concern.
3. The cache TTL stale-negative edge case.
4. The explicit warning that database recovery and filesystem recovery must be aligned if application consistency matters.

These points should remain in the final architecture discussion.

## Longhorn Replacement Analysis

The user explicitly raised a real concern: Longhorn multi-attach and related runtime behavior can be painful enough to justify considering a replacement.

That is a valid discussion, but it must be framed correctly.

### What replacing Longhorn would solve

Replacing Longhorn could improve:

- attach and detach behavior
- replica overhead and storage traffic patterns
- runtime scheduling flexibility in some workloads
- alignment with more enterprise-familiar external block storage models

### What replacing Longhorn would not solve

Replacing Longhorn does **not** automatically solve:

- restore-on-PVC-create logic
- DRY backup policy generation
- backup durability concentration on the TrueNAS domain
- pvc-plumber correctness and readiness semantics

That means Longhorn is not the first thing to change unless it is already your dominant operational pain.

### Real replacement options

#### 1. Rook-Ceph or external Ceph

This is the strongest move if the goal is “more enterprise-like on-prem primary storage.”

Pros:

- more enterprise-familiar distributed block model
- stronger separation between the storage system and workload-local node placement
- closer to how serious on-prem platform teams often converge

Cons:

- much higher operational complexity than Longhorn
- more moving parts
- does not solve restore orchestration by itself

Verdict:

- best replacement if the priority is enterprise-style primary storage
- not best if the priority is preserving simplicity while hardening DR first

#### 2. Proxmox CSI or democratic-csi against TrueNAS

Pros:

- externalizes primary storage away from in-cluster Longhorn
- can reduce some in-cluster replication overhead
- may be a better fit if Longhorn runtime behavior is the main pain point

Cons:

- risks collapsing primary storage and backup durability further onto the same appliance domain
- does not solve restore-on-create logic
- can weaken separation of concerns if both runtime I/O and backups depend on the same storage appliance

Verdict:

- viable if the goal is reducing Longhorn-specific pain
- weaker if the goal is stronger disaster-recovery isolation

#### 3. Keep Longhorn and fix the backup architecture first

Pros:

- preserves the current restore model
- addresses the most important architecture weaknesses first
- lowest-change path

Cons:

- retains Longhorn's rough edges

Verdict:

- still the best near-term path unless Longhorn pain is already unacceptable

### Recommended position on Longhorn

Do not replace Longhorn first.

Replace it only if one of these becomes true:

- Longhorn is causing repeated, material operational pain
- attach/detach behavior is materially harming workload reliability
- you are willing to accept a much more complex storage system for stronger enterprise resemblance

Otherwise, the better order of operations is:

1. Fix pvc-plumber readiness and restore correctness.
2. Improve backup durability separation.
3. Run destructive restore drills.
4. Then reevaluate whether Longhorn is still the main bottleneck.

### AKS and GKE

AKS and GKE documentation reinforce standard managed-cluster expectations:

- CSI is the expected storage baseline.
- snapshots and clones are first-class capabilities.
- backup services are plan and restore driven.

References:

- https://learn.microsoft.com/en-us/azure/aks/csi-storage-drivers
- https://docs.cloud.google.com/kubernetes-engine/docs/concepts/persistent-volumes
- https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/concepts/backup-for-gke

Your platform matches those environments at the abstraction level of PVCs and StorageClasses, but not at the restore-control-plane level.

## Is This A Pioneering Effort Or A Waste?

It is not a waste.

The part that is genuinely novel and valuable is this:

- backup intent is declared once on the PVC
- restore behavior is generated automatically
- applications do not carry extra DR manifests
- GitOps rebuilds naturally trigger the restore path

That is a meaningful platform abstraction.

This is not a new backup engine. It is a thin orchestration layer over standard primitives.

That makes it much more defensible.

The right conclusion is:

- The effort is worth continuing.
- The core idea is good.
- The implementation should be hardened before making very strong claims.

## Recommendations

### Priority 0: Fix pvc-plumber readiness semantics

This is the single most urgent recommendation.

The service must distinguish between:

- process is alive
- backend is reachable and authoritative

For `kopia-fs`, readiness should fail if the repository cannot be accessed reliably.
For `s3`, readiness should fail if the object store cannot be queried reliably.

Until this is fixed, the fail-closed story is too weak.

### Priority 1: Add a second durability domain

If requirement 1 is serious, this is mandatory.

Today, the platform is much better protected from Proxmox loss than from TrueNAS loss.

You need a second domain for backup durability, such as:

- replicated object storage
- a second NAS
- cloud object storage
- immutable/versioned bucket-backed copy

Without this, the design is good, but not “nuke-safe.”

### Priority 2: Evaluate moving the PVC backup repository to S3-compatible object storage

This is the most promising architecture improvement if it can preserve the current zero-touch restore semantics.

Why this is attractive:

- closer to Longhorn’s own preferred backup-target guidance
- closer to Velero/OADP and managed-cloud backup patterns
- cleaner lifecycle and replication controls
- less reliance on mounted share semantics during restore

Candidate targets in your environment:

- RustFS S3
- Garage S3

This should be tested against the hard requirement that restore-on-PVC-create remains automatic.

### Priority 3: Keep Longhorn for now

Do not replace Longhorn before fixing the actual weak spots.

Replacing Longhorn with democratic-csi, Proxmox CSI, or another external provisioner does not solve the main problem you are solving, which is policy-driven automatic restore.

Only revisit Longhorn if:

- it becomes the reliability bottleneck
- you want much closer alignment with enterprise distributed storage systems
- you are willing to take on the complexity of Ceph or similar

### Priority 4: Keep database-native backup separate

This is already correct and should not be merged into the generic PVC path.

### Priority 5: Run regular destructive restore drills

The next phase of maturity is proof, not theory.

Run and document drills for:

- namespace loss
- app loss
- cluster rebuild
- Longhorn volume loss
- repo mount failure
- 1Password unavailability
- TrueNAS partial failure

If the platform survives those with measured RTO and RPO, the architecture becomes materially more credible.

## Recommended Future-State Architecture

The best near-term evolution is:

1. Keep Talos.
2. Keep ArgoCD wave ordering.
3. Keep Kyverno-generated backup intent.
4. Keep pvc-plumber as the thin restore oracle.
5. Keep Longhorn as primary live app block storage for now.
6. Move PVC backup durability from Kopia-on-NFS to S3-compatible object storage if restore semantics can be preserved.
7. Replicate that backup durability to a second failure domain.
8. Preserve the separate database-native S3 backup path.

That architecture would be much easier to defend in a serious review.

If Longhorn remains a significant operational pain after those changes, then reevaluate primary storage with this priority order:

1. Rook-Ceph or external Ceph if enterprise-like on-prem block storage is the real target.
2. Proxmox CSI or democratic-csi only if the tradeoff of concentrating more dependence on TrueNAS is acceptable.
3. Stay on Longhorn if the runtime pain is tolerable and the larger DR issues are still the more important engineering problems.

## Claims You Can Safely Make

These claims are defensible today or after modest hardening:

- This is a GitOps-native, policy-driven PVC backup and restore platform.
- Applications do not need per-app backup manifests.
- Cluster rebuild can automatically restore PVC-backed app data when the external storage and secret systems remain available.
- Database workloads use a separate native backup path.
- Storage is tiered by workload pattern instead of forcing all data through one backend.

## Claims You Should Avoid

These claims are too strong today:

- “No matter what, everything restores automatically.”
- “This is equivalent to OpenShift, AKS, or GKE backup architecture.”
- “This is enterprise-grade DR” without measured drills and stronger durability separation.
- “Longhorn restore is UI-only.”

## Final Verdict

This is a strong self-hosted platform design with a real contribution in restore orchestration.

It is not a dead end.
It is not a toy.
It is not a complete enterprise DR story yet.

The verdict is:

- Conceptually right: yes.
- Valuable effort: yes.
- Worth continuing: yes.
- Ready for strongest DR claims: no, not yet.

If the restore oracle is hardened and backup durability is moved to a stronger, replicated object-backed model, this design becomes much easier to defend as a serious internal platform architecture.

In merged form, the final verdict is:

- This is a real platform effort, not a wasted one.
- The policy-driven restore model is the strongest and most distinctive part of the architecture.
- The biggest current weaknesses are restore truthfulness and insufficient durability separation.
- Longhorn may or may not be replaced later, but it is not the first problem to solve unless it is already the dominant operational pain.

## External References

- Longhorn restore from backup: https://longhorn.io/docs/latest/snapshots-and-backups/backup-and-restore/restore-from-a-backup/
- Longhorn backup target guidance: https://longhorn.io/docs/latest/snapshots-and-backups/backup-and-restore/set-backup-target/
- Velero file system backup: https://velero.io/docs/v1.18/file-system-backup/
- Velero CSI snapshot data movement: https://velero.io/docs/v1.18/csi-snapshot-data-movement/
- OKD OADP features and plugins: https://docs.okd.io/latest/backup_and_restore/application_backup_and_restore/oadp-features-plugins.html
- AKS CSI storage drivers: https://learn.microsoft.com/en-us/azure/aks/csi-storage-drivers
- GKE persistent volumes: https://docs.cloud.google.com/kubernetes-engine/docs/concepts/persistent-volumes
- Backup for GKE: https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/concepts/backup-for-gke