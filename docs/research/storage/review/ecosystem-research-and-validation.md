# Ecosystem Research & Architectural Validation Report

## Context
**Date:** 2026-04-14
**Author:** Claude Opus 4.6, synthesizing research across official docs, GitHub issues, community repos, blogs, YouTube creators, Reddit, Discord, and the home-operations ecosystem
**Purpose:** Answer the question: "Has anyone else solved the conditional PVC restore problem? If not, why not?"
**Trigger:** After multi-model architectural review (Gemini, GPT-5.4, Claude, DeepSeek), the repo owner questioned whether second-guessing was warranted — if the problem were real, surely someone else would have solved it by now.

## Executive Summary

The problem is real. Nobody else has built a complete solution.

The Kubernetes ecosystem has mature tools for backup (VolSync, Velero, Longhorn, Kasten K10) and mature tools for restore (VolumePopulators, CSI snapshots, Velero restore CRs). What nobody has built is the **decision layer**: at PVC creation time, check whether a backup exists, restore if so, create empty if not, and deny if the answer is unavailable.

The closest the community gets is VolSync's Volume Populator integration, used by the home-operations community (onedr0p/cluster-template). But that approach hangs forever on first deploy of a new app with no backup, and has no fail-closed behavior if the backup system is down.

pvc-plumber is not a backup tool. It is a ~500-line Go microservice that answers one question: "Does a backup exist for this PVC?" That question has no existing answer in the Kubernetes ecosystem.

---

## Part 1: The Architecture Under Review

### What This Cluster Does

When an app developer adds a PVC to Git with `backup: "hourly"`, the following happens automatically:

1. ArgoCD syncs the PVC manifest
2. Kyverno intercepts the CREATE at admission time
3. Kyverno calls PVC Plumber (`/readyz`) — if unreachable, PVC creation is **denied**
4. Kyverno calls PVC Plumber (`/exists/{namespace}/{pvc-name}`) — if backup found, `dataSourceRef` is injected pointing to a VolSync ReplicationDestination
5. Kyverno generates: ExternalSecret (Kopia credentials from 1Password), ReplicationSource (backup schedule), ReplicationDestination (restore capability)
6. A separate Kyverno MutatingAdmissionPolicy injects the NFS mount into VolSync mover Jobs
7. VolSync backs up PVC data via Kopia to a TrueNAS NFS share on schedule
8. On cluster rebuild, the same flow restores all data automatically — zero manual intervention

### The Core Innovation

The system provides a **conditional restore primitive** that is:

- **Admission-time**: The decision happens before the PVC exists
- **Conditional**: Backup exists → restore. No backup → create empty. Backup system down → deny.
- **Transparent**: App manifests are unmodified. No init containers, no custom annotations beyond the backup label.
- **Fail-closed**: Unknown state → explicit denial, not silent empty creation

### Sync Wave Dependency Chain

```
Wave 0: Cilium + ArgoCD + 1Password/ESO       ← networking, GitOps, secrets
Wave 1: Longhorn + Snapshot Controller + VolSync ← storage, snapshots, backup engine
Wave 2: PVC Plumber                             ← backup existence oracle
Wave 3: Kyverno                                 ← policy engine, admission webhooks
Wave 4: Infrastructure AppSet + Database AppSet  ← cert-manager, GPU, gateway, CNPG
Wave 5: Monitoring AppSet + OTEL                 ← Prometheus, Grafana
Wave 6: My-Apps AppSet                           ← user workloads (Karakeep, etc.)
```

Custom Lua health checks in ArgoCD enforce that each wave is Healthy before the next begins. This is load-bearing infrastructure, not cosmetic ordering.

---

## Part 2: Community Research — What Everyone Else Does

### Tier 1: The home-operations Community (onedr0p, joryirving, kashalls)

**Size:** ~9,165 members on Discord. The largest GitOps homelab community.

**Their stack:** Talos Linux + Flux + Rook-Ceph (or Longhorn) + VolSync (migrating from Restic to Kopia) + external NAS for NFS/SMB.

**How they handle PVC backup/restore:**

- Each app that needs backup gets a manually-defined VolSync ReplicationSource alongside its PVC, typically via a reusable Kustomize component
- Backup destination is S3-compatible storage (Backblaze B2, Cloudflare R2) or local NFS
- A MutatingAdmissionPolicy injects NFS volume mounts into VolSync mover pods (same pattern as this repo)
- On cluster rebuild, PVCs declare `dataSourceRef` pointing to a ReplicationDestination. VolSync populates from the latest Kopia/Restic snapshot. Pods go Pending until data is restored.

**What they don't have:**

| Capability | home-operations | This repo |
|---|---|---|
| Conditional restore (backup exists → restore, else → empty) | No — `dataSourceRef` is always set; new apps with no backup hang forever | Yes — PVC Plumber checks existence at admission time |
| Fail-closed gate | No — PVC hangs in Pending (no explicit deny) | Yes — Kyverno denies PVC creation if PVC Plumber is unreachable |
| Auto-generation of VolSync resources from a label | No — manually define ReplicationSource/Destination per app | Yes — Kyverno generates everything from `backup: "hourly"` label |
| First-deploy compatibility | No — new app with no backup = infinite Pending | Yes — no backup = PVC created empty, app starts normally |

**Key reference:** [onedr0p/cluster-template Discussion #1557](https://github.com/onedr0p/cluster-template/discussions/1557) documents their DR flow. [VolSync Issue #627](https://github.com/backube/volsync/issues/627) documents the problem of VolSync immediately backing up empty data on a fresh cluster, potentially overwriting good backups.

**The Restic → Kopia migration (2025-2026):** The community is actively migrating from Restic to Kopia. Motivations: Restic repos are opaque (can't browse without CLI), stale lock issues require manual intervention, Kopia has a web UI for browsing/verifying backups, and Kopia offers better deduplication and 4x faster data transfer in benchmarks. Reference: [blog.nerdz.cloud](https://blog.nerdz.cloud/2025/volsync-kopia-migration/).

### Tier 2: Longhorn Built-in Backup Users

A significant portion of homelabbers use Longhorn's native backup to S3/MinIO, skipping VolSync entirely.

**How it works:**

- Configure Longhorn backup target (MinIO, Garage, cloud S3)
- Scheduled snapshots and backups via Longhorn's built-in scheduler
- **Restore is manual** — via UI, CLI, or CRD, but always requires knowing which backup to restore and triggering it explicitly

**Real-world examples:**

- [Merox](https://merox.dev/blog/longhorn-backup-restore/) documented restoring 6 apps from Longhorn backups after redeploying a K8s cluster with Flux, using Garage S3 on Oracle Cloud. It worked. It took hours.
- [Gaige's Pages](https://www.gaige.net/recovering-longhorn-backups.html) describes rebuilding 4 storage nodes, losing all data, and recovering from S3 backups. Manual and tedious.
- [RedDec](https://reddec.net/posts/longhorn-backup-and-restore/) notes that static volumes (deterministic names) are easy to restore, but dynamic volumes (random PVC names) are "extremely complicated" to re-link.

**The gap:** Longhorn restore requires a human (or external script) to select a backup and trigger restore. There is no admission-time "check and restore" mechanism.

### Tier 3: NFS Externalists (Techno Tim, democratic-csi users)

**Philosophy:** Data never lives in Kubernetes. Mount NFS from TrueNAS/Synology. ZFS handles snapshots on the NAS side. Nuke the cluster, re-mount the shares, done.

**Who does this:** Techno Tim keeps most stateful services on TrueNAS with Docker Compose. Only public-facing/orchestrated workloads run in K8s. Democratic-CSI users mount iSCSI/NFS from TrueNAS with ZFS snapshots/replication as the backup mechanism.

**Why it works:** Cluster rebuild is trivial — just re-mount the shares. No PVC backup or restore logic needed.

**Why it doesn't solve the same problem:** Every app must use NFS. No block storage. No Longhorn snapshots. No per-PVC point-in-time restores. Not compatible with apps that need ReadWriteOnce block storage with filesystem-level snapshots.

### Tier 4: The YOLO Camp

More common than admitted. No backup strategy. Databases on VMs outside K8s. Accept data loss on rebuild. Re-download media, re-configure apps.

### YouTubers and Influencers

| Creator | Storage Approach | Backup Approach |
|---|---|---|
| **Techno Tim** | Longhorn for K8s, Docker Compose on TrueNAS for stateful services | Longhorn built-in; most data external to K8s |
| **Christian Lempa** | Longhorn | Longhorn backup; emphasizes simplicity |
| **Jim's Garage** | Various (Proxmox + K8s scripts) | Manual / varies by project |
| **Eric Daly** | democratic-csi + TrueNAS (iSCSI/NFS) on Talos | Velero + Kasten K10 |
| **VirtualizationHowto** | Rook-Ceph on Talos | Kasten K10 (discovered CSI snapshot issues the hard way) |

**No YouTuber or blogger has demonstrated admission-time conditional PVC restore.** The topic is not discussed in any video or blog post found during this research.

---

## Part 3: Evidence the Gap Is Real

### Direct Evidence

**Longhorn Issue #6748 (September 2023):** A user named astranero opened an issue requesting exactly this feature: "I want that before longhorn creates a new PV it checks backups for PV that has a name and namespace of this PVC that I am creating and then restores this PV binding it with new PVC." The issue was **closed as invalid** with no implementation.

**VolSync Issue #627:** When GitOps applies a ReplicationSource to a fresh cluster, it immediately tries to back up empty data, potentially overwriting good backups. The community works around this with manual triggers. This repo's 2-hour delay precondition on ReplicationSource generation is a cleaner solution to this exact problem.

**Kubernetes Data Protection Working Group white paper:** Discusses VolumePopulators for restore but never mentions conditional restore, fail-closed gating, or admission-time backup checking. The restore workflows described are all user-initiated.

### VolumePopulators (GA in Kubernetes 1.33) — Close But Not Enough

VolumePopulators allow PVCs to reference arbitrary CRDs via `dataSourceRef`, and a custom controller populates the volume with data before binding. This is the Kubernetes-native mechanism for restore.

**Critical limitation:** VolumePopulators are designed for a PVC that already knows it wants data from a specific source. The PVC must declare `dataSourceRef` pointing to a specific CR. There is no conditional logic — if the referenced source doesn't exist, the PVC stays Pending forever. There is no "check if backup exists, populate if so, else create empty" behavior.

**VolumePopulators provide the plumbing for restore, not the decision logic.**

### The Complete Alternative Landscape

| Tool | Does Backup | Does Restore | Conditional Logic | Fail-Closed | Admission-Time | First Deploy Works |
|---|---|---|---|---|---|---|
| Velero | Yes | Yes (imperative) | No | No | No | N/A |
| VolSync | Yes | Yes (via VolumePopulator) | No | No | No | **No** — hangs forever |
| Longhorn built-in | Yes | Yes (manual trigger) | No | No | No | N/A |
| Kasten K10 | Yes | Yes (RestoreAction) | No | No | No | N/A |
| KubeStash | Yes | Yes (via VolumePopulator) | No | Undocumented | No | Unknown |
| K8up | Yes | Yes (imperative) | No | No | No | N/A |
| Gemini (Fairwinds) | Snapshots | Manual annotation | No | No | No | Yes |
| VolumePopulator (native) | No | Yes | No | No | No | **No** — hangs if source missing |
| CSI Snapshots | Yes | Yes (if snapshot name known) | No | No | No | **No** — fails if no snapshot |
| Custom Operator | Could | Could | Could | Could | Could | Could |
| **PVC Plumber + Kyverno** | Via VolSync | Via VolSync | **Yes** | **Yes** | **Yes** | **Yes** |

### Why Nobody Else Built It

Three reasons:

1. **Most homelabbers use Flux, not ArgoCD.** Flux has built-in health checks and dependency ordering. The home-ops community doesn't need sync waves. But they still don't have conditional restore logic.

2. **The Kyverno admission webhook + external HTTP call pattern is unusual.** Most people use Kyverno for security policies, not as an orchestration layer. Using Kyverno's `apiCall` to hit an external service during PVC admission is a creative use of the tool that most people wouldn't think to do.

3. **Most people don't rebuild their cluster as often.** The typical homelab is built once and maintained. PVCs are rarely created from scratch after initial setup. The threat model of "I experiment constantly, I nuke namespaces, I upgrade Talos, I Helm-upgrade wrong" is less common than "I built it and it runs."

---

## Part 4: The Critique Process

### How This Review Happened

1. **ChatGPT** wrote the initial `homelab-storage-reference.md` — a positioning document explaining why the architecture is the right answer for the problem
2. **Claude** (this model) critiqued the document, identifying 5 gaps: no mention of operational debt, `/readyz` authority, sync wave fragility, NFS injection as hidden dependency, alerting as aspirational
3. **ChatGPT** tightened the document, adding 9 new sections covering every gap raised. The document became honest without becoming defensive.
4. **ChatGPT** recommended next steps: keep the architecture, harden implementation, validate with drills
5. **Claude** agreed with the direction but simplified the action list to 3 items (verify `/readyz`, wire Alertmanager, run one drill) after the user clarified their actual threat model

### The User's Actual Threat Model

The user clarified that their real failure mode is not hardware death or NFS outages. It is:

- Helm upgrades that accidentally delete or recreate PVCs
- Experimenting with app configs and accidentally nuking state
- Kustomize merges that drop a PVC from the resource list
- Cluster rebuilds after Talos upgrades
- Deleting namespaces to start fresh and wanting data back

This changes the framing significantly. pvc-plumber is not protecting against disk failure — it is protecting against **the user's own workflow**. The system exists so that destructive operations (intentional or accidental) are automatically recovered from, without manual intervention.

This is also why the user doesn't care about alerts — they won't read notifications. Their feedback loop is: "I deleted something, ArgoCD re-synced, did my data come back?" That's a test they run naturally every time they experiment.

### Multi-Model Architectural Review (from final-synthesis.md)

Four AI models reviewed the architecture independently:

| Model | Core Assessment | Top Priority |
|---|---|---|
| **Gemini** | Problem is genuine and under-served. Implementation has severe operational debt. | Rewrite `/readyz` to validate backend health |
| **GPT-5.4** | Good platform engineering with real merit. Strongest claims outrun implementation. | Restore truthfulness and durability concentration |
| **Claude Opus 4.6** | Right idea at the wrong maturity level for publication. All gaps are fixable. | `/readyz` + destructive drill + measured RTO |
| **DeepSeek** | Built the "Why Not X?" rebuttal framework for the article | Preemptive defense against 12 alternative suggestions |

**Unanimous consensus across all models:**

- The problem is real
- The architecture is not a waste
- The core design should not change
- `/readyz` must be authoritative (P0 fix)
- Do not replace Longhorn (it is not the bottleneck)
- Do not rewrite to a custom operator (not justified at ~40 PVCs)

---

## Part 5: Comparison to Community Best Practice

### Where This Repo Matches Community Practice

| Practice | Community Standard | This Repo |
|---|---|---|
| Immutable OS | Talos Linux | Talos Linux |
| GitOps | Flux (majority) or ArgoCD | ArgoCD |
| Block storage | Longhorn or Rook-Ceph | Longhorn |
| Backup engine | VolSync + Kopia (2025+ trend) | VolSync + Kopia |
| Backup target | NFS + cloud S3 | NFS (TrueNAS) |
| NFS injection | MutatingAdmissionPolicy | Kyverno MutatingAdmissionPolicy |
| Database backup | CNPG + Barman to S3 | CNPG + Barman to S3 |
| NFS for browsable data | Common (models, media) | Yes (comfyui, llamacpp, jellyfin) |
| Secret management | SOPS or External Secrets | External Secrets + 1Password |

### Where This Repo Goes Beyond Community Practice

| Capability | Community | This Repo |
|---|---|---|
| VolSync resource generation | Manual per-app Kustomize component | Automatic from PVC label via Kyverno |
| Conditional restore | Not implemented; `dataSourceRef` always set or never set | PVC Plumber checks backup existence at admission time |
| Fail-closed behavior | Not implemented; PVC hangs in Pending or creates empty | Kyverno denies PVC creation if backup system unavailable |
| First-deploy compatibility | New apps with no backup hang forever (VolSync VolumePopulator) | New apps create empty PVCs, start normally |
| Sync wave enforcement | Flux dependency ordering (health checks) | ArgoCD sync waves + custom Lua health checks |
| Orphan cleanup | Manual or not addressed | ClusterCleanupPolicy runs every 15 minutes |
| Backup schedule from label | Not implemented — schedule hardcoded per app | `backup: "hourly"` → `0 * * * *`, `backup: "daily"` → `0 2 * * *` |

### Where Community Practice Is Ahead

| Capability | Community | This Repo |
|---|---|---|
| Offsite backup durability | NFS + cloud S3 (3-2-1) | NFS only (single TrueNAS domain) |
| Backup browsing | Kopia web UI (joryirving runs Kopia server in-cluster) | No Kopia UI; CLI only |
| Storage backend diversity | Rook-Ceph gaining traction for RWX and performance | Longhorn only |

---

## Part 6: Conclusions

### The Gap Is Real

No tool in the Kubernetes ecosystem — open source or commercial — provides admission-time conditional PVC restore with fail-closed behavior. The closest approach (VolSync Volume Populator + home-operations conventions) solves the restore-on-rebuild case but breaks on first deploy and has no fail-closed semantics.

Longhorn Issue #6748 proves at least one other user independently identified the same gap. It was closed without implementation.

### The Architecture Is Right

The design of composing Kyverno admission policies + a lightweight backup-existence oracle + VolSync + Longhorn is a valid solution that:

- Solves a problem nobody else has solved
- Uses standard Kubernetes primitives (no custom CRDs)
- Is transparent to application developers (no Helm chart modifications)
- Fails closed on unknown state (unique in the ecosystem)
- Works on both first deploy (empty) and rebuild (restore)

### The Implementation Has Known Gaps

All identified by the multi-model review and now documented:

1. **`/readyz` may not validate Kopia repository health** — the fail-closed guarantee depends on this being authoritative
2. **Single backup domain** — TrueNAS hosts NFS shares, S3 (RustFS), and the Kopia backup repository
3. **Kyverno fire-and-forget** — if generated resources are deleted, they are not recreated until PVC label is toggled
4. **Cache TTL** — 5-minute window where backup existence check can return stale results
5. **Kyverno webhook blast radius** — mitigated by namespace exclusions and emergency cleanup script, but Kyverno remains a cluster-wide SPOF

### What to Do Next

For the user's actual threat model (accidental deletion, experiments, upgrades — not hardware failure):

1. **Verify `/readyz` probes the Kopia repo** — check pvc-plumber source code. If it only checks process health, fix it.
2. **Keep building apps.** The storage layer works. The architecture is sound. The doc is honest. Don't over-engineer a problem that's already solved for the actual use case.
3. **Consider offsite backup** when convenient — second Kopia target to S3, remote ZFS replication, or cloud bucket. Not urgent, but the only real durability gap.

### What Not to Do

- Do not replace Longhorn (it is not the pain point)
- Do not rewrite pvc-plumber as a custom operator (not justified at ~40 PVCs)
- Do not wire up alerts you won't read
- Do not run formal DR drills you'll do naturally by experimenting
- Do not redesign the architecture — it works, and nobody else has built anything better

### The One-Line Summary

pvc-plumber fills a genuine gap in the Kubernetes ecosystem — the conditional restore primitive — that no other tool addresses. The architecture is the right design for the problem. The implementation needs one fix (`/readyz`). Everything else is working.

---

## Appendix A: Sources

### GitHub Issues and Discussions
- [Longhorn Issue #6748](https://github.com/longhorn/longhorn/issues/6748) — User requesting conditional restore at PVC create time (closed, no implementation)
- [VolSync Issue #627](https://github.com/backube/volsync/issues/627) — Bootstrap problem: VolSync backs up empty data on fresh cluster
- [VolSync Issue #1158](https://github.com/backube/volsync/issues/1158) — Temporary PVC cleanup after restore
- [Flux Issue #3896](https://github.com/fluxcd/flux2/issues/3896) — PVC reconciliation after manual Longhorn restore
- [onedr0p/cluster-template Discussion #1557](https://github.com/onedr0p/cluster-template/discussions/1557) — DR flow documentation
- [Velero Issue #4847](https://github.com/vmware-tanzu/velero/issues/4847) — Velero issues with admission webhooks during restore

### Community Repos
- [onedr0p/home-ops](https://github.com/onedr0p/home-ops) — Reference GitOps homelab (Rook-Ceph + VolSync)
- [onedr0p/cluster-template](https://github.com/onedr0p/cluster-template) — Most-forked homelab starting point
- [joryirving/home-ops](https://github.com/joryirving/home-ops) — Kopia server + NFS injection pattern
- [bjw-s-labs/helm-charts](https://github.com/bjw-s-labs/helm-charts) — Popular homelab Helm library chart
- [Home Operations Discord](https://discord.com/servers/home-operations-673534664354430999) — Primary community hub

### Blog Posts
- [blog.nerdz.cloud — Volsync Kopia Migration](https://blog.nerdz.cloud/2025/volsync-kopia-migration/) — Why the community migrated from Restic to Kopia
- [blog.nerdz.cloud — Talos DR Reset](https://blog.nerdz.cloud/2025/talos-dr-reset/) — Real bare-metal rebuild with VolSync
- [Merox — Longhorn Backup Restore](https://merox.dev/blog/longhorn-backup-restore/) — Manual Longhorn restore after Flux rebuild
- [Gaige's Pages — Recovering Longhorn Backups](https://www.gaige.net/recovering-longhorn-backups.html) — 4-node rebuild, manual per-volume restore
- [RedDec — Longhorn Backup and Restore](https://reddec.net/posts/longhorn-backup-and-restore/) — Static vs dynamic volume restore complexity
- [JLP — When Borg Backups Meet Longhorn](https://blog.leechpepin.com/posts/longhorn-recovery/) — Data corruption from backing up mounted Longhorn volumes
- [HaynesLab — Backup Strategy](https://hayneslab.net/docs/funky-flux/backup-strat/) — Why VolSync over Velero for GitOps
- [Jacob Colvin — Backups for K8s and Beyond](https://jacobcolvin.com/posts/2023/01/backups-for-k8s-and-beyond/) — K8up with annotation-based PVC selection
- [Eric Daly — Backups With Velero](https://blog.dalydays.com/post/kubernetes-homelab-series-part-7-backups-with-velero/) — Velero homelab setup
- [VirtualizationHowto — I Thought My Backups Worked](https://www.virtualizationhowto.com/2026/04/i-thought-my-kubernetes-backups-worked-in-my-home-lab-but-i-was-wrong/) — CSI snapshot validation failures
- [VirtualizationHowto — Why Ceph Won](https://www.virtualizationhowto.com/2026/01/why-ceph-won-for-persistent-storage-in-my-talos-linux-kubernetes-minilab/) — Ceph on Talos for RBD + CephFS
- [Jonathangazeley — Hyperconverged Storage](https://jonathangazeley.com/2023/03/14/kubernetes-homelab-part-4-hyperconverged-storage/) — OpenEBS cStor failure, now advises against hyperconverged
- [Techno Tim — Longhorn Install](https://technotim.com/posts/longhorn-install/) — Longhorn setup guide
- [Techno Tim — Homelab Services Tour 2026](https://technotim.com/posts/homelab-services-tour-2026/) — Most services on Docker Compose, not K8s
- [wazaari.dev — TrueNAS Talos Democratic-CSI](https://wazaari.dev/blog/truenas-talos-democratic-csi/) — Democratic-CSI on Talos

### Official Documentation
- [Kubernetes VolumePopulators GA (v1.33)](https://kubernetes.io/blog/2025/05/08/kubernetes-v1-33-volume-populators-ga/)
- [VolSync Volume Populator](https://volsync.readthedocs.io/en/latest/usage/volume-populator/index.html)
- [Kubernetes Data Protection WG White Paper](https://github.com/kubernetes/community/blob/master/wg-data-protection/data-protection-workflows-white-paper.md)
- [TrueCharts VolSync Guide](https://truecharts.org/guides/backup--restore/volsync-backup-restore/)

### Benchmark and Comparison Data
- [Onidel — Longhorn vs OpenEBS vs Rook-Ceph on k3s (2025)](https://onidel.com/blog/longhorn-vs-openebs-rook-ceph-2025)
- [Cwiggs — OpenEBS Mayastor vs Longhorn](https://cwiggs.com/posts/2024-12-26-openebs-vs-longhorn/)
- [Kubedo — Kubernetes Storage Comparison](https://kubedo.com/kubernetes-storage-comparison/)

### Cautionary Tales
- Jonathan Gazeley lost all data when OpenEBS cStor lost quorum along with MicroK8s dqlite. Now advises against hyperconverged storage in homelabs.
- JLP found only 9 of 17 Longhorn volumes recoverable. Borg was backing up actively-mounted SCSI devices, producing corrupt data. Only PGDump backups survived.
- Brandon Lee (VirtualizationHowto) discovered his CSI snapshots weren't actually working — validated backups are not the same as running backups.

## Appendix B: The "Why Not X?" Quick Reference

For anyone asking "why didn't you just use X?":

| Alternative | Why It Doesn't Solve Conditional Restore |
|---|---|
| Velero | Restores are imperative CLI operations, not admission-time decisions |
| VolSync alone | Hangs when no backup exists; by design, doesn't make decisions |
| Init Containers | Requires modifying every Helm chart; cannot fail-closed |
| KubeStash / K8up | Backup operators with imperative restores, not decision engines |
| Longhorn built-in | Restore requires explicit trigger and backup identification |
| Kanister | Solves app-consistency workflows, not admission-time logic |
| CSI Snapshots | Requires knowing snapshot name in advance; fails on first deploy |
| Custom Operator | Correct long-term answer; 10x dev effort for ~40 PVCs today |
| Commercial (Portworx/K10/Trilio) | Budget, vendor lock-in, cloud-provider assumptions |
| CNPG/Barman | Database-specific; doesn't cover filesystem PVCs |
| Raw Admission Webhook | Simpler binary but reimplements Kyverno's generation/lifecycle/TLS |
| Custom VolumePopulator | Most native path; limited CSI support and bootstrap complexity today |

The universal answer: **X solves backup, but not the conditional restore decision at PVC creation time in a fully declarative GitOps pipeline.**
