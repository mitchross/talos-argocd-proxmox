# radar-ng operations

## Temporal controller ownership after a namespace rebuild

The Temporal Worker Controller identity ends with the UID of its Kubernetes
namespace. Recreating `temporal-worker-controller` intentionally changes that
identity, while Temporal retains the old `ManagerIdentity` on every Worker
Deployment. A healthy target pod then remains `Inactive` with
`PlanExecutionFailed`.

Verify before changing anything:

```sh
kubectl -n radar-ng get workerdeployment radar-ng-worker -o yaml
```

If the status error names an old controller identity and no controller with
that namespace UID exists, transfer ownership using that exact old identity:

```sh
kubectl -n temporal exec deploy/temporal-admintools -- \
  temporal worker deployment manager-identity unset \
  --deployment-name radar-ng/radar-ng-worker \
  --address temporal-frontend.temporal.svc.cluster.local:7233 \
  --namespace default \
  --identity '<old status.managerIdentity>' \
  --yes
```

The controller caches Temporal state. If the server now reports an empty
manager but the CR continues to show the old identity, delete only the current
leader pod so leader election rebuilds the client cache. Do not delete the
WorkerDeployment or its versioned Deployments.

### Orphaned pinned executions after promotion

`RolloutComplete=True` does not prove scheduled work can progress. Temporal
workflows use `PINNED` versioning, so a workflow started on a retired build can
remain `Running` with a scheduled activity and no compatible poller. Because
radar schedules use overlap policy `Skip`, one orphan blocks every later fire
and the new worker appears idle while the public manifest stays stale or empty.

Check all running executions and inspect their `BuildId`:

```sh
kubectl -n temporal exec deploy/temporal-admintools -- \
  temporal workflow list \
  --address temporal-frontend.temporal.svc.cluster.local:7233 \
  --namespace default \
  --query 'ExecutionStatus="Running"'

kubectl -n temporal exec deploy/temporal-admintools -- \
  temporal workflow describe \
  --address temporal-frontend.temporal.svc.cluster.local:7233 \
  --namespace default \
  --workflow-id '<workflow-id>'
```

If—and only if—the execution is pinned to a build with no surviving poller,
terminate that execution with an explicit reason. Do not bulk-terminate healthy
current-build work. The schedule will fire again; trigger observed MRMS once if
the tile volume is empty and freshness must be restored immediately:

```sh
kubectl -n temporal exec deploy/temporal-admintools -- \
  temporal workflow terminate \
  --address temporal-frontend.temporal.svc.cluster.local:7233 \
  --namespace default \
  --workflow-id '<orphaned-workflow-id>' \
  --reason 'retired pinned worker build'

kubectl -n temporal exec deploy/temporal-admintools -- \
  temporal schedule trigger \
  --address temporal-frontend.temporal.svc.cluster.local:7233 \
  --namespace default \
  --schedule-id ingest-mrms-base
```

Recovery is complete only after the replacement workflow shows the current
build, `/api/health` is `ok`, and `manifest.json` advertises a recent radar
frame with every configured palette.

## Isolated task-queue rollout

The application image contains role-aware queues for `mrms`, `nowcast`,
`hrrr`, `aux`, and `alerts`. Keep `USE_ISOLATED_TASK_QUEUES=0` on the legacy
pool until an image containing those roles is running. Then:

1. Seed the `radar-ng` Temporal namespace and deploy one WorkerDeployment per
   role with `SKIP_SCHEDULE_SEED=1` except `aux`.
2. Confirm each target version is current and polling its role queue.
3. Set `USE_ISOLATED_TASK_QUEUES=1` and `SEED_SCHEDULES=1` only on `aux`.
4. Confirm all schedules point to their role queues before scaling legacy.
5. Leave legacy polling `radar-ng` until pinned executions drain; never delete
   it merely because new schedule traffic moved.

This ordering prevents a schedule update from routing work to a queue with no
poller and keeps existing pinned workflows replayable.
