> [!WARNING]
> Historical document.
> This file is preserved for context only and is not the current runbook.
> Start with: [pvc-plumber-start-here](../../../pvc-plumber-start-here.md) or [docs index](../../../index.md).

# pvc-plumber YouTube Presentation Outline

**Recording guide for the "pvc-plumber v2 operator" YouTube video.**

This doc is the user's script+cheat-sheet, open alongside the recording. Every section maps to one screen/chapter in the video. The *Talking points* are in first-person voice — these are things you say, not narrate.

Cross-references for deep technical content: [pvc-plumber repo docs](https://github.com/mitchross/pvc-plumber/blob/main/docs/).

---

## A. Elevator-pitch cheat sheet

Read this once before recording. These 10 bullets are the backbone of every answer you give in the video.

1. **One label does everything.** `backup: hourly` on a PVC — that's the entire user surface. The system handles backup, restore-on-recreate, and cleanup automatically.
2. **Restore-on-recreate is the headline.** You can nuke the entire Kubernetes cluster, rebuild from Git, and every app comes back with its data already populated — no restore scripts, no ordering choreography.
3. **pvc-plumber v2 replaced Kyverno + a bash CronJob.** Three separate systems (Kyverno policy engine, pvc-plumber HTTP service, 15-min orphan-reaper CronJob) became one Go binary with a reconciler and three admission webhooks.
4. **The motivation was a real incident.** On 2026-04-08 a Kyverno webhook with `failurePolicy: Fail` deadlocked the entire cluster — Longhorn, ArgoCD, everything. The operator's webhook lives in one namespace-scoped pod with a 9-entry exclusion list that prevents the same deadlock from ever happening again.
5. **Fail-closed on the validator, fail-open on the mutator — these have different invariants.** The validator gates against data loss (silent empty volume over restorable data). The mutator just enriches (adds the `dataSourceRef`). Wrong fail policy on either one has different consequences; they're deliberately different.
6. **Get-or-Create idempotency everywhere.** The reconciler doesn't fight you. If you `kubectl apply` a `ReplicationSource` by hand, the operator sees it exists and leaves it alone. If you delete it, the operator recreates it on the next reconcile — improvement over the old Kyverno `synchronize: false` behaviour.
7. **The 9-namespace exclusion list is not paranoia; it's operational history.** `kube-system`, `volsync-system`, `argocd`, `longhorn-system`, `cert-manager`, `external-secrets`, `1passwordconnect`, `snapshot-controller`, `kyverno` — if the operator's fail-closed webhook fires in any of these, ArgoCD and Longhorn deadlock. Been there.
8. **Technical debt is explicit.** The `ExternalSecret` has a hardcoded `secretStoreRef.name: 1password` and `remoteRef.key: rustfs property: kopia_password`. If you have a different 1Password item or a different secret backend, you need to fork the operator. This is documented and deferred to v3.
9. **The v3 roadmap (catalog model + native CEL) exists and was deliberately NOT built yet.** The staleness window in the catalog model — if a backup completes between cache refresh and PVC recreate, the catalog says "Fresh" and you silently lose the restore window — is a real unsolved problem. v2's per-request Kopia call is slower but safe.
10. **SHA256 schedule, not length-mod.** The cron minute for each PVC is `sha256(ns/pvc) % 60`. The old Kyverno formula `len(ns-pvc) % 60` clustered same-length PVC names onto the same minute. Fixed in v2.1. There's a regression-pin test so it stays fixed.

---

## B. Suggested video structure

---

### Section 1 — The Pain

**Slide title**: "Why I blew up my Kyverno setup"

**Talking points**:

- I've been running a production-grade homelab on Talos OS + ArgoCD for a while now. Every app runs in Kubernetes, every app has its data on Longhorn PVCs, and every PVC needs to back up to my TrueNAS.
- The old system worked. Kyverno watched every PVC create, called a little HTTP service called pvc-plumber to ask "does a backup exist?" and either restored from the backup or admitted a fresh empty PVC.
- Then on 2026-04-08, Kyverno's admission controller crashed with `failurePolicy: Fail` registered. What that means: the Kubernetes API server couldn't process any admission webhook calls, and because `failurePolicy: Fail`, it rejected *everything* — new Deployments, StatefulSets, Jobs. Including Longhorn trying to schedule its pods. Including ArgoCD trying to reconcile. The whole cluster froze.
- I had to manually delete the MutatingWebhookConfiguration and ValidatingWebhookConfiguration objects with `kubectl` to break the deadlock — from a laptop with a kubectl kubeconfig, because the cluster was otherwise unresponsive.
- That was the moment I decided Kyverno for this specific use case was the wrong tool. Not Kyverno in general — Kyverno as the admission gate for a fail-closed PVC backup system.
- Three other pain points: (a) Kyverno's `ClusterCleanupPolicy` was silently broken on 1.17/1.18 — orphaned backup resources never got cleaned up, so I had to write a bash CronJob. (b) `background: false`, `synchronize: false`, `mutateExistingOnPolicyUpdate: false` — three footguns specific to the generate+external-HTTP pattern, any of which set wrong causes incidents. (c) Every pvc-plumber admission call was an HTTP round-trip from Kyverno to a separate pod — three calls per PVC (mutate + 2 validate rules). Slower and more fragile than inline.

**Visual to show**: The "Before — three separate systems" graph from `docs/pvc-plumber-walkthrough.md` ("What replaced what" section).

> 🎬 **Camera tip:** Pause on the diagram for 4-5 seconds after bringing it up. Let viewers read the three boxes. Then say "Three systems, all wired together with HTTP calls — and one crash takes down the whole cluster."

**Demo command**: Show the dead-simple YAML that caused all this drama:
```yaml
# The backup contract — unchanged across v1 and v2
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: app-data
  namespace: my-app
  labels:
    backup: hourly
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: longhorn
  resources:
    requests:
      storage: 10Gi
```

**Anticipated questions**:

- *"Couldn't you have just tuned Kyverno better?"* — Yes, probably. But `failurePolicy: Fail` on a general-purpose policy engine that can deadlock the cluster is an operational risk that scales with cluster size. For this specific use case — fail-closed PVC gate — I want a purpose-built binary with a scoped RBAC that can't accidentally deadlock storage.
- *"Is Kyverno bad?"* — No. Kyverno is great for policy-as-code. It's the wrong shape for "one binary that owns the PVC backup lifecycle." Those are different problems.

---

### Section 2 — The Promise

**Slide title**: "One label. Everything just works."

**Talking points**:

- This is the part I want you to internalize before we look at any code. The user surface has not changed from v1 to v2. One label. The system does the rest.
- When you label a PVC `backup: hourly`, here's the full behaviour:
  - If this is a brand-new PVC with no prior backup: it provisions empty, and after it's been Bound for 2 hours, scheduled hourly backups begin.
  - If this PVC had a backup in Kopia (same namespace, same PVC name, different cluster or same cluster after deletion): the new PVC comes back populated with the last backup's data. Automatically. No extra YAML.
  - If the backup check is down or inconclusive: the PVC creation is denied. ArgoCD retries. No silent empty volume.
- There's an escape hatch: `volsync.backup/skip-restore: "true"` + a mandatory reason annotation if you really want to start fresh despite a backup existing. The reason annotation is mandatory because a stale `skip-restore=true` in Git would silently disable restore forever — that's the footgun we're defending against.
- There's also `backup-exempt: "true"` for PVCs you're explicitly choosing not to back up (caches, scratch space, external-sourced data). Also requires a reason annotation. Declarative intent — not just an absent label.

**Visual to show**: The "Phase 1 — Admission" and "Phase 2 — Provisioning" diagrams from `docs/pvc-plumber-walkthrough.md` ("System at a glance" section).

> 🎬 **Camera tip:** Show Phase 1 first, explain the blue/red boxes, then scroll to Phase 2. About 6-8 seconds per diagram. "This is everything that happens before the PVC even exists. Then once it's admitted, the reconciler kicks in."

**Demo command**:
```bash
# Apply the PVC
kubectl apply -f demo/fresh-pvc.yaml

# Watch the operator generate the companion resources
kubectl get externalsecret,replicationsource,replicationdestination \
  -n demo -l volsync.backup/pvc=app-data -w
```

> 📸 **Screenshot opportunity:** Leave the `kubectl get ... -w` output running. Let viewers see the ExternalSecret appear, then the ReplicationDestination. Say "Watch — there's the ES, there's the RD. The RS shows up 2 hours from now once the PVC has data worth backing up."

**Anticipated questions**:

- *"Does 'daily' vs 'hourly' change the retention?"* — No, same retention policy (24 hourly, 7 daily, 4 weekly, 2 monthly). "Daily" just changes the schedule from `<minute> * * * *` to `<minute> 2 * * *`. The cron minute is deterministic: `sha256(namespace + "/" + pvcname) % 60`.
- *"What's the `<pvc>-backup` name pattern for?"* — `ReplicationSource` and `ReplicationDestination` both get named `<pvc>-backup`. They're different resource kinds with the same name. When you `kubectl get` or `kubectl patch` them, always specify the kind — `kubectl get replicationsource app-data-backup -n my-app`. Name collision between kinds is intentional (the name derives from the PVC, not the resource type).

---

### Section 3 — Architecture Overview

**Slide title**: "Four parts, one binary"

**Talking points**:

- pvc-plumber v2 is a single Go binary deployed as a Deployment with replicas=2 and a PodDisruptionBudget in `volsync-system`.
- It runs four things in one process:
  1. **Kopia client** — the same code that was already in v1. Thin wrapper around `kopia snapshot list`. Returns `restore`, `fresh`, or `unknown`. In-memory cache. Shared across all other components.
  2. **PVC reconciler** — controller-runtime reconciler watching PersistentVolumeClaims. Get-or-Create for the three companion resources. Cleanup on PVC delete or label remove. Leader-elected so only one replica runs reconciliation.
  3. **Three admission webhooks** — mutate-pvc (fail-open, injects `dataSourceRef`), validate-pvc (fail-CLOSED, the gate), mutate-job (fail-ignore, injects NFS volume into VolSync mover Jobs). All on port 9443, TLS from cert-manager.
  4. **Original HTTP server** — `/exists` endpoint, kept for backward compat and as the `OPERATOR_MODE=false` rollback path. Not admission-critical in v2.
- The feature flag `OPERATOR_MODE=true/false` is cheap insurance. If the operator misbehaves in production, flip it to `false` in the env var (no redeploy) and the binary reverts to a pure HTTP oracle — the old v1 behaviour. I've never had to use it.
- Why one binary? The Kopia client is expensive to initialize (NFS mount, repository unlock, cache warmup). Sharing it across all components means one startup cost and one in-memory cache. Two separate Deployments would need to coordinate their caches — that's more code than just putting them together.

**Visual to show**: The component diagram from `docs/pvc-plumber-walkthrough.md` ("What does this work now" section) showing the four parts inside the binary boundary.

> 🎬 **Camera tip:** Point at the red box (validating webhook) and say "This is the one that matters most — fail-closed, denies when in doubt." Then point at green (reconciler): "This is what cleans up Kyverno never cleaned up." Pause 4-5 seconds.

**Demo command**:
```bash
# Show the two replicas running
kubectl get pods -n volsync-system -l app.kubernetes.io/name=pvc-plumber -o wide

# Show the webhooks registered
kubectl get mutatingwebhookconfiguration pvc-plumber
kubectl get validatingwebhookconfiguration pvc-plumber

# Show the leader election lease
kubectl get lease -n volsync-system pvc-plumber
```

> 📸 **Screenshot opportunity:** `kubectl get pods -n volsync-system -o wide` — show both replicas Running on different nodes. "replicas=2, PodDisruptionBudget minAvailable=1 — one pod can roll and the webhooks stay up the whole time."

**Anticipated questions**:

- *"Why replicas=2 if the reconciler is leader-elected?"* — The second replica is hot standby for the webhooks. Webhooks don't need leader election; both replicas serve admission traffic. The PDB ensures at least one is always up. If the primary pod crashes, the secondary picks up the leader election lease within seconds AND was already serving webhook traffic throughout.
- *"Could this be split into a separate webhook service and a separate controller?"* — Yes, and that's how most production operators work. I chose one binary for simplicity. For this homelab, "one thing to debug" outweighs "separate scalability." The v3 architecture (catalog model) would likely split them.
- *"What's the RBAC scope?"* — ClusterRole. The reconciler needs to watch PVCs cluster-wide, and needs create/update/delete on ExternalSecrets, ReplicationSources, ReplicationDestinations across all namespaces. The webhook server just processes AdmissionReview objects — no cluster access needed for that part specifically.

---

### Section 4 — The Killer Feature: Restore-on-Recreate

**Slide title**: "Delete your cluster. It comes back."

**Talking points**:

- I'm going to delete an app that has data. Watch what happens when I re-add it from Git.
- Before I do, I want you to understand *why* this works. The key is: the `ReplicationDestination` that the operator created earlier — that object still exists even after the PVC is deleted. It points at the Kopia snapshot for this specific `namespace/pvcname`. VolSync is watching it.
- When ArgoCD recreates the PVC with `backup: hourly`, the operator's mutating webhook fires first. It checks Kopia: "does `my-app/app-data` have a backup?" Kopia says yes. The webhook injects `dataSourceRef` pointing at `my-app/app-data-backup` (the ReplicationDestination). The PVC is then admitted with that dataSourceRef set.
- Kubernetes VolumePopulator then kicks in: "this PVC has a dataSourceRef pointing at a ReplicationDestination, let VolSync populate it." VolSync runs `kopia restore` into the new Longhorn volume. The PVC binds with all the prior data intact.
- The app starts. It sees its data. Nothing is missing. This is the whole point.

**Visual to show**: The "Part 1 — operator decides restore" sequence from `docs/pvc-plumber-walkthrough.md` ("Restore on PVC recreate" section). Then Part 2.

> 🎬 **Camera tip:** Show Part 1 (admission) while saying "This all happens in about 200 milliseconds." Show Part 2 (VolSync restore) while saying "And this takes however long it takes Kopia to restore from NFS — usually a few seconds to a minute depending on data size." Pause 5 seconds on each.

**Demo command**:
```bash
# Delete the app (simulating "oops" or cluster rebuild)
kubectl delete namespace demo

# Verify the backup exists in Kopia (operator side)
kubectl exec -n volsync-system deploy/pvc-plumber -- \
  kopia snapshot list --json | jq '.[] | select(.source.path == "/demo/app-data")'

# Re-add from Git (or just kubectl apply again)
kubectl apply -f demo/

# Watch the restore happen in real time
kubectl get pvc -n demo -w &
kubectl get replicationdestination -n demo app-data-backup -w
```

> 📸 **Screenshot opportunity:** The moment `kubectl get pvc -n demo -w` shows the PVC go from Pending → Bound. Say "There it is. PVC went Pending, VolSync populated it from the Kopia snapshot, now it's Bound. The app gets its data back. I didn't type a single restore command."

**Anticipated questions**:

- *"What if the namespace is different on rebuild?"* — Kopia snapshots are tagged by `namespace/pvcname`. If you change the namespace or PVC name, pvc-plumber won't find the old backup. The matching is exact. Plan accordingly.
- *"What about the 2-hour wait for ReplicationSource creation?"* — The RD (restore handle) is created immediately. The RS (backup schedule) waits for Bound + 2h. So during a restore, you get data back immediately but scheduled backups don't start until 2h after the PVC binds. This prevents the classic race: fresh empty volume → immediate backup snapshot → "successfully" backed up an empty volume.
- *"Can I trigger a restore without deleting the PVC?"* — Yes, manually trigger the ReplicationDestination: `kubectl patch replicationdestination app-data-backup -n my-app --type merge -p '{"spec":{"trigger":{"manual":"restore-now"}}}'`. But deleting and recreating the PVC gives you a clean slate + automated restore in one operation.

---

### Section 5 — The Fail-Closed Gate

**Slide title**: "Unknown = Deny. Always."

**Talking points**:

- Let's talk about the validating webhook and why it's designed the way it is.
- The invariant the whole system protects: *a PVC labeled `backup: hourly|daily` must never bind to an empty volume when backup truth is unknown.*
- The validator has `failurePolicy: Fail`. If pvc-plumber is unreachable — pod crashed, NFS down, whatever — Kubernetes denies the PVC creation. ArgoCD retries with exponential backoff. No empty volume gets created over restorable backup data.
- The 9-namespace exclusion list is what makes this safe: `kube-system`, `volsync-system`, `argocd`, `longhorn-system`, `cert-manager`, `external-secrets`, `1passwordconnect`, `snapshot-controller`, `kyverno`. These namespaces are never gated by the validator. If pvc-plumber crashes, infrastructure can still run — Longhorn can schedule, ArgoCD can mount its PVC, ESO can sync. The cluster degrades gracefully instead of deadlocking.
- The mutator has `failurePolicy: Fail` too — but the *logic* inside the mutator is fail-open. If the Kopia check errors, the mutator just returns "allow, no patch." It's the validator that enforces the contract, not the mutator. They have different invariants: mutator enriches, validator gates.
- The Job mutating webhook has `failurePolicy: Ignore`. If NFS injection fails for a VolSync mover Job, that one backup fails. That's acceptable. Failing closed here would block ALL backups during a pvc-plumber blip, which is worse than one missed backup.
- Three different failure modes for three different risk profiles: fail-closed (validator), fail-closed-logic-open (mutator), fail-ignore (job mutator). This is intentional design, not inconsistency.

**Visual to show**: The "What if the operator is down during the restore?" sequence diagram from `docs/pvc-plumber-walkthrough.md`. (4 participants — already compact and readable.)

> 🎬 **Camera tip:** This diagram is short — pause 3-4 seconds. The key thing to point at is the "DENY" arrow and say "That's it. That's the whole point. The cluster says no, ArgoCD queues a retry, nobody gets an empty volume."

**Demo command**:
```bash
# Simulate operator outage — scale down pvc-plumber
kubectl scale deploy pvc-plumber -n volsync-system --replicas=0

# Try to create a backup-labeled PVC
kubectl apply -f demo/fresh-pvc.yaml
# Should get: admission denied

# Check what the denial message says
kubectl describe pvc app-data -n demo

# Scale it back
kubectl scale deploy pvc-plumber -n volsync-system --replicas=2
```

> 📸 **Screenshot opportunity:** `kubectl describe pvc app-data -n demo` showing the "admission denied" event. Show the exact message from the validator. Say "This is the message you'll see. Read it — it tells you exactly why. 'decision=unknown, authoritative=false.' The operator couldn't reach Kopia, so it said no."

**Anticipated questions**:

- *"What if my cluster has a network partition and pvc-plumber can't reach NFS, but I urgently need to deploy an app?"* — Two options: (a) annotate the PVC with `volsync.backup/skip-restore: "true"` + a reason, which bypasses the Kopia check and admits a fresh empty volume. (b) For namespaces in the exclusion list, no gating applies anyway. For everything else, you're accepting the "I want this fenced" contract by putting a `backup` label on the PVC.
- *"Why can't the validator just warn instead of deny?"* — Warning admission (the `warn` admission response) would still admit the PVC. The whole point is to not admit an empty PVC over restorable data. Once a PVC is admitted and bound to an empty volume, VolSync's restore path (`dataSourceRef`) is closed — you'd have to delete and recreate. The invariant only holds at PVC creation time.

---

### Section 6 — The Migration Story

**Slide title**: "7 Kyverno rules → 1 reconciler + 3 webhooks"

**Talking points**:

- The migration from Kyverno to pvc-plumber v2 was a single ArgoCD sync, not a phased rollout. Let me explain why and what made that possible.
- In my original design doc I had a 4-phase plan: build alongside Kyverno, deploy alongside Kyverno with reconcile-only mode, flip webhooks, cleanup. I threw that plan away because for a single-operator homelab, "rollback" means `git revert + argocd sync`, not "switch back to the old system." A coexistence period just means two systems fighting over who owns the ES/RS/RD objects.
- What made a single-cutover safe: (a) the operator's `ensure*` methods are Get-or-Create — existing Kyverno-created resources are left alone. (b) The operator's cleanup uses the same label selector Kyverno used (`volsync.backup/pvc=<pvc>`). So Kyverno-created resources get reaped correctly when a PVC is deleted or its label removed. (c) VolSync doesn't care who created the ReplicationSource — once it exists, VolSync owns the backup schedule.
- The merge ordering was the only real prerequisite: first merge the operator binary PR in the pvc-plumber repo so CI pushes the image to GHCR. Then merge the cluster PR that deploys the new operator manifests AND deletes the Kyverno policies in the same ArgoCD sync. No race.
- What changed for end users: nothing. Same label. Same backup schedule minute (even the old `len(...)` formula runs the same as before for existing PVCs; SHA256 only applies to new ones created by v2.1+). Same skip-restore annotation. Same troubleshooting flow.
- v1 → v2 is a major version bump in semver. The image went from `1.7.0` to `2.0.0-rc1`. The HTTP `/exists` API is unchanged. The webhook API changed (it's now Kubernetes AdmissionReview, not a custom HTTP protocol). CHANGELOG.md documents both.

**Visual to show**: The "Before — three separate systems / After — one binary" graph from `docs/pvc-plumber-walkthrough.md` ("What replaced what" section), then the replacement table below it.

> 🎬 **Camera tip:** Point at the left subgraph: "Three processes, HTTP calls between them." Point at the right: "One binary. The Kopia call happens inline." Pause on the table for 6-8 seconds — it's dense but useful for viewers who know Kyverno. "Every row in that table is something I deleted."

**Demo command**:
```bash
# Show the operator is running
kubectl get pods -n volsync-system -l app.kubernetes.io/name=pvc-plumber

# Show Kyverno is gone
kubectl get namespace kyverno 2>&1  # should say "not found"
kubectl get clusterpolicy 2>&1      # should say CRD not found or empty

# Show operator-managed resources on a real PVC
kubectl get externalsecret,replicationsource,replicationdestination \
  -n my-app -l app.kubernetes.io/managed-by=pvc-plumber
```

> 📸 **Screenshot opportunity:** `kubectl get namespace kyverno` returning "not found" — clean and satisfying. Then `kubectl get clusterpolicy` returning "the server doesn't have a resource type 'clusterpolicies'". Both in the same terminal. "It's just gone."

**Anticipated questions**:

- *"Why not use Helm for the operator?"* — The operator is deployed via Kustomize in ArgoCD. I'm already using Kustomize for everything else in the cluster. Adding a Helm chart for one in-house operator would be scope creep. If pvc-plumber were a community project, I'd wrap it in Helm.
- *"What's the CHANGELOG look like?"* — [github.com/mitchross/pvc-plumber/CHANGELOG.md](https://github.com/mitchross/pvc-plumber/blob/main/CHANGELOG.md). Breaking changes are clearly called out. The v2.0 section lists the removed HTTP endpoints and the new webhook API shape.
- *"What if someone is still using v1?"* — v1 is still there on the `1.x` branch. The v2 image is backward-compatible in HTTP mode (`OPERATOR_MODE=false`). The actual breaking change is the removal of Kyverno as the caller — if you were using Kyverno with the v1 HTTP API, you need to either (a) keep using v1, or (b) adopt the operator and delete the Kyverno policies.

---

### Section 7 — What's Next

**Slide title**: "The roadmap (honest version)"

**Talking points**:

- Let me be honest about what's done, what's planned, and what's deferred.
- **Done (v2.0)**: operator binary, Get-or-Create reconciler, three webhooks, single-cutover migration, Kyverno fully removed, `longhorn-pvc-backup-audit` replaced with a PrometheusRule.
- **Coming in v2.1** (PR already open): SHA256 schedule spread replacing `len(...)%60`. The `backup-exempt` label + reason annotation contract (currently undocumented but the handler short-circuits correctly). Minor fixes.
- **v2.2 stretch goals**: `PVCProtection` CRD — a per-PVC status object that would give you `kubectl get pvcprotection -A` to see every backup's last run, next scheduled run, and any errors. Operator-owned Kopia maintenance (consolidate the `kopia-maintenance-cronjob.yaml` CronJob into the operator binary). Both are nice-to-have but not blocking.
- **v3 (deferred, explicitly)**: catalog model + native CEL `MutatingAdmissionPolicy`. A `PVCBackupCatalog` CR refreshed periodically from Kopia, read by CEL admission rules instead of per-request Kopia calls. This would eliminate the Kopia round-trip on every PVC create. The blocker: the catalog has a staleness window — if a backup completes between refresh ticks AND a PVC is recreated in that window, the catalog could say "Fresh" and you'd silently lose the restore window. The v3 roadmap doc (`docs/plans/pvc-plumber-v3-roadmap.md`) describes what write-through invalidation from the backup trigger path would look like. Not built yet because the safe version is more code than the benefit justifies for ~40 PVCs.
- **What's NOT happening**: multi-cluster federation, continuous data protection (RPO < 1h), backup-to-S3 (NFS is faster and deduplicates across PVCs), application-consistent backups for stateful databases (that's CNPG + Barman, a completely separate system).

**Visual to show**: Show the bullet list on screen (no mermaid needed — it's a roadmap, not a flow).

> 🎬 **Camera tip:** Read out the v2.1 / v2.2 / v3 bullets. Be honest about v3's staleness problem — it builds more credibility than glossing over it. "v3 is better in theory but has a bug I haven't solved yet." Viewers respect that.

**Demo command**:
```bash
# Show what v2.1 SHA256 schedule looks like
# (deterministic but not clustered)
echo "karakeep/data-pvc" | sha256sum | python3 -c "
import sys; h=int(sys.stdin.read().strip().split()[0],16); print(f'{h%60} * * * *')
"
# outputs: <minute> * * * *  (same minute every time for this PVC)
```

> 📸 **Screenshot opportunity:** Run the SHA256 script for two or three of your real PVC names. Show that each one gets a different minute. "It's deterministic — same PVC, same namespace, always the same minute — but distributed. Compare that to length-mod-60 where all 8-character PVC names hit the same slot."

**Anticipated questions**:

- *"When does v3 ship?"* — When Talos ships a Kubernetes version with stable `MutatingAdmissionPolicy` AND someone (probably me) solves the write-through invalidation problem. No timeline.
- *"Is the `PVCProtection` CRD going to be a custom CRD or use a standard API?"* — Custom CRD, similar to `VolumeSnapshot` or `ReplicationSource`. The goal is `kubectl get pvcprotection app-data -n my-app -o yaml` showing `lastBackup`, `nextBackup`, `healthy: true/false`.
- *"Could you just use Velero?"* — Velero is great for namespace-level snapshots and migration. pvc-plumber's value is per-PVC granularity + automatic restore-on-create (no manual restore step). They're complementary, not competing.

---

### Section 8 — Q&A

**Slide title**: "Questions?"

**Pre-anticipated questions to have ready**:

- *"Can I use this without ArgoCD?"* — Absolutely. The operator is a normal Kubernetes Deployment. `kubectl apply -f` the manifests in `infrastructure/controllers/pvc-plumber/`. ArgoCD is just how this cluster manages the operator's lifecycle.
- *"What if my NFS goes down?"* — If NFS is down at admission time, the Kopia check returns `unknown`, and the validating webhook denies PVC creation. ArgoCD retries. This is by design — you don't want empty volumes initialized over restorable data during a storage incident. Fix NFS → ArgoCD retries → backups resume.
- *"How do I know what minute my PVC's backup is scheduled for?"* — `kubectl get replicationsource <pvc>-backup -n <ns> -o jsonpath='{.spec.trigger.schedule}'`. Or compute it: `sha256(namespace + "/" + pvcname) % 60`.
- *"Is the Kopia encryption key per-PVC or shared?"* — One shared encryption key for the entire Kopia repository. All PVCs in all namespaces share one repo on NFS. The ExternalSecret per PVC just fetches the shared `KOPIA_PASSWORD` from 1Password. Single blast radius — if the password leaks, all backups are decrypted. Acceptable for a LAN-only backup system.
- *"What's the ExternalSecret hardcoded to 1Password?"* — Yes. `secretStoreRef.name: 1password`, `remoteRef.key: rustfs property: kopia_password`. If you use Vault, sealed-secrets, or a different 1Password item name, you need to fork the operator or patch the reconciler's `ensureExternalSecret` function. This is called out in the code as technical debt deferred to v3.
- *"Does pvc-plumber work with RWX (ReadWriteMany) PVCs?"* — The operator doesn't distinguish RWO vs RWX. VolSync's Kopia mover requires a snapshot for `copyMethod: Snapshot`, which requires the StorageClass to support VolumeSnapshots. Longhorn supports this for RWO. NFS-backed RWX PVCs (via NFS CSI driver) do NOT support VolumeSnapshot — those PVCs should not carry a `backup` label.
- *"What's the `volsync-<pvcname>` ExternalSecret for specifically?"* — It provides the `KOPIA_PASSWORD`, `KOPIA_REPOSITORY`, and `KOPIA_FS_PATH` secrets to the VolSync mover Job. VolSync's Kopia mover needs these environment variables to authenticate to and locate the Kopia repository.

---

## C. Recording checklist

Before recording:
- [ ] `kubectl get pods -n volsync-system` — operator running, 2/2
- [ ] `kubectl get pods -n argocd` — ArgoCD healthy
- [ ] Demo namespace with a fresh PVC ready: `kubectl apply -f demo/`
- [ ] Terminal font size: 18pt minimum for screen recording
- [ ] Have `docs/pvc-plumber-walkthrough.md` open in a browser tab for diagram references
- [ ] Have the pvc-plumber repo open: [github.com/mitchross/pvc-plumber](https://github.com/mitchross/pvc-plumber)

After recording:
- [ ] Chapters in video description (one per section title above)
- [ ] Link to this repo's `docs/` in video description
- [ ] Link to pvc-plumber repo in description
- [ ] Pin a comment with the `backup: hourly` YAML snippet

---

## D. Technical debt to mention on camera (credibility points)

Being honest about rough edges builds more trust than glossing over them:

| Known issue | What to say |
|---|---|
| ExternalSecret hardcoded to 1Password | "If you're using Vault or a different secret backend, you'll need to fork the operator. This is documented technical debt — v3 will make the secret backend configurable via operator config." |
| `kyverno` in the 9-namespace exclusion list | "I kept `kyverno` in the exclusion list even though Kyverno is removed. Costs nothing, and if Kyverno is ever reinstalled for something unrelated, the deadlock prevention is already there." |
| SHA256 schedule only in v2.1 | "v2.0 still uses the old length-based schedule formula inherited from the Kyverno policy. If you install v2.0, PVC names of similar length will cluster on the same minute. v2.1 fixes this with SHA256." |
| Per-request Kopia calls (latency) | "Every PVC admission costs one Kopia round-trip from the mutating webhook and one from the validating webhook. On a slow NFS or after a cold cache start, this can take a few seconds. The v3 catalog model would fix this, but has its own staleness tradeoffs." |
| One shared Kopia password | "One password for all PVCs means if it leaks, every backup is decryptable. This is deliberate for a LAN-only system. Don't adopt this pattern if backups leave your network." |
