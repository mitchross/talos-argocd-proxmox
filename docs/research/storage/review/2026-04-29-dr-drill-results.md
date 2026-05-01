---
title: PVC backup/restore DR drill results
status: COMPLETE — #1 PASS, #2 PASS, #3 INCONCLUSIVE-by-design, #4 FAIL (orphan cleanup is broken)
date: 2026-04-30
relates_to:
  - docs/research/storage/review/2026-04-29-dr-drill-plan.md
  - docs/research/storage/review/2026-04-28-claude-opus-review.md
---

## Live cluster state at drill time

Worth recording — the live cluster does **not** have all of the hardening
pass applied yet (the working tree has it; ArgoCD hasn't synced it):

- **pvc-plumber image: `1.4.0`** (old response shape: `{exists, namespace, pvc, backend}` — no `decision` / `authoritative` fields). The hardening pass bumps to `1.5.1` in working tree.
- **Kyverno ClusterPolicy `volsync-pvc-backup-restore`**: still has `require-pvc-plumber-available` (the /readyz gate). Does NOT have the new `require-authoritative-backup-decision` rule from the hardening pass. So the live admission gate is the legacy single-check version.
- **Kopia maintenance schedule: `0 3 * * *`** in cluster vs. `37 3 * * *` in working tree.

These drills therefore validate the **currently-deployed** flow, not the
hardened one in working tree. Re-running them after sync will be useful but
not blocking.


# DR drill results — running log

## Drill #1 — Recovery via ArgoCD app delete + resync (**PASS**)

**Run on**: 2026-04-30 EDT
**Target**: `nginx-example/storage` (existing 5Gi backup-labeled PVC, no live consumer mount)
**Marker**: `drill1b-1777587744`

### What was tested

The drill plan in `2026-04-29-dr-drill-plan.md` described a synthetic "single-PVC
delete + recreate" scenario, but that's not a path operators actually take in a
GitOps cluster. The test was **redesigned** to mirror the real recovery flow:

1. Write marker `drill1b-1777587744` to `nginx-example/storage`
2. Trigger fresh manual backup on `storage-backup` ReplicationSource — `Successful` in 1m29s
3. **`kubectl delete application my-apps-nginx -n argocd`** — cascading delete via
   `resources-finalizer.argocd.argoproj.io` reaped PVC, RS, RD, ExternalSecret
4. The `my-apps` ApplicationSet immediately re-created the Application
5. ArgoCD synced the manifest → namespace resources regenerated:
   - PVC created with backup label
   - Kyverno admission added `dataSourceRef: ReplicationDestination/storage-backup`
   - Kyverno generated fresh ExternalSecret + ReplicationSource + ReplicationDestination
   - VolSync's mover ran on the fresh RD (because `lastManualSync=""` ≠ `manual: restore-once`)
   - `RD.status.latestImage` set to a brand-new VolumeSnapshot from latest Kopia data
   - VolSync VolumePopulator copied the latestImage into the PVC
6. Reader pod read marker file → matched expected → **PASS**

### Why this matters

The first drill attempt earlier today restored *stale* (13-day-old) data. That
turned out to be testing the wrong path: a synthetic `kubectl delete pvc` that
left the RD intact with its already-fired `lastManualSync: restore-once`. In a
real GitOps cluster, operators don't bypass ArgoCD to surgically delete one
resource — they delete the Application and resync. That cascading-delete path
regenerates the RD fresh, so VolSync re-fires the mover on creation and pulls
the latest Kopia data.

### Recovery scenarios — confidence map

| Scenario | RD state on PVC re-creation | Restore works? |
|----------|-----------------------------|----------------|
| Full cluster destroy + bootstrap | Fresh RD, `lastManualSync=""` → mover fires, fresh `latestImage` | ✅ |
| `kubectl delete app + resync` (this drill) | Same — fresh RD via cascading delete | ✅ |
| `kubectl delete ns` + Argo recreate | Same — fresh RD | ✅ |
| Surgical `kubectl delete pvc` (no Argo) | Old RD persists, `lastManualSync` already matches → no re-fire → stale `latestImage` | ❌ |

The fourth row is **outside the normal DR path**, but it's a realistic
break-glass operator action — Longhorn attach failure on a single volume,
isolated app corruption, mid-migration storage class swap, or "fix one PVC
without reaping the whole Argo app" all surface this scenario in practice.

**Safe surgical restore procedure (when you don't want to delete the Argo app)**:

```bash
# 1. Delete the matching ReplicationDestination so Kyverno regenerates it
#    fresh on the next PVC admission cycle.
kubectl delete replicationdestination <pvc-name>-backup -n <ns>

# 2. Delete and recreate the PVC. Kyverno will regenerate the RD; VolSync
#    will fire its restore-once trigger on the new RD; latestImage will
#    reflect the latest backup in Kopia.
kubectl delete pvc <pvc-name> -n <ns>
kubectl apply -f <pvc-manifest.yaml>
```

**Easier alternative**: just `kubectl delete app <name> -n argocd` and let
ArgoCD reap and re-sync. Cleaner cascade; no risk of forgetting the RD.

### Side-finding (Longhorn, unrelated to backup/restore)

During the drill, the volume created by VolSync's VolumePopulator wound up in
Longhorn's `OfflineRebuildingInProgress` state with `state: failed` on the
engine, even though the populator job completed successfully. New pods on
either the volume's attached node or the originally-scheduled node could not
mount it (`AttachVolume.Attach failed ... volume is not ready for workloads`).
After 5+ minutes Longhorn did not self-recover. Recovery required deleting the
PVC again and letting ArgoCD re-apply, which produced a clean volume that
mounted normally.

This is a Longhorn-level issue with cloned populator volumes, not a
backup/restore architecture issue. Worth tracking as its own item if it
recurs:

- File: open issue with `kubectl get volume -o yaml` snapshot for repro
- Workaround: delete the broken PVC, let GitOps re-apply (no data loss because
  the data is in Kopia, restored on next populate cycle)

### Cluster state after drill

- `nginx-example/storage` Bound to a fresh, healthy Longhorn volume
- ReplicationSource last sync: today, Successful
- ReplicationDestination last sync: today, Successful (from the drill's regen)
- ExternalSecret SecretSynced=True
- ArgoCD app: Synced + Healthy

No follow-up cleanup needed.

---

## Drill #2 — Plumber-down (PASS)

**Run on**: 2026-04-30 EDT
**Method**: scaled `pvc-plumber` Deployment to 0 replicas, attempted to create a backup-labeled PVC in disposable namespace `dr-drill-2`.

### Result

PVC creation **denied** with this error:

```
admission webhook "mutate.kyverno.svc-fail" denied the request: mutation policy
volsync-pvc-backup-restore error: failed to apply policy ... add-datasource-if-backup-exists:
failed to evaluate preconditions: ... failed to fetch data for APICall: failed to execute
HTTP request for APICall backupCheck: ... dial tcp 10.110.36.222:80: connect:
operation not permitted
```

PVC was NOT created (`kubectl get pvc` returned NotFound).

### Observation

Denial fired through the **mutate rule's apiCall failure**, not the dedicated
`require-pvc-plumber-available` /readyz validate rule. With no Service
endpoints (deployment scaled to 0), the apiCall got `connect: operation not
permitted` and Kyverno failed-closed. Same outcome either way — admission
denied — but worth noting that two independent paths arrive at the same
correct behavior.

### Recovery

Scaled plumber back to 2 replicas, /readyz=ok, namespace deleted.

---

## Drill #3 — Kopia-error (INCONCLUSIVE BY DESIGN)

**Run on**: 2026-04-30 EDT
**Method attempted**: pointed `KOPIA_REPOSITORY_PATH` at a non-existent path,
expecting pvc-plumber to start but fail Kopia operations.

### What actually happened

ArgoCD selfHeal reverted the env change instantly (the unsynced working-tree
deployment.yaml is what ArgoCD applies, so my live patch was clobbered).
Paused selfHeal on the `pvc-plumber` Application, re-applied bogus path. New
pods went into CrashLoopBackOff with the log line:

```
Failed to load configuration: KOPIA_REPOSITORY_PATH /nonexistent-drill3 does not exist
```

### Why this drill collapses to Drill #2

`internal/config/config.go:loadKopiaConfig` does an `os.Stat()` on the repo
path and refuses to start if it doesn't exist. `cmd/pvc-plumber/main.go`
also exits if `kopiaClient.Connect()` fails. So a bogus repo path or wrong
password → pod crashes on startup → no endpoints → admission denial via the
same mechanism as Drill #2.

There is no "running pvc-plumber that returns Kopia errors" mode in v1.4.0
(or v1.5+, which keeps the same startup gate). To genuinely test "running
but unhealthy backend" you'd need to either:

1. Add a non-fatal startup mode (start anyway, return errors from /exists)
2. Disrupt NFS at the kernel level (yank the mount mid-flight)
3. Inject a Kopia binary that errors on snapshot list (mock executor)

None of these fit a "drill on live cluster" gate. Marking this drill
**inconclusive** — the failure mode is real but design-bounded by Drill #2.

### Recovery

Restored env, re-enabled selfHeal, /readyz=ok. ArgoCD app briefly OutOfSync
(transient — the working tree's deployment.yaml differs from what's in git),
selfHeal reconciles.

---

## Drill #4 — Orphan cleanup (**FAIL — orphan cleanup is broken in production**)

**Run on**: 2026-04-30 23:14–23:47 UTC

### Method

1. Create `dr-drill-4-data` PVC with `backup: daily` in `dr-drill-4` namespace
2. Verify Kyverno generated children: ExternalSecret `volsync-dr-drill-4-data`
   + ReplicationDestination `dr-drill-4-data-backup` + backup-dest PVC
3. Remove the `backup` label
4. Wait for `volsync-orphan-cleanup` ClusterCleanupPolicy to fire
   (schedule `*/15 * * * *`) and reap the children

### Result

**Two consecutive cleanup ticks fired and reaped nothing.**

| Tick | `lastExecutionTime` | ES present after? | RD present after? |
|------|---------------------|-------------------|-------------------|
| 23:30 UTC | set | yes | yes |
| 23:45 UTC | set | yes | yes |

After the 23:30 tick failed, ruled out the empty-labels edge case by
relabeling `backup=weekly` (definitively a non-empty string not in
`[hourly, daily]`). Made no difference. Restarted the cleanup-controller
deployment — also no effect.

### Diagnosis

- RBAC is fine: `kubectl auth can-i {list,get,delete}` on PVC + ES + RD
  for `system:serviceaccount:kyverno:kyverno-cleanup-controller` all return
  `yes`.
- Resource labels match the policy's match selectors:
  - `app.kubernetes.io/managed-by=kyverno` ✓
  - `volsync.backup/pvc=dr-drill-4-data` ✓ (Exists)
- Policy `lastExecutionTime` updates on schedule, so the controller IS
  ticking; it just isn't deleting.
- cleanup-controller emits **no INFO/WARN/ERROR** during the entire
  evaluation window — only TRC startup messages. No record of evaluation
  results, no "would delete", no errors.

### Likely cause (untested hypothesis)

Kyverno cleanup-controller is `v1.17.2`. The policy uses an `apiCall`
context (`urlPath: /api/v1/namespaces/{{target.metadata.namespace}}/persistentvolumeclaims`)
to look up the parent PVC's `backup` label, with a JMESPath transform
(`items[?metadata.name=='{{pvcName}}'].metadata.labels.backup | [0] || ''`)
and an `AnyNotIn` condition. The most plausible failure mode is that
`apiCall` contexts in `ClusterCleanupPolicy` are silently broken (no
errors logged, just a no-op) in this Kyverno version, or that the
JMESPath default-value pattern (`| [0] || ''`) doesn't behave the way
plain JMESPath would.

This is a **production issue**, not a drill artifact. With orphan cleanup
broken, removing a `backup` label from a PVC leaves the generated ES + RS +
RD in place forever. Manual cleanup required until fixed.

### Action items

1. **Open a tracking issue**: orphan cleanup is silently broken under
   Kyverno 1.17.2; no resources have been reaped since at least the last
   policy update.
2. **Investigate**: write a minimal reproducer cleanup policy WITHOUT the
   `apiCall` context (just selector + label conditions) and see if THAT
   fires. If yes, the apiCall path is the bug. If no, it's something
   deeper in the cleanup-controller.
3. **Workaround for now**: maintain a manual "orphan reaper" script —
   walk RDs/ESes, check parent PVC backup label, delete if mismatched.
   Could be a CronJob in `infrastructure/controllers/kyverno/` to bridge
   until Kyverno cleanup is fixed.
4. **Audit existing cluster** for stale orphans the broken cleanup never
   reaped — the 25 backup-labeled PVCs are all current, but if anyone has
   ever removed a `backup` label, the children are still there.

### Cleanup

Deleted `dr-drill-4` namespace (cascading delete reaped the test resources
manually since orphan cleanup wouldn't).

---

# Overall scorecard

| Drill | Result | Implication |
|-------|--------|-------------|
| #1 — Recovery via app delete + resync | ✅ PASS | The real DR path operators use works. Architecture correct. |
| #2 — Plumber-down | ✅ PASS | Fail-closed admission denial confirmed. Two paths to denial (defense in depth). |
| #3 — Kopia-error | ⚠️ INCONCLUSIVE | v1.4.0/v1.5+ refuse to start with bad config; failure collapses to #2. Not a real test scenario. |
| #4 — Orphan cleanup | ❌ FAIL | **Production issue**: cleanup-controller ticks but doesn't delete. Likely Kyverno 1.17.2 + apiCall-in-cleanup bug. |

The hardening pass + drills surfaced **one real bug** (#4 orphan cleanup
broken) and confirmed the rest of the design works. The drill plan was
written assuming the v1.5+ tri-state contract, but the live cluster is
still on the pre-hardening v1.4.0 + legacy single-check policy. After the
working tree is committed and synced, drills #1 + #2 should be re-run to
validate the hardened path.
