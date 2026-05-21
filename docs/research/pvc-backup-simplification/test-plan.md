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

Split into two sub-tests because the backup-side and restore-side
matter for *different* reasons. **T7b is the single most important
verification in Phase 0** — it is the end-to-end proof of the
walkthrough claim "a PVC never silently binds empty over a real
backup." Every link in that chain (`dataSourceRef → populator →
volsync-dst- Job → MAP → wait-for-rustfs → mover → bind`) must hold;
T7b exercises all of them at once.

### T7 prerequisites (run once, before T7a/T7b)

```bash
kubectl api-resources | grep mutatingadmissionpolic            # must show v1beta1
kubectl get mutatingadmissionpolicy volsync-mover-backend-availability
kubectl get mutatingadmissionpolicybinding volsync-mover-backend-availability
kubectl create ns vb-test
```

Also capture VolSync mover Job's retry shape so you know the ceiling
the `wait-for-rustfs` 1h timeout fits inside (see cluster/README.md
"Bootstrap-chaos sizing notes"):

```bash
# After triggering ANY mover Job (T7a does this), capture:
kubectl get job <volsync-dst-or-src-name> -n vb-test \
  -o jsonpath='{"backoffLimit="}{.spec.backoffLimit}{"  activeDeadlineSeconds="}{.spec.activeDeadlineSeconds}{"\n"}'
```

Record those values in `dr-drill` notes. If `activeDeadlineSeconds` is
set and is less than 3600, the MAP's 1h init timeout is effectively
capped to it — tune accordingly.

### T7a — Backup-side: MAP injection sanity

Goal: confirm the MAP correctly matches backup mover Jobs and that
both init containers run.

```bash
# In vb-test: apply chart for a small test PVC, trigger immediate backup
task volsync:backup PVC=t7test NS=vb-test
# While the volsync-src-* pod is alive:
kubectl get pods -n vb-test -l app.kubernetes.io/created-by=volsync \
  -o jsonpath='{.items[*].spec.initContainers[*].name}'
# Expect: "jitter wait-for-rustfs"
# Both init containers should reach Completed; the mover container then runs.
```

PASS: both initContainers present and Completed; mover succeeds; snapshot
appears in the Kopia repo. FAIL: MAP not matching → check CEL match
conditions, label `app.kubernetes.io/created-by=volsync` on the Job.

### T7b — Restore-side: PVC stays Pending while backend unreachable (LOAD-BEARING)

Goal: prove the populator → RD Job → MAP chain holds end to end.
This is the data-safety claim the whole migration rests on.

**Black-hole mechanism: scoped CiliumNetworkPolicy, NOT MAP mutation.**
Editing the deployed MAP's probe target would gate every backup-labeled
PVC's mover cluster-wide during the test window (all 26 existing
pvc-plumber lineages would have their scheduled backups blocked). The
CNP approach black-holes RustFS *only* from pods inside the test
namespace, leaves the deployed MAP untouched, and tests the real
production probe target rather than a modified one.

```bash
# Pre: a Kopia repo lineage exists for test PVC 't7test' from T7a above.
kubectl create ns vb-test-restore

# Step 1: black-hole RustFS for volsync mover pods in vb-test-restore.
#         Cilium's egressDeny is the right primitive — standard K8s NP
#         can only allow-list, which would require enumerating every
#         other egress (DNS, cluster CIDR, ...) just to subtract one IP.
cat <<'EOF' | kubectl apply -f -
apiVersion: cilium.io/v2
kind: CiliumNetworkPolicy
metadata:
  name: blackhole-rustfs-for-t7b
  namespace: vb-test-restore
spec:
  endpointSelector:
    matchLabels:
      app.kubernetes.io/created-by: volsync
  egressDeny:
    - toCIDR:
        - 192.168.10.133/32
      toPorts:
        - ports:
            - port: "30293"
              protocol: TCP
EOF

# Step 2: chart-render the same PVC in vb-test-restore, with the same
#         dataSourceRef -> t7test-dst pointing at the same Kopia repo
#         from T7a. The populator triggers a restore Job.

# Step 3: observe — the deployed MAP injects wait-for-rustfs, the probe
#         fails (CNP blocks the TCP), init loops with logs every 30s.
kubectl get pvc t7test -n vb-test-restore -w                    # STATUS stays Pending
kubectl get pods -n vb-test-restore -l app.kubernetes.io/created-by=volsync
# Expect: volsync-dst-* pod stuck in Init.
kubectl logs -n vb-test-restore <pod> -c wait-for-rustfs
# Expect: 'waiting for rustfs s3 (192.168.10.133:30293) — Ns elapsed' every 30s.

# Step 4: remove the black-hole. The next probe iteration (≤5s later)
#         passes; init exits 0; mover restores from the Kopia repo;
#         PVC binds with real data.
kubectl delete ciliumnetworkpolicy blackhole-rustfs-for-t7b -n vb-test-restore
kubectl get pvc t7test -n vb-test-restore                       # STATUS = Bound
# Verify content actually came from Kopia (not an empty bind):
#   exec into a pod that mounts the PVC and check for known file/data
#   that was in t7test's snapshot from T7a.
```

PASS: PVC stays Pending throughout the CNP window; binds with real data
after CNP removed; **no empty bind happens at any point**. This is THE
proof that the operator-free design is safe.

FAIL modes (any of these means STOP and triage before Phase 1):
- PVC binds empty while CNP active → MAP isn't matching the
  `volsync-dst-` Job (check CEL `matchConditions`) OR the populator
  doesn't actually gate binding on Job completion (check VolSync version).
- Init container exits 1 before you delete the CNP → 1h timeout triggered;
  bump higher OR investigate. If your bootstrap-window estimate from the
  cluster/README.md sizing notes shows realistic cold-start <1h, the
  timeout is fine and a real CNP-active window of >1h is the realistic
  failure mode the timeout is designed to surface.
- volsync-dst-* Job hits `backoffLimit` and goes Failed before you can
  test the recovery path → restore would be permanently stuck on a real
  outage. Check Job spec (T7 prereqs above) and either lower init
  timeout to leave more retries, or patch the Job's backoffLimit via an
  additional MAP/admission rule.
- Cluster doesn't have Cilium (it does, but if you're testing in a
  scratch cluster) → use a host-level iptables block on the test node
  instead, or run the test from a node that doesn't route to RustFS.

---

## Execution order

**Phase 0 (cluster prep):** T7a (sanity) → **T7b (the proof)** → T1 → T5.
**Phase 1+ (per-app):** T3 for every migrated PVC; T3-R5 explicitly for
the first SQLite app in Phase 3.
**Anytime:** T2 (alignment check), T4 (drop-the-2h-guard decision), T6.

Phase 1 does not start without T7b passing. If T7b fails, the operator-
free design is unsafe on this cluster as configured and the migration
either pauses for triage or falls back to Path B (residual webhook).
