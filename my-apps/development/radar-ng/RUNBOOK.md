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
pool until the observe-only Schedule image is running on all six workers. Then:

1. Deploy the exact same image digest to legacy and the five role pools. Leave
   `SKIP_SCHEDULE_SEED=1` on every role pool.
2. Confirm all six target versions are current, the five role queues have both
   workflow and activity pollers, and the Open-Meteo queue has its activity
   poller. Check node memory headroom while both pool sets coexist.
3. Keep legacy as the sole seeder and Schedule observer. Do not transfer
   seeding to `aux` during this cutover.
4. Change only legacy's `USE_ISOLATED_TASK_QUEUES` from `0` to `1`. Its seeder
   updates the schedules after the destination pollers are ready.
5. Confirm every schedule's actual task queue, then observe one natural run per
   role. A manual trigger is not proof that the Schedule timer is healthy.
6. Leave legacy polling `radar-ng` until pinned and long-lived executions drain;
   never delete it merely because new schedule traffic moved.

Before workflow API routes are enabled, separately change tile-server's
`TEMPORAL_ALERTS_TASK_QUEUE` to `radar-ng-alerts` and roll it. Those routes are
disabled today, so keep that rollout out of the initial Schedule cutover.

This ordering prevents a schedule update from routing work to a queue with no
poller, keeps one declarative Schedule writer, and preserves replayability for
existing pinned workflows. Roll back by first proving the legacy pollers are
healthy, changing the legacy flag back to `0`, and letting the same seeder route
schedules back. Keep the role pools until their executions drain.

## Schedule stops firing (timer never fires)

Signature: `temporal schedule describe --schedule-id <id>` shows its next action
in the past, no running action, and no natural fire. A manual trigger can make
fresh application output while leaving the Schedule's durable timer stranded,
so it is mitigation, not repair.

The application observer deliberately does not trigger, update, delete,
recreate, terminate, or purge anything. Treat its critical overdue event as a
Temporal control-plane incident. Inventory the timer DLQ and affected workflow
histories using the [Temporal timer DLQ runbook](../temporal/README.md#timer-dlq-alert-runbook).
Coordinate every affected application owner before approving a DLQ prefix
merge; prefix semantics may include another application's messages.

Recovery is complete only after the DLQ job succeeds, the queue is inventoried
again, and affected schedules fire naturally for at least two cadences. Never
purge the DLQ or use a manual trigger as the acceptance test.
