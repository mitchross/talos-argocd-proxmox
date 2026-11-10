# Temporal safe worker deployments

This runbook releases a new version of a Temporal worker, the process that
runs workflow code. It changes the worker image in Git. It does not touch
workflows already in flight or the Temporal server.

**Ship a new worker by changing its image in Git. Never edit a running worker.**
The controller starts the new version next to the old one and runs a smoke
workflow. It then ramps new work to the new version and retires the old version
once its workflows finish.

The runbook covers the application workers: News Reader, Deal Scout and Radar.
For the Temporal server, use the
[server README](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/development-infra/temporal/README.md).
For the concepts and the failure catalog, read
[Temporal worker versioning](worker-versioning-guide.md).

This page applies Michael Jones's
[Temporal Safe Deploys lab](https://syntaxsugar.io/lab/temporal-safe-deploys/)
to the manifests in this Git repo. Read the lab once if the terms Build ID,
pinned and drained are unfamiliar. It takes about an hour.

## The idea in five lines

1. A workflow that started on version A must finish on version A. Replaying
   its history against different code fails with a non-determinism error.
2. Every worker image therefore gets a **Build ID**. Each workflow is
   **pinned** to the Build ID it started on.
3. The Temporal Worker Controller runs one Kubernetes Deployment per Build ID,
   all on the same task queue. Temporal routes each task to the right one.
4. New work goes to the newest version only after its **gate** workflow, a
   smoke test, passes and its **ramp**, the stepwise traffic shift, finishes.
5. An old version is **drained** when no workflow is pinned to it. The
   controller then scales it down and deletes it on a timer.

## What runs here

Every app has one `Connection` named `cluster-temporal` that points at
`temporal-frontend.temporal.svc.cluster.local:7233`. Every app also has one or
more `WorkerDeployment` resources. Use exactly these `kind` names. The
controller ignores the deprecated `Temporal*` kinds, so an image bump on those
never rolls.

| App | WorkerDeployment | Rollout | Gate workflow | Sunset |
|---|---|---|---|---|
| News Reader | `news-digest` | Progressive: 10% for 2 min, then 50% for 5 min | `NewsDeploymentSmokeWorkflow` | scale down 10 min, delete 1 h |
| Deal Scout | `deal-scout` | Progressive: 50% for 2 min | `DealScoutDeploymentSmokeWorkflow` | scale down 10 min, delete 1 h |
| Radar | five `radar-ng-worker-*` pools | All at once | `RadarDeploymentSmokeWorkflow` | scale down 10 min, delete 1 h |

Radar uses all-at-once because its five pools share volumes and must move
together. It still keeps the old version alive until every pinned run drains.

The sunset timers count from the moment a version becomes Drained, not
from promotion. Deletion waits `scaledownDelay + deleteDelay` after Drained,
so an old version lives at least 70 minutes past its last pinned workflow.

## Before you start

- Publish the new worker image first. Radar and Deal Scout pin by digest. News
  Reader uses a plain `vMAJOR.MINOR.PATCH` tag that is never overwritten.
- Keep every image and ConfigMap that an old version references. An old
  version restarts its pods from its original template.
- Check node headroom. Two versions run at once during a rollout.

## Release a worker

A release needs about 15 minutes of your attention. The controller does the
waiting.

1. Confirm that the new worker image is published.
2. Open a PR that changes only the image line in the app's `WorkerDeployment`.
   Any change to the pod template, image or environment creates a new Build ID.
3. Before you merge, render and test from the root of the Git repo:

   ```bash
   kustomize build my-apps/personal-projects/news-reader > /dev/null
   kustomize build my-apps/personal-projects/radar-ng > /dev/null
   kustomize build my-apps/personal-projects/deal-scout > /dev/null
   python -m unittest discover -s scripts/tests -p test_temporal_deployments.py -v
   ```

   Expected: every build renders and every test passes.
4. Merge the PR. Argo CD syncs the `WorkerDeployment`. The controller creates
   the new Deployment, waits for it to poll, runs the gate workflow, then ramps.
5. Watch the rollout with the commands in the next section. The release is
   complete when the resource is `Ready` and the old version shows `Drained`.

Argo CD shows the Application as Progressing for the whole ramp. That is
normal. It shows Degraded only when the gate workflow fails or the controller
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

If a gate fails, read its error in the Temporal UI at `temporal.vanillax.me`.
Fix the image, publish it again, and open another PR. Do not delete the gate to
get past it.

## Long-running workflows

A workflow that never finishes never drains without help. Radar's watch
workflows are of this kind. Radar implements the pattern from the lab:

1. The workflow stays pinned while it runs, so replay is always safe.
2. When Temporal reports a newer version, the workflow finishes the current
   step and waits for in-flight signal handlers. It then calls continue-as-new
   with the `AUTO_UPGRADE` behaviour. Continue-as-new ends the run and starts a
   fresh run on the new version, with its state passed as arguments.
3. A sleeping workflow does not see a new version until it runs a task. Radar
   polls every 60 seconds, so it wakes itself. A workflow that only waits on a
   signal needs a no-op wake-up signal in its code. Send it after the release:

   ```bash
   temporal workflow signal --workflow-id <workflow-id> --name <wake-up-signal>
   ```

Expected after a Radar release: each watch workflow shows a new Run ID within
a couple of minutes, and the old version drains once all of them have moved.

Versioning does not make breaking code changes safe. If you reorder or add
activities inside a loop, a workflow still fails when it replays across that
change. Such a change is safe only across a continue-as-new, because the fresh
run has no old history to replay.

## Fix a bad release (forward-only)

This is the rollback procedure. A release rolls forward only. Do not revert to
an older image.

1. Publish a fixed image and open a new image PR. The new version supersedes
   the bad one for new work only.

    Expected result: the fixed Build ID appears as `Current`, the bad one as
    `Draining`, and no new workflow starts on the bad one.
2. Leave the bad version running. Workflows already pinned to it stay there
   until they finish or you recover them. Do not scale it down by hand, and do
   not change routing with the CLI. The controller owns both.
3. To move a pinned workflow off a broken version, follow Temporal's
   [recover pinned workflows](https://docs.temporal.io/production-deployment/worker-deployments/recover-pinned-workflows)
   procedure for that one execution. Check its state afterwards. Clear the
   override once the repaired version has processed it.

## Gotchas

- A config change is a release. Radar copies release settings into the pod
  template, so an edit to them creates a new Build ID. That is intended.
- Keep old ConfigMaps until the last old Deployment is deleted. An old version
  restarts its pods from the original template. Before you delete anything a
  Deployment mounts, check every retained Deployment, not only the running pods:

  ```bash
  kubectl -n <namespace> get deployments -o json \
    | jq -r '.. | objects | .configMapRef?.name // .configMap?.name // empty' | sort -u
  ```

- Two versions run at once. Radar's five pools need capacity for two
  generations during a rollout. Check node headroom before you add replicas.
- A gate against the wrong image blocks the rollout forever. The gate workflow
  type must exist in the image being promoted.
- The registry must keep every referenced image. An old version that cannot
  pull its image cannot restart.

## Sources of truth

These pages explain the concepts and the pattern that this page follows:

- [Temporal Safe Deploys lab](https://syntaxsugar.io/lab/temporal-safe-deploys/) by Michael Jones
- [Lab repository](https://github.com/mikeacjones/temporal-safe-deploys-lab): `starter` is the exercise, `main` is the finished versioned worker
- [Temporal worker versioning](https://docs.temporal.io/production-deployment/worker-deployments/worker-versioning) and [recover pinned workflows](https://docs.temporal.io/production-deployment/worker-deployments/recover-pinned-workflows)
- [Temporal Worker Controller](https://github.com/temporalio/temporal-worker-controller)

These files define what this cluster runs:

- [Controller chart values](https://github.com/mitchross/talos-argocd-proxmox/blob/main/infrastructure/platform/temporal-worker-controller/values.yaml) and [CRD chart pins](https://github.com/mitchross/talos-argocd-proxmox/blob/main/infrastructure/platform/temporal-worker-controller/kustomization.yaml)
- [Argo CD health rule for WorkerDeployment](https://github.com/mitchross/talos-argocd-proxmox/blob/main/infrastructure/controllers/argocd/values.yaml)
- [News Reader worker](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/personal-projects/news-reader/temporal-workers/temporal-worker-deployment.yaml)
- [Deal Scout worker](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/personal-projects/deal-scout/temporal-workers/temporal-worker-deployment.yaml)
- [Radar worker pools](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/personal-projects/radar-ng/temporal-workers/worker-pools.yaml) and [release settings patch](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/personal-projects/radar-ng/temporal-workers/release-env-patch.yaml)
- [Manifest tests](https://github.com/mitchross/talos-argocd-proxmox/blob/main/scripts/tests/test_temporal_deployments.py)
