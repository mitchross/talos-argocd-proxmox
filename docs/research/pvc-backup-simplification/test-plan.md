# Test plan — full pvc-plumber decommission to author-spec + MAP

Status: PROPOSAL. These run against a live cluster (cannot execute from the
exploratory branch). **T7 is the new Phase-0 gate** (was T2). With the MAP
in place the populator's hard-unreachable behaviour matters less — the MAP
fail-closes the mover Job regardless.

Conventions: scratch namespace `vb-test` and throwaway PVCs only; never
test against real app data. RustFS endpoint = `192.168.10.133:30293` per
`infrastructure/controllers/pvc-plumber/deployment.yaml`.

---

## T1 — Per-PVC Kopia mover Secret schema (resolves R2)

Goal: confirm the chart's `volsync-<pvc>` Secret keys match what the
perfectra1n Kopia mover actually consumes.

```bash
kubectl get replicationsource -A -l volsync.backup/pvc | head
ns=<ns>; pvc=<pvc>
kubectl get externalsecret volsync-$pvc -n $ns -o yaml
kubectl get secret        volsync-$pvc -n $ns -o yaml -o jsonpath='{.data}' | jq 'keys'
kubectl get replicationsource ${pvc}-backup -n $ns -o yaml | yq '.spec.kopia'
```

PASS: chart `templates/externalsecret.yaml` rendered keys ⊇ live Secret
keys, and `spec.kopia.repository` references a Secret of that name/shape.
FAIL: adjust the template's `target.template.data` block; re-run.

## T2 — Populator behaviour on hard-unreachable backend (alignment check, not gate)

Goal: confirm whether the Kopia populator stays Pending (author's Restic
claim) or binds empty when the backend is unreachable. **Now informational**
— Option C MAP fail-closes the mover Job before this matters. Worth running
once to know the baseline.

```bash
kubectl create ns vb-test
# Render chart for a fake pvc 'gatetest' pointing at a BOGUS endpoint
#   s3.endpoint=10.255.255.1:1   (black-holed)
# Apply ONLY ES + RD + a PVC with dataSourceRef -> gatetest-dst
kubectl get pvc gatetest -n vb-test -w
kubectl describe pvc gatetest -n vb-test
kubectl get pods -n vb-test
```

Result documented either way; doesn't gate the migration.

## T3 — Per-app backup+restore round-trip (run for every migrated PVC)

```bash
# After chart-rendering app X (still pvc-plumber-free for X):
kubectl get replicationsource,replicationdestination,externalsecret -n <ns> \
  -l volsync.backup/pvc=<pvc>
# Force a backup (RS name = <pvc>, per chart vb.rsName)
kubectl patch replicationsource <pvc> -n <ns> --type merge \
  -p '{"spec":{"trigger":{"manual":"t3-'$(date +%s)'"}}}'
# Confirm snapshot lands in the SAME Kopia lineage (continuity proof —
# repo name volsync-<pvc> unchanged vs pvc-plumber era)
task volsync:snapshots PVC=<pvc> NS=<ns>
# Then: delete the PVC, let the populator restore, confirm app data intact.
```

PASS: snapshot appended to `volsync-<pvc>`; restore brings back real data;
app starts with history.

### T3-R5 — Burn sub-test (Phase 3 gate)

Specifically reproduce-or-refute the original SQLite-corruption-on-restore
burn that motivated pvc-plumber. Author reports "I use volsync to back up
SQLite and never ran into" the issue.

Run T3 against a previously-burned SQLite-bearing app (Karakeep, an *arr —
something you remember corrupting). Two outcomes:

- **PASS** (no corruption): the burn was Kyverno/timing-specific, not a
  VolSync-inherent issue. Strict tier migration safe to proceed.
- **FAIL** (reproduces): the migration model has a real failure mode we
  did not anticipate. STOP Phase 3 and triage — possibly an init-container
  ordering issue, or the populator restoring concurrently with app
  startup, or a checkpoint/WAL race. Re-evaluate.

## T4 — Is the Bound+2h guard still needed? (informs dropping it)

Goal: confirm the populator restores *before* the PVC binds, so the RS can
never capture a pre-restore empty volume (the hazard pvc-plumber's 2h timer
guarded).

```bash
# With a populated repo: create the PVC, race the RS manual trigger
# immediately. Inspect whether RS ever snapshots an empty FS.
```

PASS: PVC only binds after populator restore; earliest RS run sees populated
data → 2h guard unnecessary. FAIL: keep an equivalent guard (RS
`trigger.schedule` only, no immediate manual). Do not drop on assumption.

## T5 — Cleanup-label interaction (resolves R1)

Goal: confirm relabeling a PVC off `backup:` does NOT make pvc-plumber's
reconciler delete chart-rendered RS/RD/ES.

```bash
# In vb-test: apply chart for fake PVC WHILE pvc-plumber is running.
# Note chart RS name = <pvc>, RD name = <pvc>-dst — different from
# pvc-plumber's <pvc>-backup, so they coexist by name.
# Add then remove the `backup:` label on the source PVC; watch chart resources.
kubectl get rs,rd,externalsecret -n vb-test -l volsync.backup/pvc=<pvc> -w
```

PASS: chart resources survive relabel. FAIL: chart drops
`volsync.backup/pvc` label and uses its own owner label
(`app.kubernetes.io/managed-by=volsync-backup-chart`); re-test. Worst case:
scale pvc-plumber reconciler to 0 during cutover window.

## T6 — Schedule-spread parity (cosmetic, R3)

Render the chart for 20 representative ns/pvc pairs; confirm computed
minutes (adler32(ns/pvc) % 60) are well-distributed across 0–59. Exact
values differ from pvc-plumber's sha256 — only distribution matters.

## T7 — Cluster MAP fail-closed on unreachable backend (Phase-0 GATE)

Goal: prove the MAP injects the `wait-for-rustfs` init container into
mover Jobs and that the init container fails the Job when RustFS is
unreachable.

```bash
# Pre: talos-patch.yaml applied; MAP+Binding deployed.
kubectl api-resources | grep mutatingadmissionpolic            # must show v1beta1
kubectl get mutatingadmissionpolicy volsync-mover-backend-availability
kubectl get mutatingadmissionpolicybinding volsync-mover-backend-availability

# 1. Verify INJECTION when backend is up — trigger any backup, confirm pod
#    has both `jitter` and `wait-for-rustfs` initContainers and both succeed.
kubectl create ns vb-test
# (apply chart for a small test PVC, trigger backup via task volsync:backup)
kubectl get pods -n vb-test -l app.kubernetes.io/created-by=volsync \
  -o jsonpath='{.items[*].spec.initContainers[*].name}'        # expect: jitter wait-for-rustfs

# 2. Verify FAIL-CLOSED when backend is "down" — repoint MAP image command
#    temporarily to probe an unroutable host (e.g. 10.255.255.1:1) and trigger
#    a backup. Confirm Job goes into BackoffLimit failure.
#    (Then revert MAP back to 192.168.10.133:30293.)
```

PASS: both initContainers injected; (1) succeeds when RustFS reachable;
(2) fails Job with clear log line when unreachable; Job retries with
exponential backoff. FAIL: triage the MAP — CEL expression, JSONPatch
shape, feature-gate enablement.

---

## Execution order

**Phase 0 (cluster prep):** T7 (gate) → T1 → T5.
**Phase 1+ (per-app):** T3 for every migrated PVC; T3-R5 explicitly for
the first SQLite app in Phase 3.
**Anytime:** T2 (alignment check), T4 (drop-the-2h-guard decision), T6.
