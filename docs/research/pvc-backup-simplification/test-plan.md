# Test plan — declarative VolSync migration

Status: PROPOSAL. These run against a live cluster (cannot execute from the
exploratory branch). T2 is the **migration gate** — nothing strict-tier
moves until it passes.

Conventions: use a scratch namespace `vb-test` and a throwaway PVC; never
test against a real app's data PVC. All `kubectl` from a workstation with
cluster access.

---

## T1 — Secret/repo schema reconciliation (resolves R2)

Goal: confirm the chart's `volsync-<pvc>` secret keys match what the
perfectra1n Kopia mover actually consumes.

```bash
# Pick any currently backed-up PVC
kubectl get replicationsource -A -l volsync.backup/pvc
ns=<ns>; pvc=<pvc>
kubectl get externalsecret volsync-$pvc -n $ns -o yaml
kubectl get secret        volsync-$pvc -n $ns -o yaml -o jsonpath='{.data}' | jq 'keys'
kubectl get replicationsource ${pvc}-backup -n $ns -o yaml | yq '.spec.kopia'
```

PASS: chart `templates/externalsecret.yaml` rendered keys ⊇ the live secret
keys, and `spec.kopia.repository` references a secret of that name/shape.
FAIL action: adjust the template's `target.template.data` block; re-run.

## T2 — THE GATE: unreachable backend behaviour (resolves MUST-HAVE #2)

Goal: prove the Kopia RD/populator fails *closed* (PVC stays Pending) when
the S3 backend is unreachable — i.e. the author's Restic claim holds on this
fork.

```bash
kubectl create ns vb-test
# Render chart for a fake pvc 'gatetest' pointing at a BOGUS endpoint
#   s3.endpoint=10.255.255.1:1   (black-holed)
# Apply ONLY the RD + ES + a PVC with dataSourceRef -> gatetest-backup
kubectl get pvc gatetest -n vb-test -w        # observe
kubectl describe pvc gatetest -n vb-test
kubectl get pods -n vb-test                   # mover pod state
```

PASS: PVC stays `Pending` indefinitely; mover pod keeps erroring/retrying;
**it never binds empty**. Then point endpoint back at real RustFS with an
EMPTY repo path → confirm it *does* bind empty (genuine-fresh still works).
FAIL: PVC binds empty while backend unreachable → **author-spec is unsafe
for strict tier on this fork. STOP migration. Strict tier must use Path B
(residual webhook). Best-effort tier may still proceed (accepted risk).**

Record exact mover logs + timing in `dr-drill` notes.

## T3 — Per-app backup+restore round-trip (run for every migrated PVC)

```bash
# After chart-rendering app X (still pvc-plumber-free for X):
kubectl get replicationsource,replicationdestination,externalsecret -n <ns> \
  -l volsync.backup/pvc=<pvc>
# Force a backup
kubectl patch replicationsource <pvc>-backup -n <ns> --type merge \
  -p '{"spec":{"trigger":{"manual":"t3-'$(date +%s)'"}}}'
# Watch it complete, then verify the snapshot landed in the SAME lineage
#   (continuity proof — repo name unchanged vs pvc-plumber era)
# Then: delete the PVC, let the populator restore, confirm app data intact.
```

PASS: snapshot appended to `volsync-<pvc>` (not a new lineage); restore
brings back real data; app starts with history.

## T4 — Is the Bound+2h guard still needed? (informs dropping it)

Goal: confirm the populator restores *before* the PVC binds, so the RS can
never capture a pre-restore empty volume (the hazard pvc-plumber's 2h timer
guarded).

```bash
# With a populated repo: create the PVC, race the RS manual trigger
# immediately. Inspect whether RS ever snapshots an empty FS.
```

PASS: PVC only binds after populator restore; earliest RS run sees populated
data. → 2h guard is unnecessary, document its removal.
FAIL: there is a window where RS could capture empty → keep an equivalent
guard (e.g. RS `trigger.schedule` only, no immediate manual; or a startup
gate). Do NOT drop the guard on assumption.

## T5 — Cleanup-label interaction (resolves R1, blocker)

Goal: confirm relabeling a PVC off `backup:` does NOT make pvc-plumber's
reconciler delete the chart-rendered RS/RD/ES.

```bash
# In vb-test: chart-render a fake PVC WHILE pvc-plumber is running.
# Add then remove the `backup:` label; watch the chart's resources.
kubectl get rs,rd,externalsecret -n vb-test -l volsync.backup/pvc=<pvc> -w
```

PASS: chart resources survive relabel. FAIL: pick a mitigation from
migration-plan R1 (separate owner label / scale reconciler to 0 / decom
pvc-plumber first) and re-test.

## T6 — Schedule-spread parity (cosmetic, R3)

Render the chart for 20 representative ns/pvc pairs; confirm computed
minutes are well-distributed across 0–59 (no thundering herd). Exact values
differ from pvc-plumber — only distribution matters.

---

## Execution order

T1 → T2 (**gate**) → T5 → T4 → then per-app T3 through phasing → T6 anytime.
If T2 fails: best-effort tier may still migrate; strict tier requires Path B.
