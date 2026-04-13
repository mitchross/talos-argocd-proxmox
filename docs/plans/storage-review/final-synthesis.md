# Final Synthesis & Master Architectural Recommendations

## Context & Origin
**Collaborators:** Gemini (Started), ready for Claude & GPT input
**Date:** 2026-04-12
**Purpose:** This document serves as the master, synthesized position on the `pvc-plumber` + Kyverno Zero-Touch DR architecture. It was initialized by Gemini after analyzing the peer reviews provided by GPT-5.4 and Claude Opus 4.6. This is intended to be a living document; Claude and GPT should append their own final thoughts, disagreements, or consensus points here to form the ultimate execution baseline.

## 1. The Core Architectural Verdict (Gemini's Input)

I am formally adopting the consensus that **the core problem being solved is genuine and under-served.** The current Kubernetes ecosystem lacks a "conditional restore primitive" (the ability to conditionally provision a PVC from a backup if it exists, and provision empty otherwise) that is compatible with declarative GitOps pipelines.

The `pvc-plumber` microservice + Kyverno admission control flow is a valid, highly innovative solution to this "GitOps Impedance Mismatch." The architecture is not a waste, nor is it a frivolous homelab experiment; it effectively mimics enterprise policy-driven abstractions.

However, the current implementation carries severe operational debt that will cause catastrophic failures during a high-concurrency DR event. It must be hardened before publication or production use.

## 2. Immediate Engineering Action Plan (Code & Architecture Changes)

Before writing any articles or claiming "Enterprise-Grade DR," the following code and architecture changes must be executed:

### P0: Re-write the `/readyz` fail-closed gate
- **The Defect:** Currently, `pvc-plumber` `/readyz` returns 200 OK regardless of backend storage health. If TrueNAS dies, the microservice stays "Ready" but falls back to `exists: false`. Kyverno then allows ArgoCD to deploy a fresh, empty PVC over a missing backup.
- **The Fix:** Modify the `pvc-plumber` Go code. The `/readyz` endpoint MUST perform an active health check against the Kopia repository (e.g., executing a `stat` on a known file or a quick API ping). If the storage backend is unreachable, the pod must fail readiness. This guarantees Kyverno rejects all PVC creation until the backup vault is fully restored.

### P0: Eliminate the `nolock` NFS Time Bomb
- **The Defect:** VolSync pods are mounting the Kopia TrueNAS repository over NFS using the `nolock` option. During a multi-volume restore or concurrent backup phase, uncoordinated writes will silently corrupt the Kopia index.
- **The Fix:** You have two options. (1) Shift the VolSync Kopia destination away from NFS to your existing S3-compatible GarageFS/RustFS object store, which handles concurrency via eventual consistency safely. (2) Deploy a centralized Kopia Repository Server pod that handles all filesystem writes locally and exposes a gRPC endpoint to the VolSync movers.

### P1: Implement High Availability (HA) for `pvc-plumber`
- **The Defect:** Running a single replica of the admission oracle means a single node drain or OOM kill instantly freezes all stateful deployments cluster-wide.
- **The Fix:** Update the `pvc-plumber` deployment to `replicas: 2`, implement Pod Anti-Affinity (forcing them onto separate Proxmox nodes), and add a `PodDisruptionBudget` of `minAvailable: 1`.

### P1: Thundering Herd Mitigation
- **The Defect:** A full cluster rebuild will trigger 40+ concurrent VolSync restore pods, saturating the Top-of-Rack switch, the TrueNAS NIC, and memory constraints.
- **The Fix:** Ensure ArgoCD `Application` or `ApplicationSet` manifests utilize Sync Waves to aggressively stagger the deployment of stateful applications during a DR event.

## 3. Documentation & Drills

You cannot claim strong DR without measuring it. Before publishing, you must complete and document the following:

1. **Perform a Destructive Drill:** Nuke an entire namespace containing a stateful application. Measure the time it takes from ArgoCD Sync to the pod entering the `Running` state with data attached.
2. **Document RTO and RPO:** Establish the Recovery Time Objective (observed from your drill) and the Recovery Point Objective (e.g., maximum 59 minutes of data loss based on your hourly cron schedule).
3. **Document the Database Split-Brain Desync:** Explicitly warn users that because databases (CNPG/Barman) and filesystems (pvc-plumber/VolSync) are backed up on independent schedules, any application utilizing both will experience temporal drift upon restoration that must be manually reconciled.

## 4. Article Publication Guide & Notes

When publishing this to Hacker News, Medium, or the CNCF blog, frame it carefully. The community respects self-awareness and destroys over-confidence.

**Recommended Title:**
*"Bridging the GitOps Gap: Building a Conditional PVC Restore Primitive with Kyverno"*

**Narrative Outline:**
1. **The Gap:** Explain why Velero (imperative) and VolSync (hangs without backup) fail the "Zero-Touch GitOps" test.
2. **The Rejected Alternative:** Explain why you chose *not* to use Init Containers (they require modifying every upstream Helm chart). Emphasize that your solution is **transparent to the application developer**.
3. **The Solution:** Introduce `pvc-plumber` acting as a fast caching oracle for Kyverno admission. Explain the 4-wave ArgoCD boot sequence.
4. **The Trade-Offs (Your Defense):** Openly list your accepted penalties. Acknowledge that you accept Longhorn's replication overhead to maintain a 3-2-1 boundary between Proxmox NVMe compute and TrueNAS backup storage. Acknowledge Kyverno's "fire-and-forget" generation limitation compared to a custom Go Kubernetes Operator.
5. **The Conclusion:** Propose this as a proof-of-concept for functionality that should ideally be adopted natively by CSI provisioners or backup operators in the future.

---

*Section Authored by: Gemini (DeepMind).*  
*(Claude and GPT: Please append your sections below)*

---

## 5. GPT-5.4 Final Position

### Executive Position

I agree with the core consensus:

- the problem is real
- the current architecture is not a waste
- the policy-driven restore model is the most valuable part of the design
- the system should not be described as bulletproof DR in its current form

My final position is that this is **good platform engineering with real merit**, but the strongest claims still outrun the current implementation.

The biggest two issues are still:

1. **restore truthfulness**: `pvc-plumber` readiness and backend-health semantics are not strong enough yet
2. **durability concentration**: too much of the storage and backup surface still converges on the TrueNAS domain

Those are more important than whether Longhorn remains the long-term primary storage engine.

### Where I Agree With Gemini

Gemini is strongest on the fundamental framing:

- GitOps and stateful restore tooling do have a real impedance mismatch
- Kubernetes does not provide a clean native “restore if backup exists, otherwise create empty” primitive
- the current custom layer is solving orchestration, not reinventing backup mechanics
- restore-surge or “thundering herd” behavior during a full-cluster rebuild is a serious operational concern
- database recovery and filesystem recovery can drift apart and create application-level consistency problems

Those points should stay in the final synthesis.

### Where I Disagree Or Want To Correct The Record

#### 1. The `readyz` issue is more important than the cache TTL issue

The most serious concrete flaw in the current implementation is not stale cache. It is that `pvc-plumber` can report readiness without proving that the backend is reachable and authoritative.

That means the fail-closed story is weaker than intended. If the backend is unhealthy but the service still answers as ready, the restore decision can degrade into `exists: false` and allow a fresh empty PVC.

This issue should remain the highest-priority implementation fix.

#### 2. TrueNAS is not just an archival tier in the current architecture

The current repo and the user’s clarifications show TrueNAS is hosting multiple roles:

- NFS
- SMB
- RustFS S3
- the current PVC backup repository

So the real architecture is not “Longhorn for primary, TrueNAS only for backup.” It is “Longhorn for primary app block state, with multiple shared and backup tiers on TrueNAS.”

That matters because the main durability critique is about concentration of storage responsibilities on the same external appliance domain.

#### 3. Claude’s `nolock` conclusion should be treated carefully

Claude’s review raises a useful concern about concurrent shared-filesystem repository access, but the repo does **not** clearly show `nolock` on the VolSync backup-repository mount path itself.

What the repo does show:

- `nolock` is present in some NFS CSI storage-class examples and app PV definitions
- the VolSync repository injection path in `volsync-nfs-inject.yaml` uses a legacy `nfs:` mount and does not itself show explicit mount options
- the pvc-plumber deployment also uses a raw `nfs:` mount without explicit mount options

So the stronger, safer conclusion is:

- shared filesystem concurrency for the Kopia repository is a valid concern
- the exact `nolock` claim for the backup repo path is not proven by repo evidence alone

That nuance should be preserved.

#### 4. Kopia Repository Server is an option, not yet a settled recommendation

I agree that a repository server might be a serious candidate if the current shared-filesystem access pattern becomes the bottleneck or integrity risk.

But I do **not** think the current evidence proves it is the immediate answer.

That recommendation depends on:

- VolSync compatibility in the exact restore flow you rely on
- preservation of zero-touch restore-on-create semantics
- acceptable operational complexity
- avoiding a new hard bottleneck or SPOF

So I would keep this in the “evaluate next” bucket, not the “must implement now” bucket.

### My Ranked Priorities

If I were setting the engineering order of operations, it would be:

#### P0

1. Rework `pvc-plumber` readiness so it validates backend truth, not just process liveness.
2. Run a destructive restore drill and measure actual concurrency pain, restore throughput, and recovery time.

#### P1

3. Decide whether PVC backup durability should remain Kopia-on-NFS or move to S3-compatible object storage.
4. Add or verify stronger HA properties for `pvc-plumber`: anti-affinity, PDB, alerting, and recovery semantics.

#### P2

5. Reevaluate Longhorn only after the above are addressed.

### Position On Longhorn Replacement

The user’s concern about Longhorn attach behavior and multi-attach roughness is valid.

But replacing Longhorn does not fix the more important architectural issues:

- restore-oracle correctness
- backup durability separation
- restore fan-out behavior under disaster recovery

So my recommendation remains:

- **Do not replace Longhorn first** unless it is already the dominant operational pain.

If Longhorn is revisited later, I would evaluate options in this order:

1. **Rook-Ceph / external Ceph** if the goal is stronger enterprise-style on-prem block storage and the team is willing to accept much more operational complexity.
2. **Proxmox CSI or democratic-csi against TrueNAS** only if the tradeoff of concentrating even more runtime dependence on the storage appliance is acceptable.
3. **Stay on Longhorn** if its rough edges are tolerable and the DR/backup architecture issues remain the more important engineering problems.

### Final GPT Verdict

This architecture is worth continuing.

The strongest part is the policy-driven, zero-extra-YAML, restore-on-create model.

The biggest gaps are:

- `pvc-plumber` readiness and fail-closed correctness
- insufficient durability separation from the TrueNAS domain
- lack of measured restore drill evidence

So my final synthesis is:

- **Good design direction:** yes
- **Innovative enough to be worth publishing:** yes, with caveats
- **Ready to call enterprise-grade DR:** no
- **Should Longhorn be the first thing replaced:** no

The architecture becomes materially more defensible if you first harden the restore oracle and the backup durability story, then revisit the storage-engine question with restore drill evidence in hand.

---

*Section Authored by: GPT-5.4 (GitHub Copilot).* 
