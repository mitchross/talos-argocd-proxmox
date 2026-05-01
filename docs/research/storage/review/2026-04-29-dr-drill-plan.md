---
title: PVC backup/restore DR drill plan
status: DRAFT — awaiting approval before execution
date: 2026-04-29
relates_to:
  - docs/research/storage/review/2026-04-28-claude-opus-review.md
  - docs/research/storage/review/2026-04-28-current-flow-hardening-plan.md
  - docs/pvc-plumber-full-flow.md
---

# PVC backup/restore DR drill plan

Four drills to validate the FAIL-CLOSED PVC bridge **before** we declare the
hardening pass production-trusted. Each drill is scoped to a *disposable*
namespace + PVC pair so no production data is at risk; each drill names its
own reset/cleanup commands.

> **Stop before executing.** This document is the plan. Do not run it without
> explicit go-ahead from the operator on shift.

---

## Pre-flight

Run once before any drill. Verifies the cluster is in a known-good state.

```bash
# 1. All ReplicationSources successfully ran their last manual or scheduled sync.
kubectl get replicationsource -A -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name,RESULT:.status.latestMoverStatus.result

# 2. pvc-plumber is up and ready.
kubectl get pods -n volsync-system -l app.kubernetes.io/name=pvc-plumber
kubectl exec -n volsync-system deploy/pvc-plumber -- wget -qO- http://localhost:8080/readyz

# 3. Kyverno admission controller is up and the policy is Ready.
kubectl get clusterpolicy volsync-pvc-backup-restore
kubectl get pods -n kyverno -l app.kubernetes.io/component=admission-controller

# 4. Kopia maintenance owner is correct.
kubectl logs -n volsync-system $(kubectl get pod -n volsync-system -l app.kubernetes.io/name=kopia-maintenance -o name | head -1) | grep -E "Owner:|Recent Maintenance Runs:" | head -2

# 5. Snapshot a backup of the alerts in case a drill misfires.
kubectl get prometheusrule -n prometheus-stack volsync-alerts -o yaml > /tmp/volsync-alerts-pre-drill.yaml
```

If any of the above is not green: STOP, fix, restart pre-flight.

---

## Drill #1 — Disposable PVC restore (golden path)

**What we prove**: a brand-new backup-labeled PVC pulls last snapshot and
materializes its data, end-to-end through Kyverno → pvc-plumber → VolSync.

**Setup namespace**: `dr-drill` (disposable; created by drill, deleted at end).
Storage footprint: 1 Gi PVC, will be restored from a fresh ad-hoc backup.

```bash
# 1. Create the namespace and a disposable backup-labeled PVC.
kubectl create namespace dr-drill

cat <<'EOF' | kubectl apply -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: dr-drill-data
  namespace: dr-drill
  labels:
    backup: daily
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 1Gi
  storageClassName: longhorn
EOF

# 2. Wait for PVC to bind, then write a known marker into it.
kubectl wait --for=jsonpath='{.status.phase}=Bound' pvc/dr-drill-data -n dr-drill --timeout=120s

cat <<'EOF' | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: writer
  namespace: dr-drill
spec:
  restartPolicy: Never
  containers:
  - name: writer
    image: busybox:1.36
    command: ["sh","-c","echo dr-drill-marker-$(date -u +%s) > /data/marker.txt && cat /data/marker.txt"]
    volumeMounts: [{name: data, mountPath: /data}]
  volumes:
  - name: data
    persistentVolumeClaim: {claimName: dr-drill-data}
EOF
kubectl wait --for=condition=ContainersReady=false pod/writer -n dr-drill --timeout=60s
MARKER=$(kubectl logs -n dr-drill writer | tail -1)
echo "Wrote marker: $MARKER"

# 3. Trigger a manual backup and wait for it to land.
TRIGGER="dr-drill-$(date +%s)"
kubectl patch replicationsource -n dr-drill dr-drill-data-backup --type=merge \
  -p "{\"spec\":{\"trigger\":{\"manual\":\"$TRIGGER\"}}}"

# Poll until lastManualSync reflects $TRIGGER and result=Successful.
until [ "$(kubectl get replicationsource -n dr-drill dr-drill-data-backup -o jsonpath='{.status.lastManualSync}')" = "$TRIGGER" ]; do sleep 10; done
kubectl get replicationsource -n dr-drill dr-drill-data-backup -o jsonpath='{.status.latestMoverStatus.result}'; echo

# 4. Verify pvc-plumber sees the snapshot.
kubectl exec -n volsync-system deploy/pvc-plumber -- \
  wget -qO- http://localhost:8080/exists/dr-drill/dr-drill-data | jq

# 5. Tear down PVC + writer pod, leave the snapshot on NFS.
kubectl delete pod writer -n dr-drill --wait=false
kubectl delete pvc dr-drill-data -n dr-drill

# 6. Recreate the SAME PVC. Kyverno should add dataSourceRef; VolSync
#    should restore the marker.
cat <<'EOF' | kubectl apply -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: dr-drill-data
  namespace: dr-drill
  labels:
    backup: daily
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 1Gi
  storageClassName: longhorn
EOF

kubectl wait --for=jsonpath='{.status.phase}=Bound' pvc/dr-drill-data -n dr-drill --timeout=300s
kubectl get pvc dr-drill-data -n dr-drill -o jsonpath='{.spec.dataSourceRef}'; echo

# 7. Mount and verify the marker survived.
cat <<'EOF' | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: reader
  namespace: dr-drill
spec:
  restartPolicy: Never
  containers:
  - name: reader
    image: busybox:1.36
    command: ["sh","-c","cat /data/marker.txt"]
    volumeMounts: [{name: data, mountPath: /data}]
  volumes:
  - name: data
    persistentVolumeClaim: {claimName: dr-drill-data}
EOF
kubectl wait --for=condition=ContainersReady=false pod/reader -n dr-drill --timeout=60s
RESTORED=$(kubectl logs -n dr-drill reader | tail -1)
echo "Restored marker: $RESTORED"
[ "$MARKER" = "$RESTORED" ] && echo "PASS" || echo "FAIL"
```

**Cleanup** (always run, even on failure):

```bash
kubectl delete namespace dr-drill --wait=false
```

**Pass criterion**: `MARKER` and `RESTORED` are byte-identical.

---

## Drill #2 — Plumber-down (fail-closed admission)

**What we prove**: when pvc-plumber is unreachable, new backup-labeled PVCs
in app namespaces are **denied** at admission instead of silently bypassing
the restore-existence check.

> **RISK**: this scales pvc-plumber to zero. ANY backup-labeled PVC creation
> cluster-wide is denied while the deployment is down. Do not run this drill
> while ArgoCD is in the middle of bootstrapping or while another operator
> is deploying a new app. Coordinate first.

```bash
# 1. Snapshot current state.
kubectl get deploy pvc-plumber -n volsync-system -o jsonpath='{.spec.replicas}' > /tmp/pvc-plumber-replicas

# 2. Scale pvc-plumber to zero.
kubectl scale deploy pvc-plumber -n volsync-system --replicas=0
kubectl wait --for=delete pod -l app.kubernetes.io/name=pvc-plumber -n volsync-system --timeout=60s

# 3. Try to create a backup-labeled PVC in the disposable namespace.
kubectl create namespace dr-drill-2 || true
cat <<'EOF' | kubectl apply -f - 2>&1 | tee /tmp/dr-drill-2-output.txt
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: should-be-denied
  namespace: dr-drill-2
  labels:
    backup: daily
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 1Gi
  storageClassName: longhorn
EOF
# EXPECT: error containing "PVC Plumber could not make an authoritative ..."
grep -E "authoritative|denied|policy|admission" /tmp/dr-drill-2-output.txt && echo "PASS" || echo "FAIL"

# 4. Confirm the PVC was NOT created.
kubectl get pvc -n dr-drill-2 should-be-denied 2>&1 | grep -q "NotFound" && echo "PASS (not created)" || echo "FAIL (PVC exists)"
```

**Recovery** (run as soon as the assertion is captured):

```bash
PREV=$(cat /tmp/pvc-plumber-replicas)
kubectl scale deploy pvc-plumber -n volsync-system --replicas=${PREV:-1}
kubectl wait --for=condition=Available deploy/pvc-plumber -n volsync-system --timeout=120s
kubectl delete namespace dr-drill-2 --wait=false
```

**Pass criterion**: PVC creation rejected; `kubectl get pvc` shows NotFound.

---

## Drill #3 — Kopia-error (backend returns unknown)

**What we prove**: when pvc-plumber is reachable but its backend lookup
fails (e.g. Kopia binary errors, repository unmounted), Kyverno still
denies admission rather than treating "unknown" as "fresh".

> **RISK**: this temporarily breaks pvc-plumber's view of the repository
> by patching its env to point at a bogus path. Same blast radius as Drill
> #2 — every backup-labeled PVC creation is denied while broken. Recover
> immediately after capturing the assertion.

```bash
# 1. Capture current env so we can restore it.
kubectl get deploy pvc-plumber -n volsync-system -o yaml > /tmp/pvc-plumber-deploy.yaml

# 2. Point pvc-plumber at a non-existent repository path.
kubectl set env deploy/pvc-plumber -n volsync-system KOPIA_REPOSITORY_PATH=/nonexistent
kubectl rollout restart deploy/pvc-plumber -n volsync-system

# 3. Wait — but Connect() should fail; pod will CrashLoopBackOff. That's fine,
#    it means /readyz is false. Verify pvc-plumber is NOT Ready.
sleep 30
kubectl get pods -n volsync-system -l app.kubernetes.io/name=pvc-plumber

# 4. Try to create a backup-labeled PVC.
kubectl create namespace dr-drill-3 || true
cat <<'EOF' | kubectl apply -f - 2>&1 | tee /tmp/dr-drill-3-output.txt
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: should-be-denied
  namespace: dr-drill-3
  labels:
    backup: daily
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 1Gi
  storageClassName: longhorn
EOF
grep -E "authoritative|unknown|denied" /tmp/dr-drill-3-output.txt && echo "PASS" || echo "FAIL"
kubectl get pvc -n dr-drill-3 should-be-denied 2>&1 | grep -q "NotFound" && echo "PASS (not created)" || echo "FAIL"
```

**Recovery** (run immediately):

```bash
kubectl apply -f /tmp/pvc-plumber-deploy.yaml
kubectl rollout status deploy/pvc-plumber -n volsync-system --timeout=120s
kubectl exec -n volsync-system deploy/pvc-plumber -- wget -qO- http://localhost:8080/readyz
kubectl delete namespace dr-drill-3 --wait=false
```

**Pass criterion**: PVC creation rejected; deny message references unknown
or non-authoritative decision.

---

## Drill #4 — Orphan cleanup

**What we prove**: when a backup label is removed (or a PVC is deleted),
the `volsync-orphan-cleanup` ClusterCleanupPolicy reaps the generated
ReplicationSource, ReplicationDestination, and ExternalSecret within
the 15-minute cleanup window.

```bash
# 1. Use the same disposable namespace as Drill #1 (or create a fresh one).
kubectl create namespace dr-drill-4 || true

# 2. Create a backup-labeled PVC and confirm Kyverno generated all 3 children.
cat <<'EOF' | kubectl apply -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: dr-drill-4-data
  namespace: dr-drill-4
  labels:
    backup: daily
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 1Gi
  storageClassName: longhorn
EOF
kubectl wait --for=jsonpath='{.status.phase}=Bound' pvc/dr-drill-4-data -n dr-drill-4 --timeout=120s

# 3. Wait the 2h "young PVC" gate by skipping it: ReplicationSource won't
#    appear until the PVC has aged 2h per the generate rule. We test orphan
#    cleanup of the ExternalSecret + ReplicationDestination instead, which
#    are unconditional.
kubectl get externalsecret,replicationdestination -n dr-drill-4

# 4. Remove the backup label.
kubectl label pvc dr-drill-4-data -n dr-drill-4 backup-

# 5. Wait up to 16 minutes for the orphan cleanup policy (runs every 15min).
echo "Waiting for orphan cleanup… check back in ~16 minutes."
# NOTE: kyverno cleanup policies don't expose a manual trigger. The cycle
# is fixed at 15m. Use this gap to grab a coffee.

# 6. After 16+ minutes, confirm the children are gone.
kubectl get externalsecret -n dr-drill-4 volsync-dr-drill-4-data 2>&1 | grep -q NotFound && echo "PASS (ES gone)" || echo "FAIL (ES still present)"
kubectl get replicationdestination -n dr-drill-4 dr-drill-4-data-backup 2>&1 | grep -q NotFound && echo "PASS (RD gone)" || echo "FAIL (RD still present)"
```

**Cleanup**:

```bash
kubectl delete namespace dr-drill-4 --wait=false
```

**Pass criterion**: all three generated resources (ES, RS if it existed, RD)
are gone within ~16 minutes of the label removal.

---

## Reporting

After each drill, capture into `docs/research/storage/review/2026-04-29-dr-drill-results.md`:

- Drill name + timestamp
- PASS / FAIL
- Recovery commands run
- Any unexpected events from the cluster (Kyverno restarts, alerts fired)
- Snapshots of relevant logs

---

## What this plan does NOT cover (deferred)

- **Multi-PVC concurrent restore storm** (10+ backup-labeled PVCs created at
  once). The current admission path goes through a serial `apiCall` per PVC;
  worth measuring webhook latency under fan-out, but not part of the
  baseline confidence gate.
- **Kopia repository corruption recovery.** Out of scope for this round; we
  trust the maintenance cronjob + per-snapshot deduplication. Schedule a
  separate drill once the protected-pvc-controller is in shadow mode.
- **Long-running mover under load.** Validated incidentally by the every-N-hour
  scheduled backups; a dedicated soak test would be useful but is not on
  this plan.
