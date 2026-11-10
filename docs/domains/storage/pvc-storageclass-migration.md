# Move a PVC to another StorageClass

This runbook changes the StorageClass of one existing kopiur-backed PVC without losing
data, for example from `longhorn` to `longhorn-wired-ha`. It changes one PVC and its
`Restore`. It leaves everything else in the Application alone.

Kubernetes does not let you change `spec.storageClassName` on an existing PVC. The only
path is restore-before-bind, the same flow that the cluster uses for disaster recovery.
You take a backup, delete the PVC and its `Restore`, and let Argo CD recreate both. kopiur
then fills the volume on the target class from that backup before the PVC binds.

## Before you start

Check each item. Do not start the cutover until all are true.

- The target class creates volumes and places replicas as you expect. Prove it with a
  disposable PVC first (see [Prove the target class](#prove-the-target-class)).
- The PVC uses the `kopiur-backup` component. It has a `SnapshotPolicy`, a
  `SnapshotSchedule`, a `Restore`, and a `dataSourceRef` that points at the `Restore`.
- The last scheduled `Snapshot` is `Succeeded` and the Longhorn volume is `healthy`.
- The workload has a single writer that you can pause. A Postgres Deployment qualifies.
- A Git change that sets the target `storageClassName` on the PVC is merged. Until you
  recreate the PVC, Argo CD reports that the PVC fails to sync ("field is immutable").
  That is expected. Run the cutover right after the merge.

## Prove the target class

Create a throwaway PVC on the target class, write a file with a checksum, and list where
Longhorn put the replicas:

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

Expect each replica on a different node. Then delete one replica object.
Confirm that Longhorn rebuilds it and that the checksum still matches:

```sh
kubectl -n longhorn-system delete replicas.longhorn.io <one-replica-name>
kubectl -n longhorn-system get volumes.longhorn.io $PV -o jsonpath='{.status.robustness}'   # healthy again within ~1 min
kubectl -n sc-canary exec writer -- sh -c 'cd /data && sha256sum -c blob.sha'                 # blob: OK
kubectl delete ns sc-canary
```

## Cutover (worked example: `temporal/temporal-postgres-data`)

The commands use the Temporal Postgres volume as the example. `<ns>` is `temporal`,
`<pvc>` is `temporal-postgres-data`, and `<restore>` is `temporal-postgres-data-restore`.
Replace the names, the pod label and the `psql` user for another PVC.

1. Leave the reclaim policy of the old PV alone. Your fallback is the pinned cutover
   backup from step 3, not the old volume. Do not patch the old PV to `Retain`. With the
   class's `Delete` reclaim policy, Kubernetes and Longhorn remove the old volume as soon
   as the PVC is gone, so you clean up nothing by hand. The pinned backup holds the exact
   pre-cutover bytes outside the cluster.

2. Stop the writers without touching the pod. Apply a Cilium `ingressDeny` policy, then
   end the open database sessions. A plain Kubernetes NetworkPolicy with no ingress rules
   does **not** block traffic here, because the cluster's Cilium allow rules still admit
   it and clients reconnect within seconds. A Cilium deny rule overrides every allow rule.
   Each client that you disconnect tries to reconnect and meets the deny rule. Argo CD
   does not manage this policy, so Argo CD will not remove it for you.

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

   Expect a count of `0`. Run the count again ten seconds later and expect `0` again.
   The query leaves out the metrics sidecar's loopback session (`client_addr IS NULL`),
   and that session stays open. Temporal services log persistence errors while the
   policy blocks them. Those errors show that the block works.

3. Take the cutover backup. A hand-made `Snapshot` object reuses the `SnapshotPolicy`
   (hooks, identity, mover uid). `deletionPolicy: Retain` keeps the Kopia snapshot if
   someone later deletes the object. `pin: true` exempts it from retention.

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

   Expect `Succeeded <kopia-id>` within a few minutes. Write the id down.

4. Make Argo CD read the target class, then delete the `Restore`, the PVC and the pod.
   Argo CD can keep an old render for minutes after a merge. From that render it
   recreates the PVC on the **old** class. Hard-refresh the Application. Wait until the
   PVC shows `OutOfSync`, which means the desired state differs from the live PVC. Delete
   nothing before that. Delete the `Restore` first. A `Restore` chooses its backup once,
   when it is created, and never chooses again, so a leftover `Restore` fills the volume
   from an old backup. Delete the pod too, because PVC protection keeps the PVC while a
   pod uses it.

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

5. Check which backup the recreated `Restore` chose before you check the data.

   ```sh
   kubectl -n <ns> get restore <restore> -o jsonpath='{.status.resolved.pinnedAt} {.status.resolved.kopiaSnapshotID}{"\n"}'
   kubectl -n <ns> get pvc <pvc> -o jsonpath='{.status.phase} {.spec.storageClassName}{"\n"}'
   ```

   Expect the Kopia id from step 3 and a `pinnedAt` time later than that backup. Expect
   the PVC to go from `Pending` to `Bound` on the target class. A PVC that binds at once
   was not filled by kopiur. In that case, stop and inspect the `Restore` conditions.

6. Verify the volume and the database.

   ```sh
   NEW_PV=$(kubectl -n <ns> get pvc <pvc> -o jsonpath='{.spec.volumeName}')
   kubectl -n longhorn-system get replicas.longhorn.io -l longhornvolume=$NEW_PV -o custom-columns='NODE:.spec.nodeID,STATE:.status.currentState'
   kubectl -n <ns> logs deploy/temporal-postgres -c postgres | grep -E "redo done|ready to accept"
   kubectl -n <ns> exec deploy/temporal-postgres -c postgres -- psql -U temporal -d temporal -tc "SELECT pg_is_in_recovery();"
   ```

   Expect replicas on different nodes, the log lines `redo done` and then `ready to
   accept connections`, and the query result `f`.

7. Release the writers and check Temporal.

   ```sh
   kubectl -n <ns> delete ciliumnetworkpolicy cutover-quiesce
   kubectl -n <ns> exec deploy/temporal-admintools -- temporal operator cluster health   # SERVING
   kubectl -n <ns> exec deploy/temporal-admintools -- temporal schedule list --namespace default
   kubectl -n <ns> exec deploy/temporal-admintools -- tdbg dlq list                     # count unchanged
   ```

   After a restore, a schedule whose `NextRunTime` is in the past has lost its timer.
   Its scheduler workflow shows no pending timer and reacts only to signals. Pause and
   unpause the schedule to start the timer again. This does not change the schedule spec
   or the DLQ:

   ```sh
   kubectl -n <ns> exec deploy/temporal-admintools -- temporal schedule toggle --schedule-id <id> --namespace default --pause --reason "re-arm timer"
   kubectl -n <ns> exec deploy/temporal-admintools -- temporal schedule toggle --schedule-id <id> --namespace default --unpause --reason "re-arm timer"
   kubectl -n <ns> exec deploy/temporal-admintools -- temporal schedule describe --schedule-id <id> --namespace default -o json | jq '.info.futureActionTimes[0]'   # in the future
   ```

8. Confirm that the volume on the target class backs up. There is no old volume to remove, because step 4 deleted it.

   ```sh
   kubectl -n <ns> get snapshot --sort-by=.metadata.creationTimestamp | tail -2   # newest: Succeeded
   ```

## If a step fails, or to roll back

| Situation | What to do |
|---|---|
| The PVC stays `Pending` and the `Restore` shows `Stalled` | The Kopia repository is unreachable or the mover cannot read. Fix the cause, and kopiur retries. Nothing binds empty, because restore-before-bind keeps the PVC `Pending` on an error. |
| The `Restore` chose the wrong backup | Delete the `Restore` and the PVC again. The recreated `Restore` chooses the newest backup. |
| You want the old class back | Revert the Git change, then repeat step 4. The cutover backup restores onto the old class in the same way. |
| Nothing else works | The pinned cutover `Snapshot` holds the exact pre-cutover bytes. A fresh `Restore` and PVC fill from it on any class. |

## Related

- [Pick a StorageClass](storage-tiers.md) describes each class.
- [How kopiur backup and restore work](kopiur-backup-architecture.md) and
  [disaster recovery](../../disaster-recovery.md) explain restore-before-bind and how a
  `Restore` chooses its backup.
- The worked example manifests are `my-apps/development-infra/temporal/postgres/pvc.yaml`
  and `my-apps/development-infra/temporal/kopiur/temporal-postgres-data.yaml`.
