# Scheduled Restore Canary

Continuous proof that the DR restore path still works, sitting on top of the
2026-06-02 full-nuke PASS. The canary answers one question on demand:

```text
Can a known test PVC be deleted, recreated from Git with dataSourceRef,
restored by VolSync, and verified byte-correctly?
```

It tests **restore**, not merely backup. A green backup column proves bytes
left the cluster; only a drill proves they come back.

## Components

| Piece | Location |
|---|---|
| Canary app (namespace, PVC, sleeper Deployment) | `my-apps/system/restore-canary/` |
| Drill script | `scripts/restore-canary-drill.sh` |
| Argo Application | `my-apps-restore-canary` (auto-discovered by the my-apps AppSet, wave 6) |

The canary is a normal pvc-plumber v4 managed PVC: namespace gate label, PVC
fuse labels, `tier=manual`, static `dataSourceRef → restore-canary-data-dst`.
pvc-plumber owns the RS/RD; VolSync/Kopia move bytes; the drill only ever
bumps `spec.trigger.manual` strings (the documented "backup now" /
"restore-refresh now" knobs) and deletes/recreates the one canary PVC.

**Why `tier=manual`:** the RS renders `spec.trigger.manual: backup-on-demand`;
a backup fires only when that string changes, so the drill controls backup
timing exactly and there is zero idle mover churn between drills. The
operator never repairs the manual trigger *value* (it only flags a leftover
cron on a manual-tier RS), so drill bumps are not fought.

## What a passing drill proves

1. The sentinel written before the drill was captured in a **Successful**
   Kopia backup (RS manual trigger).
2. The RD can pull that snapshot back from RustFS/S3 and advance
   `status.latestImage` (RD manual trigger).
3. Argo recreates the deleted PVC **from Git** with its `dataSourceRef`
   (verified live on the new object, never via app status).
4. The VolSync volume populator binds the new PVC from `latestImage`.
5. The restored sentinel is **byte-identical** (sha256) and embeds the
   pre-delete PVC UID — the data came from the drill's backup, not an empty
   or stale volume.
6. `/audit` returns to fresh `already-matches` and a post-restore backup
   succeeds (the trigger reset itself fires it).
7. Nothing else changed: the non-canary PVC inventory is fingerprinted
   before/after (VolSync's ephemeral `volsync-*` mover PVCs excluded).

## What it does NOT prove

- App-level restore correctness for real workloads (databases, multi-PVC
  apps, permissions edge cases). It proves the *platform path*, not every
  app's data shape.
- CNPG recovery — separate system (Barman → S3), see
  [CNPG disaster recovery](domains/cnpg/disaster-recovery.md).
- Full-cluster bootstrap ordering — that is the
  [nuke runbook](cluster-dr-nuke-restore-runbook.md)'s acceptance test.
- Offsite/secondary backup copies (not yet built).
- Restores of backups older than the drill's own (it always restores the
  newest snapshot).

## Running it

```bash
# Read-only gates + status (safe anytime):
scripts/restore-canary-drill.sh

# Seed/refresh the sentinel and force a backup + RD refresh (no deletes):
scripts/restore-canary-drill.sh --seed

# The real drill (destructive to the canary PVC ONLY):
scripts/restore-canary-drill.sh --live-run
```

The drill refuses to run unless every preflight gate passes: exact
namespace/PVC identity, all contract labels, live `dataSourceRef`, RS+RD
present and `managed-by=pvc-plumber`, Kopia secret fanned out, `/audit`
`already-matches`. Destructive actions are pinned to hardcoded constants;
a drill-in-progress namespace annotation prevents overlapping runs
(`--force-unlock` clears a stale marker).

Results are recorded as namespace annotations for the pre-nuke checklist:

```text
restore-canary.vanillax.dev/last-drill-time
restore-canary.vanillax.dev/last-drill-result      pass | fail
restore-canary.vanillax.dev/last-drill-commit
restore-canary.vanillax.dev/last-drill-uid-before
restore-canary.vanillax.dev/last-drill-uid-after
```

## The Argo stale-cache hazard (why the drill is shaped this way)

ArgoCD has repeatedly reported `Synced` while live objects were stale, and
`selfHeal` **recreates deleted resources from the stale cached render**
(2026-05-30 tubesync, 2026-06-10 drift-drill incidents). A PVC deleted
before the current render is in cache gets recreated with the OLD spec —
during a drill that could mean a missing `dataSourceRef` and an **empty
restored volume**. The drill therefore always:

```text
hard-refresh app → wait for the refresh annotation to be consumed
→ wait until app revision == origin/main SHA
→ verify the live PVC spec BEFORE deleting
→ explicit SHA-pinned sync after deletion (selfHeal alone is not trusted)
→ verify the recreated live PVC's dataSourceRef, UID, and contents
```

Never gate any step on Argo `Synced` alone.

## First-deploy bootstrap (day-one populator deadlock)

Verified against VolSync v0.17.11 source: the volume populator **waits
forever** for `ReplicationDestination.status.latestImage` and never falls
back to provisioning an empty volume. A brand-new PVC that ships the full
backup contract (including `dataSourceRef`) before any backup exists
deadlocks `Pending`:

```text
bind needs latestImage ← restore needs a snapshot ← backup needs a Bound source
```

This affects ANY genuinely new app that adopts the full contract on day one,
not just the canary. Bootstrap procedure (one-time per new PVC):

1. Pre-create the namespace and the PVC **without** `dataSourceRef`
   (otherwise identical to Git). It binds empty; the operator wires RS/RD.
   The RD's initial `restore-once` sync fails harmlessly until a backup
   exists (expected transient mover errors).
2. Push/let Argo adopt. The AppSet's `ignoreDifferences` +
   `RespectIgnoreDifferences=true` mean Argo never tries to add the
   immutable `dataSourceRef` to the Bound PVC.
3. `scripts/restore-canary-drill.sh --seed` — sentinel + first Successful
   backup + RD `latestImage`.
4. First drill runs with `--live-run --bootstrap`: the delete→Git-recreate
   installs the `dataSourceRef` on the new PVC. Steady state from then on.

## Interpreting failures

| Failure point | Meaning | First moves |
|---|---|---|
| Preflight gate | Contract drift (labels, RS/RD ownership, audit verdict) | Fix via Git/labels; check `/audit` entry; do NOT drill |
| RS backup timeout | Backup path broken (mover, RustFS, MAP gate, Longhorn snapshot) | `kubectl get pods -n restore-canary`, mover logs, RustFS reachability |
| RD sync timeout / latestImage stale | Restore-read path broken (repo auth, snapshot missing) | RD mover logs; Kopia repo health |
| PVC never Bound after recreate | Populator path broken — **this is the alarm the canary exists for** | RD `latestImage`, populator events on the PVC, VolSync controller logs |
| Sentinel hash mismatch | Restore returned wrong/stale bytes — treat as data-loss-class incident | Freeze drills; compare RD latestImage timestamps vs RS lastSyncTime |
| Containment fingerprint changed | Something outside the canary moved during the drill | Investigate immediately before any further drills |

A failed drill leaves `last-drill-result=fail` on the namespace and exits
nonzero. There is no automatic retry — failures must be triaged by a human.

## Cleanup / recovery if a drill dies midway

The drill is single-pass with no destructive retries. Worst case is the PVC
deleted and not yet recreated:

```bash
kubectl annotate ns restore-canary restore-canary.vanillax.dev/drill-in-progress- || true
kubectl get application my-apps-restore-canary -n argocd   # check revision
# hard refresh, then explicit sync (see hazard section) — Argo recreates the
# PVC with dataSourceRef and the populator restores it. Then re-run:
scripts/restore-canary-drill.sh            # gates + status
```

Because the canary holds only a sentinel, the worst possible loss is the
sentinel itself — reseed with `--seed`.

## Scheduling (future, NOT enabled)

The first scheduled mode should be a simple operator-run cadence (e.g.
monthly, or before any risky platform change) using the manual script. An
in-cluster CronJob needs RBAC for PVC delete + Application patch and is
deliberately deferred until several manual drills have passed. Optional
later-wave observability (PrometheusRule on the namespace annotations or a
textfile exporter) must live in a monitoring overlay, never in the canary
app itself — core stays Prometheus-free.

## Related docs

- [Cluster nuke/rebuild/restore runbook](cluster-dr-nuke-restore-runbook.md)
- [VolSync storage recovery](volsync-storage-recovery.md)
- [pvc-plumber cheatsheet](pvc-plumber-cheatsheet.md) (restore drill quick path)
- [Talos ArgoCD pvc-plumber integration](talos-argocd-pvc-plumber-integration.md)
