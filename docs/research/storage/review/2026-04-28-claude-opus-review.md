# Review of Codex GPT-5.5 Storage/Backup Plan

Reviewer: Claude Opus 4.7 (1M context)
Date: 2026-04-28
Scope reviewed:
- `2026-04-28-draft-evaluation.md`
- `2026-04-28-current-flow-hardening-plan.md`
- `2026-04-28-protected-pvc-controller-prd.md`
- `2026-04-28-working-notes.md`
- Code/manifests they claim to have shipped (verified against repo state and pvc-plumber source)

## TL;DR

Codex's review is **good and largely correct**. The architectural verdict ("keep the custom layer, harden the boundary") is right, the tri-state contract is the right model, and the immediate hardening pass it actually shipped — pvc-plumber tri-state, Kyverno Enforce, Kopia default-safe maintenance, ServiceMonitor + alerts — does what it claims. I verified the code/manifests, not just the prose.

There are a handful of things to fix or watch before sleeping easy on this:

1. **Two CEL policies are dead code in the repo** — `volsync-pvc-validate.yaml` and `volsync-pvc-mutate.yaml` exist but aren't in `kustomization.yaml`. Pick one path or delete them.
2. **`VolSyncRestoreTooLong` alert is almost certainly broken** — it filters on `volumeattributesclass=~".*volsync.*"` which doesn't exist for VolSync VolumePopulator-restored PVCs.
3. **Three sequential pvc-plumber HTTP calls per PVC CREATE** — could hit Kyverno's webhook timeout during rebuild storms.
4. **The "Definition of Done" drills are still TODO** — no live `pvc-plumber-down`, no Kopia-error, no actual restore drill has been run. The design is paper until then. Do the drills before writing controller code.
5. **The PRD is a good sketch but underestimates the controller effort.** Don't start it until the bridge is drilled.

The rest of this doc justifies each.

## Verification: Did Codex Actually Ship What It Claims?

Walked the diff against the working-notes "implementation update" section. Spot checks:

| Claim | Reality |
|---|---|
| pvc-plumber tri-state response | Yes — `internal/backend` defines `DecisionRestore/Fresh/Unknown`, kopia client returns `Authoritative: false` on exec or JSON parse error (`internal/kopia/client.go:89-114`) |
| `/exists` returns 503 on unknown | Yes — `internal/handler/handler.go:135-137` writes 503 when `Error != ""`, `!Authoritative`, or `Decision == Unknown` |
| `HTTP_TIMEOUT` wraps backend call | Yes — `handler.go:113-117` does `context.WithTimeout` on the request context, `kopia.client.Run` uses `exec.CommandContext` |
| Cache stores only authoritative non-error | Yes — `internal/cache/cache.go:93` |
| Image pinned to 1.5.0 in deployment | Yes — `infrastructure/controllers/pvc-plumber/deployment.yaml:38`, `HTTP_TIMEOUT=3s` set on line 53 |
| Kyverno legacy policy now Enforce | Yes — `validationFailureAction: Enforce` (line 18) plus rule-level `failureAction: Enforce` on rules 0 and 1 |
| Kyverno mutate gated on authoritative=restore | Yes — preconditions on lines 150-163 require all of `authoritative=true`, `decision=restore`, `exists=true` |
| `apiCall.default` for plumber failure | Yes — Rule 0 defaults `status: unavailable`, Rule 1 defaults to `decision: unknown, authoritative: false` |
| Kopia maintenance default safety | Yes — `kopia-maintenance-cronjob.yaml:145` is `kopia maintenance run` (no `--safety=none`), schedule moved to `37 3 * * *` |
| ServiceMonitor + alerts | Yes — `pvc-plumber-metrics` ServiceMonitor at line 95 of `custom-servicemonitors.yaml`, three alerts (`PVCPlumberDown`, `PVCPlumberUnknownDecisions`, `PVCPlumberBackupCheckErrors`) at `volsync-alerts.yaml:163-220` |
| New decision-flow doc | Yes — `docs/pvc-restore-decision-flow.md` |

**Verdict: implementation matches the docs.** No "I claimed it but didn't actually do it" gaps found.

## Issues Worth Fixing

### 1. Dead-code CEL policies (high signal, easy fix)

`infrastructure/controllers/kyverno/policies/volsync-pvc-validate.yaml` and `volsync-pvc-mutate.yaml` exist on disk but `infrastructure/controllers/kyverno/kustomization.yaml` only includes:

```
- policies/volsync-pvc-backup-restore.yaml
- policies/volsync-nfs-inject.yaml
- policies/volsync-orphan-cleanup.yaml
```

So the modern `policies.kyverno.io/v1` CEL `ValidatingPolicy`/`MutatingPolicy` files are **never deployed**. This was already flagged in the working notes but the hardening pass didn't resolve it.

Two reasonable choices:

- **(A) Delete them.** Legacy ClusterPolicy is now Enforce + tri-state and works. Don't carry uncalled YAML that will silently rot.
- **(B) Wire them in and retire the validate/mutate rules from the legacy ClusterPolicy.** This is the "migrate to CEL" path codex notes as the long-term direction. Test before flipping. Note that Kyverno's `http.Get()` library returns `null` on failure — the validate file at line 39 already handles the null case, but the mutate file doesn't have a defensive null check on `variables.backupCheck` (see `mutate.yaml:42-48`).

I'd do (A) tonight and revisit (B) only if/when you actually retire the legacy ClusterPolicy. Carrying both is the worst option.

### 2. `VolSyncRestoreTooLong` alert is probably dead

`monitoring/prometheus-stack/volsync-alerts.yaml:115-120`:

```promql
kube_persistentvolumeclaim_status_phase{phase="Pending"} == 1
and on (persistentvolumeclaim, namespace)
kube_persistentvolumeclaim_info{volumeattributesclass=~".*volsync.*"} == 1
```

`volumeattributesclass` is the VolumeAttributesClass field on a PVC (a different KEP). VolSync VolumePopulator-restored PVCs use `spec.dataSourceRef.kind=ReplicationDestination`; they don't set a VolumeAttributesClass. The filter almost certainly matches zero series in your cluster. Verify with:

```
promql: count by (volumeattributesclass) (kube_persistentvolumeclaim_info{namespace!=""})
```

Better predicate: identify pending restore PVCs by joining on a label that VolSync's mover adds, or by matching `kube_persistentvolumeclaim_info` rows whose name has a `ReplicationDestination` of the same name. kube-state-metrics doesn't expose `dataSourceRef` directly; the cleanest route is a recording rule fed by `kube_persistentvolumeclaim_labels` joined with your `app.kubernetes.io/managed-by: kyverno` label and PVC phase.

This is the single biggest "we think we have an alert, we don't" item in the doc.

### 3. Three pvc-plumber calls per PVC CREATE

`volsync-pvc-backup-restore.yaml` now performs:

- Rule 0 (`require-pvc-plumber-available`): `GET /readyz`
- Rule 1 (`require-authoritative-backup-decision`): `GET /exists/<ns>/<pvc>`
- Rule 2 (`add-datasource-if-backup-exists`): `GET /exists/<ns>/<pvc>` again

Kyverno doesn't share `context` between rules. With `HTTP_TIMEOUT=3s` on the plumber side and Kyverno's default webhook timeout (10s), this is fine in steady state. During a fresh cluster bring-up you can have 50+ PVCs being admitted in a tight window and pvc-plumber's cache will go cold (TTL=5m, no continuous re-warm). Three serial NFS-backed Kopia subprocess calls per PVC — at 1-2s per call with NFS — can push individual admissions past 10s and surface as `failed calling webhook`.

Mitigations, in order of effort:

- Move the `/readyz` check inside the validate rule that already calls `/exists`. `/exists` returning 503 already covers "plumber unavailable" because the apiCall default kicks in. Rule 0 is now redundant.
- Re-warm the pvc-plumber cache periodically (every 60-120s), not just at startup. Today a long DR pause silently expires every entry.
- Consider `failurePolicy: Fail` audit: confirm Kyverno is fail-closed on the webhook itself when plumber is *completely* unreachable. (It should be, given the apiCall.default; just confirm during the drill.)

### 4. Mutate rule has no apiCall.default

Rule 2's `backupCheck` apiCall (line 144-149) has no `default:` block. If pvc-plumber is unreachable, the apiCall fails and Kyverno aborts the rule with an error rather than evaluating preconditions. In practice Rule 1 has already denied the PVC, but defense-in-depth: copy the same default from Rule 1 here too.

### 5. Kopia maintenance ownership claim

The cronjob does `kopia maintenance set --owner=maintenance@cluster` on every run. Kopia validates `--owner` against the running client identity, so this is safe — but if a VolSync mover has ever claimed ownership (it shouldn't, but the synthetic identity wasn't always used), the maintenance job will fail with "maintenance must be run by designated user." Worth verifying once on the live repo:

```
kopia repository connect filesystem --path=/repository --override-username=maintenance --override-hostname=cluster
kopia maintenance info
```

The owner shown should be `maintenance@cluster`. If not, the cronjob's `kopia maintenance set --owner` will silently drift on every run trying to wrest ownership away.

### 6. PVC inventory: unlabeled Longhorn RWO state

Working notes correctly identified Longhorn PVCs missing labels:
- `searxng/redis-data`
- `frigate/mosquitto-storage-pvc`
- `project-zomboid/zomboid-server-files`
- `radar-ng/*` RWX
- Various Paperless, gitea-actions, etc.

The hardening plan's Phase 1 (audit-only `backup`/`backup-exempt` policy) is the right next concrete step and was deferred. Recommend: write the audit policy this week. It's cheap, no blast radius, and surfaces real gaps. Several of those PVCs (Mosquitto, Redis-as-cache) genuinely should be `backup-exempt: cache`; others (Zomboid server files, Paperless consume) probably *should* have a backup label and don't.

### 7. Backup schedule herd

The "stagger later" deferral is reasonable, but at 18 daily PVCs all firing at `0 2 * * *`, plus 7 hourly at `0 * * * *`, you're stacking up to 25 simultaneous Longhorn VolumeSnapshot + Kopia mover pod creations at 02:00 UTC. That's not catastrophic at homelab scale but it does mean:

- Longhorn snapshot controller queue spikes
- Kopia repository lock contention (multiple writers serialize on index updates)
- Mover pod scheduling can starve other workloads briefly

Quick win until the controller arrives: hash-stagger via the schedule expression in the Kyverno generate rule. CEL/JMESPath in Kyverno can do `hash_string` of `namespace+name`, mod 60. Rough sketch:

```
schedule: "{{ to_string(modulo(hash(concat([request.object.metadata.namespace, '/', request.object.metadata.name])), `60`)) }} 2 * * *"
```

Test in dry-run first; Kyverno's JMESPath has known quirks with `hash`.

### 8. Drills are missing — and they're the actual deliverable

Both the hardening plan (line 309: "Run destructive restore drills") and the PRD (test plan) acknowledge this is undone. **This is the gap that matters.** Until you've actually:

- Created a disposable PVC, deleted it, recreated it, and watched VolSync restore — end-to-end
- Killed pvc-plumber and watched Kyverno deny PVC creation
- Forced a Kopia error (chmod the NFS mount inside the pod, or break the password) and watched the deny path fire
- Watched a generate rule reconcile after the orphan-cleanup deleted a generated resource

…the design is theoretical. The architecture is right; the failure modes need behavioral confirmation. **Do this before any controller code.** Each drill takes ~30min and would catch alert misfires (#2), webhook timeout issues (#3), and ownership drift (#5).

## On the Controller PRD

Codex's PRD is a solid first sketch. The phasing (Observe → Reconcile → Shadow → Enforce → Cleanup) is the right shape. But:

- **Effort is underestimated.** A real Kubernetes admission webhook with cert lifecycle (cert-manager or self-signed rotator), leader election, finalizer/owner-ref discipline, status reconciliation across multiple owned objects, and CRD version-skew handling is multi-month solo work even for an experienced operator/Go dev. The PRD reads like 2-week scope; it isn't.
- **The CRDs are good but unprototyped.** `PVCProtectionClass`, `PVCBackupRepository`, and `PVCProtection` are reasonable, but worth running `kubebuilder init` and rendering them through `kustomize build` before committing to the names. Field names (`unknownPolicy`, `protectAfter`, `repositoryRef.name`) tend to feel different once you're writing reconcile logic against them.
- **The catalog manager design assumes Kopia's `snapshot list --all --json` is fast enough.** At 27GiB on NFS today this is probably true. At 270GiB it may not be. Worth measuring before building.
- **The "shadow mode" comparison story is hand-waved.** Concretely: the controller writes its decision to `PVCProtection.status`, Kyverno keeps doing the actual mutation, and you compare. But Kyverno doesn't expose its decision in a structured way; you'd need to either tail Kyverno admission logs and join, or have the controller observe the admitted PVC's resulting state. Not impossible, but more work than "controller observes only" implies.
- **Don't build the controller until you've drilled the bridge.** If the bridge survives 3-4 real DR drills cleanly, the bar to justify a CRD shifts. You may discover the bridge is good enough.

The PRD itself is worth keeping as the design vision. Don't start coding it this quarter.

## On Codex's Doc Quality

Honest praise: codex did a careful job. The verification trail in the working notes is unusually good — file paths with line numbers, source citations on external claims, explicit "what I checked" sections. The draft evaluation correctly identifies the missing primitive ("restore intent" vs backup mechanics). The conclusion that VolSync VolumePopulator + Kopia + a decision oracle is the right shape is correct.

Two stylistic notes:
- The PRD has a lot of "boxes and arrows" ASCII diagrams. They're fine but don't add much over a Mermaid flowchart. The new decision-flow doc you have is more useful.
- The hardening plan's "implementation update" section at the end is mixed in with "still required" — split these so future-you can tell what's done from what's not.

## Recommended Next-Morning Priorities

In order:

1. **Delete the unwired CEL policy files** (`volsync-pvc-validate.yaml`, `volsync-pvc-mutate.yaml`) or wire them in with a deliberate plan to retire the legacy mutate rule. Don't ship dead code.
2. **Fix or delete `VolSyncRestoreTooLong`.** Verify in your Prometheus that the current expr returns rows. If not, replace it.
3. **Run the four drills.** Disposable PVC restore, plumber-down, Kopia-error, orphan-cleanup. ~2 hours total. This is the actual confidence gain.
4. **Add the audit-only `backup`/`backup-exempt` Kyverno policy.** Surface the unlabeled Longhorn RWO PVCs.
5. **Verify Kopia maintenance owner** with one manual `kopia maintenance info` from inside a maintenance-job-shaped pod.
6. **Consolidate the three pvc-plumber HTTP calls into one.** Drop Rule 0; let `/exists` 503 handle plumber-down via the apiCall.default.
7. **Add a periodic cache re-warm** in pvc-plumber (60-120s). Pre-warm-only-at-startup is a real gap during long syncs.
8. **(Later)** Hash-stagger schedules. Useful before the inventory grows past ~50 backup-labeled PVCs.
9. **(Much later)** Start the controller PRD. Only after multiple successful drills.

## Bottom Line

The codex review was thorough, the implementation it shipped is real, and the direction is correct. The remaining risk is mostly behavioral (drills) and a few small misalignments (dead code, broken alert, redundant HTTP calls). Nothing here suggests the design is wrong. Sleep well.
