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

## Task queues and Schedule seeding

Each role owns its own queue: `radar-ng-mrms`, `radar-ng-nowcast`,
`radar-ng-hrrr`, `radar-ng-aux`, and `radar-ng-alerts`. Open-Meteo activities
run on `radar-ng-open-meteo`. The single-process `radar-ng` queue is retired.

`USE_ISOLATED_TASK_QUEUES=1` in `radar-ng-temporal-config` makes seeding write
each Schedule to its own role queue. Exactly one pool seeds: `aux` carries
`SEED_SCHEDULES=1` and also runs the read-only stall observer. Every other pool
keeps `SKIP_SCHEDULE_SEED=1`. Two seeders race each other, so never set
`SEED_SCHEDULES` on a second pool.

Verify routing after any change to seeding or queue names:

```sh
kubectl -n temporal exec deploy/temporal-admintools -- \
  temporal schedule describe -s ingest-mrms-base -o json | jq '.schedule.action.startWorkflow.taskQueue.name'
for q in mrms nowcast hrrr aux alerts; do
  kubectl -n temporal exec deploy/temporal-admintools -- \
    temporal task-queue describe -t "radar-ng-$q" --task-queue-type workflow
done
```

Expected: each schedule names its role queue, and every role queue lists both
workflow and activity pollers. A queue with zero pollers silently drops work:
schedules fire, the workflow task is never picked up, and the execution times
out with no error anywhere except stale data.

Never point a Schedule at a queue before its poller exists. When adding a role,
deploy the pool first, confirm its pollers, then let `aux` reseed.

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
