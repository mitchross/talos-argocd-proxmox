# Move a kopiur-backed PVC to another StorageClass

**Purpose:** change the StorageClass of an existing PVC (for example `longhorn` →
`longhorn-wired-ha`) without losing data.
**Status:** runbook, current truth.
**Scope:** one PVC and its `Restore` CR. Nothing else in the Application changes.
Kubernetes treats `spec.storageClassName` as immutable, so the only path is the
same restore-before-bind flow the cluster already uses for disaster recovery:
snapshot → delete PVC + `Restore` → let Argo CD recreate both → kopiur hydrates
the new volume from the snapshot.

## Prerequisites

- The target class provisions and places replicas the way you expect. Prove it
  with a disposable PVC first (see "Canary" below).
- The PVC is on the `kopiur-backup` component: `SnapshotPolicy`, `SnapshotSchedule`,
  `Restore`, and a `dataSourceRef` pointing at the `Restore`.
- The last scheduled `Snapshot` is `Succeeded` and the Longhorn volume is `healthy`.
- The workload is a single writer you can pause (a Postgres Deployment qualifies).
- A merged Git change that sets the new `storageClassName` on the PVC. Until the
  PVC is recreated, Argo CD reports that resource as failing to sync
  ("field is immutable"). That is expected; run the cutover right after merge.

## Canary

```sh
kubectl create ns sc-canary
kubectl -n sc-canary apply -f - <<'YAML'
apiVersion: v1
kind: PersistentVolumeClaim
metadata: { name: canary }
spec: { accessModes: [ReadWriteOnce], storageClassName: <new-class>, resources: { requests: { storage: 2Gi } } }
YAML
kubectl -n sc-canary run writer --image=busybox:1.37 --restart=Never --overrides='{"spec":{"containers":[{"name":"w","image":"busybox:1.37","command":["sh","-c","head -c 64M /dev/urandom >/data/blob; sha256sum /data/blob >/data/blob.sha; sync; sleep 3600"],"volumeMounts":[{"name":"d","mountPath":"/data"}]}],"volumes":[{"name":"d","persistentVolumeClaim":{"claimName":"canary"}}]}}'
PV=$(kubectl -n sc-canary get pvc canary -o jsonpath='{.spec.volumeName}')
kubectl -n longhorn-system get replicas.longhorn.io -l longhornvolume=$PV -o custom-columns='NAME:.metadata.name,NODE:.spec.nodeID,STATE:.status.currentState'
```

Expected: one replica per distinct node. Then delete one replica CR and confirm
Longhorn rebuilds it and the data still verifies:

```sh
kubectl -n longhorn-system delete replicas.longhorn.io <one-replica-name>
kubectl -n longhorn-system get volumes.longhorn.io $PV -o jsonpath='{.status.robustness}'   # healthy again within ~1 min
kubectl -n sc-canary exec writer -- sh -c 'cd /data && sha256sum -c blob.sha'                 # blob: OK
kubectl delete ns sc-canary
```

## Cutover (worked example: `temporal/temporal-postgres-data`)

Replace names for another PVC. `<ns>` is `temporal`, `<pvc>` is
`temporal-postgres-data`, `<restore>` is `temporal-postgres-data-restore`.

1. **Keep the old volume as a fallback.** Nothing is deleted until step 8.

   ```sh
   OLD_PV=$(kubectl -n <ns> get pvc <pvc> -o jsonpath='{.spec.volumeName}')
   kubectl patch pv $OLD_PV -p '{"spec":{"persistentVolumeReclaimPolicy":"Retain"}}'
   ```

2. **Stop writers without touching the pod.** A temporary NetworkPolicy blocks
   every client; terminating open sessions forces reconnects into the block.
   Argo CD does not manage this object, so it will not remove it for you.

   ```sh
   kubectl -n <ns> apply -f - <<'YAML'
   apiVersion: networking.k8s.io/v1
   kind: NetworkPolicy
   metadata: { name: cutover-quiesce }
   spec:
     podSelector: { matchLabels: { app: temporal-postgres } }
     policyTypes: [Ingress]
   YAML
   kubectl -n <ns> exec deploy/temporal-postgres -c postgres -- psql -U temporal -d temporal -c \
     "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE backend_type='client backend' AND pid<>pg_backend_pid();"
   kubectl -n <ns> exec deploy/temporal-postgres -c postgres -- psql -U temporal -d temporal -c \
     "SELECT count(*) FROM pg_stat_activity WHERE backend_type='client backend' AND pid<>pg_backend_pid();"
   ```

   Expected: the count is `0` and stays `0` on a second run. Temporal services
   log persistence errors while blocked; that is the point.

3. **Take the cutover snapshot.** Manual `Snapshot` CRs reuse the policy (hooks,
   identity, mover uid). `Retain` keeps the kopia snapshot if the CR is later
   deleted; `pin` exempts it from retention.

   ```sh
   kubectl -n <ns> apply -f - <<'YAML'
   apiVersion: kopiur.home-operations.com/v1alpha1
   kind: Snapshot
   metadata: { name: <pvc>-cutover }
   spec:
     policyRef: { name: <pvc> }
     deletionPolicy: Retain
     pin: true
   YAML
   kubectl -n <ns> get snapshot <pvc>-cutover -o jsonpath='{.status.phase} {.status.snapshot.kopiaSnapshotID}{"\n"}'
   ```

   Expected: `Succeeded <kopia-id>` within a few minutes. Write the id down.

4. **Recreate the claim.** Delete the `Restore` first: it pins its snapshot at
   admission and never re-resolves, so a leftover `Restore` would hydrate an old
   snapshot. The pod must go too, or PVC protection keeps the claim alive.

   ```sh
   kubectl -n <ns> delete restore <restore>
   kubectl -n <ns> delete pvc <pvc> --wait=false
   kubectl -n <ns> delete pod -l app=temporal-postgres
   kubectl -n <ns> get pvc <pvc>          # NotFound within ~1 min
   kubectl get pv $OLD_PV                 # Released
   kubectl -n argocd annotate application <app> argocd.argoproj.io/refresh=normal --overwrite
   ```

5. **Check the pin before the bytes.**

   ```sh
   kubectl -n <ns> get restore <restore> -o jsonpath='{.status.resolved.pinnedAt} {.status.resolved.kopiaSnapshotID}{"\n"}'
   kubectl -n <ns> get pvc <pvc> -o jsonpath='{.status.phase} {.spec.storageClassName}{"\n"}'
   ```

   Expected: the kopia id from step 3, a `pinnedAt` newer than it, and the PVC
   moving `Pending → Bound` on the new class. A PVC that binds instantly never
   ran the populator; stop and inspect the `Restore` conditions.

6. **Verify the volume and the database.**

   ```sh
   NEW_PV=$(kubectl -n <ns> get pvc <pvc> -o jsonpath='{.spec.volumeName}')
   kubectl -n longhorn-system get replicas.longhorn.io -l longhornvolume=$NEW_PV -o custom-columns='NODE:.spec.nodeID,STATE:.status.currentState'
   kubectl -n <ns> logs deploy/temporal-postgres -c postgres | grep -E "redo done|ready to accept"
   kubectl -n <ns> exec deploy/temporal-postgres -c postgres -- psql -U temporal -d temporal -tc "SELECT pg_is_in_recovery();"
   ```

   Expected: replicas on distinct nodes, `redo done` then `ready to accept
   connections`, and `f`.

7. **Release the writers.**

   ```sh
   kubectl -n <ns> delete networkpolicy cutover-quiesce
   kubectl -n <ns> exec deploy/temporal-admintools -- temporal operator cluster health   # SERVING
   kubectl -n <ns> exec deploy/temporal-admintools -- temporal schedule list --namespace default
   kubectl -n <ns> exec deploy/temporal-admintools -- tdbg dlq list                     # count unchanged
   ```

8. **Retire the old volume** only after the next scheduled `Snapshot` on the new
   volume is `Succeeded`.

   ```sh
   kubectl -n <ns> get snapshot --sort-by=.metadata.creationTimestamp | tail -2
   kubectl delete pv $OLD_PV
   ```

## Failure path

- **PVC stuck `Pending`, `Restore` shows `Stalled`:** the repository is
  unreachable or the mover cannot read. Fix the cause; kopiur retries. Nothing
  binds empty (restore-before-bind fails closed).
- **Wrong snapshot pinned:** delete the `Restore` and the PVC again; the next
  admission pins the newest snapshot.
- **Roll back the class:** revert the Git change, then repeat step 4. The
  cutover snapshot restores equally well onto the old class.
- **Last resort:** the Retained old PV still holds the pre-cutover bytes until
  step 8. Bind it with a PVC that sets `volumeName` and no `dataSourceRef`.

## Source of truth

- StorageClass contract: [storage-tiers.md](storage-tiers.md)
- Backup/restore mechanics and the `Restore` pin: [kopiur-backup-architecture.md](kopiur-backup-architecture.md), [../../disaster-recovery.md](../../disaster-recovery.md)
- Worked example manifests: `my-apps/development/temporal/postgres/pvc.yaml`, `my-apps/development/temporal/kopiur/temporal-postgres-data.yaml`
