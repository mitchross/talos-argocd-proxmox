# Temporal safe worker deployments

**Ship a new worker by changing its image in Git. Never edit a running worker.**
The controller starts the new version next to the old one, runs a smoke
workflow, ramps new work over, and retires the old version once its workflows
finish. Nothing in flight is touched.

**Status:** runbook for the live cluster. **Scope:** application workers
(News Reader, Deal Scout, Radar). The Temporal server itself is covered by the
[server README](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/development/temporal/README.md).

This page follows Michael Jones's
[Temporal Safe Deploys lab](https://syntaxsugar.io/lab/temporal-safe-deploys/)
and applies it to this repository's manifests. Read the lab once if the words
*Build ID*, *pinned* or *drained* are new to you. It takes about an hour.

## The idea in five lines

1. A workflow that started on version A must finish on version A. Replaying
   its history against different code fails with a non-determinism error.
2. So every worker image gets a **Build ID**. Workflows are **pinned** to the
   Build ID they started on.
3. The **Temporal Worker Controller** runs one Kubernetes Deployment per
   Build ID, all on the same task queue. Temporal routes each task to the
   right one.
4. New work goes to the newest version only after its **gate** workflow
   passes and its **ramp** finishes.
5. An old version is **drained** when nothing is pinned to it any more. The
   controller then scales it down and deletes it on a timer.

## What runs here

Every app has one `Connection` named `cluster-temporal` that points at
`temporal-frontend.temporal.svc.cluster.local:7233`, and one or more
`WorkerDeployment` resources. The `kind` names matter: the controller ignores
the deprecated `Temporal*` kinds, so an image bump on those never rolls.

| App | WorkerDeployment | Rollout | Gate workflow | Sunset |
|---|---|---|---|---|
| News Reader | `news-digest` | Progressive: 10% for 2 min, then 50% for 5 min | `NewsDeploymentSmokeWorkflow` | scale down 10 min, delete 1 h |
| Deal Scout | `deal-scout` | Progressive: 50% for 2 min | `DealScoutDeploymentSmokeWorkflow` | scale down 10 min, delete 1 h |
| Radar | five `radar-ng-worker-*` pools | All at once | `RadarDeploymentSmokeWorkflow` | scale down 10 min, delete 1 h |

Radar uses all-at-once because its five pools share volumes and must move
together. It still keeps the old version alive until every pinned run drains.

The sunset timers count from the moment a version becomes **Drained**, not
from promotion. Deletion waits `scaledownDelay + deleteDelay` after Drained,
so an old version lives at least 70 minutes past its last pinned workflow.

## Release a worker

About 15 minutes of your attention. The controller does the waiting.

1. Publish the new worker image. Radar and Deal Scout pin by digest; News
   Reader uses a plain `vMAJOR.MINOR.PATCH` tag that is never overwritten.
2. Open a PR that changes only the image line in the app's `WorkerDeployment`.
   Any change to the pod template, image or environment is a new Build ID.
3. Before merging, render and test from the repository root:

   ```bash
   kustomize build my-apps/development/news-reader > /dev/null
   kustomize build my-apps/development/radar-ng > /dev/null
   kustomize build my-apps/utility/deal-scout > /dev/null
   python -m unittest discover -s scripts/tests -p test_temporal_deployments.py -v
   ```

   Expected: every build renders and every test passes.
4. Merge. Argo CD syncs the `WorkerDeployment`. The controller creates the new
   Deployment, waits for it to poll, runs the gate workflow, then ramps.
5. Watch it land (next section). You are done when the resource is `Ready`
   and the old version shows `Drained`.

Argo CD shows the app as **Progressing** for the whole ramp. That is normal.
It shows **Degraded** only when the gate workflow fails or the controller
cannot reach Temporal.

## Watch a rollout

From your workstation:

```bash
kubectl get workerdeployments -A -o json | jq '.items[] | {
  ns: .metadata.namespace, name: .metadata.name,
  observed: (.status.observedGeneration == .metadata.generation),
  current: .status.currentVersion.buildID,
  target: .status.targetVersion.buildID,
  gates: [.status.targetVersion.testWorkflows[]? | .status],
  ready: ([.status.conditions[]? | select(.type=="Ready") | .status][0])
}'
```

Expected during a rollout: `observed: true`, `target` set to the new Build
ID, gates `Running` then `Completed`, `ready: "False"`. Expected at the end:
`current` equals the new Build ID and `ready: "True"`.

From inside the cluster, with the Temporal CLI:

```bash
kubectl -n temporal exec -it deploy/temporal-admintools -- bash
temporal worker-deployment describe --name <deployment-name>
temporal worker-deployment list
```

`describe` lists every version with its status: `Current`, `Ramping`,
`Draining` or `Drained`. A `Draining` version still has pinned workflows.

If a gate fails: read its error in the Temporal UI at `temporal.vanillax.me`,
fix the image, publish again, open another PR. Do not delete the gate to get
past it.

## Long-running workflows

A workflow that never finishes never drains on its own. Radar's watch
workflows are this shape. The lab's pattern, which Radar implements:

1. Stay **pinned** while running, so replay is always safe.
2. When Temporal reports a newer version, finish the current step, wait for
   in-flight signal handlers, then **continue-as-new** with the
   `AUTO_UPGRADE` behaviour. The fresh run starts on the new version and
   carries its state forward as arguments.
3. A sleeping workflow does not notice a new version until it runs a task.
   Radar polls every 60 seconds, so it wakes itself. A workflow that only
   waits on a signal needs a no-op wake-up signal in its code, sent after
   the release:

   ```bash
   temporal workflow signal --workflow-id <workflow-id> --name <wake-up-signal>
   ```

Expected after a Radar release: each watch workflow shows a new Run ID within
a couple of minutes, and the old version drains once all of them have moved.

Versioning does not make breaking code changes safe. If you reorder or add
activities inside a loop, a workflow still fails when it replays across that
change. Continue-as-new is the boundary where such changes become safe.

## Roll back

1. Revert the image PR. That is the whole rollback for **new** work: the
   previous template is the current version again.
2. Workflows already pinned to the bad version stay there. Leave that version
   running until they finish or you recover them. Do not scale it down by
   hand and do not change routing with the CLI; the controller owns both.
3. To move a pinned workflow off a broken version, follow Temporal's
   [recover pinned workflows](https://docs.temporal.io/production-deployment/worker-deployments/recover-pinned-workflows)
   procedure for that one execution. Check its state afterwards and clear
   the override once the repaired version has processed it.

Expected after step 1: the reverted Build ID appears as `Current`, the bad one
as `Draining`, and no new workflow starts on it.

## Gotchas

- **A config change is a release.** Radar copies release settings into the
  pod template, so editing them creates a new Build ID. That is intended.
- **Keep old ConfigMaps until the last old Deployment is gone.** An old
  version restarts its pods from the original template. Check every retained
  Deployment, not just the running pods, before deleting anything it mounts:

  ```bash
  kubectl -n <namespace> get deployments -o json \
    | jq -r '.. | objects | .configMapRef?.name // .configMap?.name // empty' | sort -u
  ```

- **Two versions run at once.** Radar's five pools need capacity for two
  generations during a rollout. Check node headroom before adding replicas.
- **A gate against the wrong image blocks forever.** The gate workflow type
  must exist in the image being promoted.
- **The registry must keep every referenced image.** An old version that
  cannot pull its image cannot restart.

## Sources of truth

Concepts and the pattern this page follows:

- [Temporal Safe Deploys lab](https://syntaxsugar.io/lab/temporal-safe-deploys/) by Michael Jones
- [Lab repository](https://github.com/mikeacjones/temporal-safe-deploys-lab): `starter` is the exercise, `main` is the finished versioned worker
- [Temporal worker versioning](https://docs.temporal.io/production-deployment/worker-deployments/worker-versioning) and [recover pinned workflows](https://docs.temporal.io/production-deployment/worker-deployments/recover-pinned-workflows)
- [Temporal Worker Controller](https://github.com/temporalio/temporal-worker-controller)

What this cluster actually runs:

- [Controller chart values](https://github.com/mitchross/talos-argocd-proxmox/blob/main/infrastructure/controllers/temporal-worker-controller/values.yaml) and [CRD chart pins](https://github.com/mitchross/talos-argocd-proxmox/blob/main/infrastructure/controllers/temporal-worker-controller/kustomization.yaml)
- [Argo CD health rule for WorkerDeployment](https://github.com/mitchross/talos-argocd-proxmox/blob/main/infrastructure/controllers/argocd/values.yaml)
- [News Reader worker](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/development/news-reader/temporal-workers/temporal-worker-deployment.yaml)
- [Deal Scout worker](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/utility/deal-scout/temporal-workers/temporal-worker-deployment.yaml)
- [Radar worker pools](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/development/radar-ng/temporal-workers/worker-pools.yaml) and [release settings patch](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/development/radar-ng/temporal-workers/release-env-patch.yaml)
- [Manifest tests](https://github.com/mitchross/talos-argocd-proxmox/blob/main/scripts/tests/test_temporal_deployments.py)
