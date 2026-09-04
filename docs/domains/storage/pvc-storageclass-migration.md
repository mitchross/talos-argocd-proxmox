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

1. **The fallback is the pinned cutover snapshot, not the old volume.** Do not
   patch the old PV to `Retain`. The class's `Delete` reclaim policy lets
   Kubernetes and Longhorn garbage-collect the old volume the moment the claim
   is gone, with nothing to clean up by hand. Step 3 pins the kopia snapshot
   that holds the exact pre-cutover bytes off-cluster.

2. **Stop writers without touching the pod.** Use a Cilium `ingressDeny`
   policy. A plain Kubernetes NetworkPolicy with no ingress rules does **not**
   block here: the cluster's existing Cilium allow rules still admit the
   traffic, and clients reconnect within seconds. Deny rules win over allows.
   Terminating open sessions forces every client to reconnect into the block.
   Argo CD does not manage this object, so it will not remove it for you.

   ```sh
   kubectl -n <ns> apply -f - <<'YAML'
   apiVersion: cilium.io/v2
   kind: CiliumNetworkPolicy
   metadata: { name: cutover-quiesce }
   spec:
     endpointSelector: { matchLabels: { app: temporal-postgres } }
     ingressDeny:
       - fromEntities: [all]
   YAML
   kubectl -n <ns> exec deploy/temporal-postgres -c postgres -- psql -U temporal -d temporal -c \
     "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE backend_type='client backend' AND pid<>pg_backend_pid() AND client_addr IS NOT NULL;"
   kubectl -n <ns> exec deploy/temporal-postgres -c postgres -- psql -U temporal -d temporal -c \
     "SELECT count(*) FROM pg_stat_activity WHERE backend_type='client backend' AND pid<>pg_backend_pid() AND client_addr IS NOT NULL;"
   ```

   Expected: the count is `0` and stays `0` on a second run ten seconds later.
   The metrics sidecar's loopback session is exempt (`client_addr IS NULL`) and
   is expected to remain. Temporal services log persistence errors while
   blocked; that is the point.

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

4. **Make Argo CD see the new class, then recreate the claim.** Argo CD can
   hold a stale render for minutes after a merge and will happily recreate the
   PVC on the **old** class from it. Hard-refresh and wait until the PVC shows
   `OutOfSync` (the desired state now differs from the live claim) before
   deleting anything. Delete the `Restore` first: it pins its snapshot at
   admission and never re-resolves, so a leftover `Restore` would hydrate an old
   snapshot. The pod must go too, or PVC protection keeps the claim alive.

   ```sh
   kubectl -n argocd annotate application <app> argocd.argoproj.io/refresh=hard --overwrite
   kubectl -n argocd get application <app> -o json | jq -r '.status.resources[] | select(.kind=="PersistentVolumeClaim") | "\(.name) \(.status)"'   # <pvc> OutOfSync
   OLD_PV=$(kubectl -n <ns> get pvc <pvc> -o jsonpath='{.spec.volumeName}')
   kubectl -n <ns> delete restore <restore>
   kubectl -n <ns> delete pvc <pvc> --wait=false
   kubectl -n <ns> delete pod -l app=temporal-postgres
   kubectl -n <ns> get pvc <pvc>          # NotFound within ~1 min
   kubectl get pv $OLD_PV                 # NotFound once the claim is gone (reclaim Delete)
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

   A schedule whose `NextRunTime` is in the past after a restore has lost its
   timer (the scheduler workflow shows no pending timer and only reacts to
   signals). Re-arm it without touching the spec or the DLQ:

   ```sh
   kubectl -n <ns> exec deploy/temporal-admintools -- temporal schedule toggle --schedule-id <id> --namespace default --pause --reason "re-arm timer"
   kubectl -n <ns> exec deploy/temporal-admintools -- temporal schedule toggle --schedule-id <id> --namespace default --unpause --reason "re-arm timer"
   kubectl -n <ns> exec deploy/temporal-admintools -- temporal schedule describe --schedule-id <id> --namespace default -o json | jq '.info.futureActionTimes[0]'   # in the future
   ```

8. **Confirm the new volume backs up.** Nothing to retire; the old volume was
   garbage-collected in step 4.

   ```sh
   kubectl -n <ns> get snapshot --sort-by=.metadata.creationTimestamp | tail -2   # newest hourly: Succeeded
   ```

## Failure path

- **PVC stuck `Pending`, `Restore` shows `Stalled`:** the repository is
  unreachable or the mover cannot read. Fix the cause; kopiur retries. Nothing
  binds empty (restore-before-bind fails closed).
- **Wrong snapshot pinned:** delete the `Restore` and the PVC again; the next
  admission pins the newest snapshot.
- **Roll back the class:** revert the Git change, then repeat step 4. The
  cutover snapshot restores equally well onto the old class.
- **Last resort:** the pinned cutover `Snapshot` holds the exact pre-cutover
  bytes; a fresh `Restore` + PVC hydrates from it on any class.

## Source of truth

- StorageClass contract: [storage-tiers.md](storage-tiers.md)
- Backup/restore mechanics and the `Restore` pin: [kopiur-backup-architecture.md](kopiur-backup-architecture.md), [../../disaster-recovery.md](../../disaster-recovery.md)
- Worked example manifests: `my-apps/development/temporal/postgres/pvc.yaml`, `my-apps/development/temporal/kopiur/temporal-postgres-data.yaml`
