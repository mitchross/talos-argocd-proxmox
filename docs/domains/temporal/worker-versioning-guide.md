# Temporal worker versioning: from homelab to production

**A deploy does not just replace pods. It replaces code that must keep finishing
work it started hours or days ago.** This guide explains how Temporal worker
versioning works on Kubernetes and Argo CD. It lists the failures this lab hit,
and the checks that stop them in a production cluster.

**Status:** concept guide and failure catalog for the live cluster.
**Scope:** application workers, the Temporal Worker Controller, and the Argo CD
path that ships them. For the release procedure, use
[Temporal safe worker deployments](safe-deployments.md). For the Temporal
server, use the
[server README](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/development-infra/temporal/README.md).

!!! note "Homelab versus production"
    In a homelab you can delete a broken workflow and redeploy. In production
    a workflow can be an order, a payment, or a three-day job. You cannot throw
    it away. Every rule below assumes you cannot.

## The parts

| Part | What it does |
|---|---|
| **Image** | Your worker code, built and tagged, for example `v1.4.2@sha256:…`. |
| **Argo CD** | Makes the cluster match Git. You change Git; Argo CD applies it. |
| **Worker** | A pod that asks Temporal for work and runs workflow and activity code. |
| **History** | Temporal records every step a workflow takes. |
| **Replay** | When a worker restarts, another worker re-runs the workflow code against the history. If the code now decides differently, the workflow fails with a non-determinism error. |
| **Build ID** | The identity of one worker version. Temporal routes each workflow to the right Build ID. |
| **Temporal Worker Controller** | A Kubernetes controller. It runs one Deployment per Build ID, runs a gate workflow, ramps traffic, and deletes drained versions. |

Each workflow follows one **versioning behavior**:

- **Pinned:** the workflow finishes on the Build ID it started on. Replay is
  always safe. The old version must stay alive until its last pinned workflow
  ends.
- **Auto-upgrade:** the workflow moves to the newest Build ID at its next task.
  Old versions drain fast. The new code must replay old histories correctly.

All workers in this lab default to **pinned**.

## How a release flows

1. A merge builds an image with a version tag and a digest.
2. CI replays saved workflow histories against the new code. A failed replay
   stops the release.
3. A PR changes the image in the app's `WorkerDeployment`. A person reviews it.
4. Argo CD syncs the `WorkerDeployment`.
5. The controller creates a new Deployment and waits for it to poll Temporal.
6. The controller runs the gate workflow, then ramps new work to the new version.
7. The old version becomes **Drained** when nothing is pinned to it.
8. The controller scales it down after `scaledownDelay` and deletes it after
   `scaledownDelay + deleteDelay`, both counted from Drained.

## Failure catalog

Each entry gives the symptom, the cause, how to test for it, and how to
prevent it.

### Versioning is off, and nothing reports it

- **Symptom:** the rollout waits forever for the new version to register. Old
  Deployments are never deleted. Several versions run old code at once.
- **Cause:** the worker did not receive its deployment options, so it polled
  without a Build ID. A misspelled SDK option name does this silently in
  plain JavaScript. For example, `useVersioning` is the deprecated Build-ID
  API; the current option is `useWorkerVersioning`.
- **Test:** after each release, confirm that the new Build ID polls the task
  queue. Pass `--select-all-active`; without it, versioned pollers do not show.

    ```bash
    temporal task-queue describe --task-queue <queue> --select-all-active
    ```

- **Prevent:**
    - Log `versioning ON, build <id>` at worker start.
    - Build the options only from the `TEMPORAL_DEPLOYMENT_NAME` and
      `TEMPORAL_WORKER_BUILD_ID` variables the controller injects. Never set
      them by hand.
    - Alert when a target version stays unregistered for more than 10 minutes.

### The Build ID does not change when you expect, or changes when you do not

- **Symptom:** a change merges and nothing rolls. Or a small config edit starts
  a full rollout.
- **Cause:** the controller hashes the pod template plus the `Connection` into
  the Build ID. The image tag is only one input. A change to
  `temporalNamespace` alone does not change the hash. Any env var or mounted
  config change does.
- **Test:** for each change type (image, env, config, namespace, resources),
  record whether `.status.targetVersion.buildID` changes.
- **Prevent:**
    - Ship a namespace move together with a pod-template change, such as a
      harmless env var.
    - Never mix an image bump with routing, storage, or flag changes.
    - Keep old ConfigMaps and images until the last old Deployment is deleted.
      An old version restarts from its original template.

### One stuck pinned workflow stops a schedule

- **Symptom:** a schedule stops firing. Argo CD shows Synced and the controller
  shows `RolloutComplete`.
- **Cause:** a run is pinned to a Build ID that no longer has workers. No one
  can finish it. The schedule uses overlap policy **Skip**, so every later
  fire is skipped.
- **Test:** after each promotion, list running workflows pinned to Build IDs
  with no pollers. The count must be zero.
- **Prevent:**
    - Give every workflow an execution timeout of about two to three times its
      normal run time.
    - Alert on overdue schedules, not only on pod health.
    - Keep a runbook for these orphans. Radar's is in
      [`radar-ng/RUNBOOK.md`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/personal-projects/radar-ng/RUNBOOK.md).

### New code breaks workflows already running

- **Symptom:** non-determinism errors after a release.
- **Cause:** an auto-upgrade workflow replayed its history on code that takes a
  different path. A short workflow is not automatically safe: retries can
  outlast the ramp. Common code causes are reordered activities and timers that
  are not cancelled when another branch wins.
- **Test:** store real histories as fixtures, with private data removed. Replay
  every fixture in CI before an image is published. Add fixtures; never edit
  old ones.
- **Prevent:**
    - Put logic changes behind a patch marker, for example
      `patched("my-change-v1")`. Old histories then take the old path.
    - Default to pinned. Use auto-upgrade only where replay tests cover the
      workflow.
    - Keep a patch marker until no retained history predates it.

### Long-running workflows keep old versions alive

- **Symptom:** an old version stays **Draining** for days.
- **Cause:** a pinned workflow that never ends never drains. An idle workflow
  does not see a new version until it runs a task.
- **Prevent:**
    - At safe points, check whether the target version changed. If it did,
      **continue-as-new** with the auto-upgrade behavior.
    - The SDK reports that change on one task and can clear it on the next.
      Store it in workflow state until the safe point.
    - Wake idle workflows with a timer or a no-op signal.
    - Change state shape in two releases: add a field with a default first,
      remove the old field later.

### The controller loses its identity

- **Symptom:** every `WorkerDeployment` fails with `PlanExecutionFailed` and a
  ManagerIdentity mismatch.
- **Cause:** the controller stamps an identity on each Temporal worker
  deployment. The identity includes the Kubernetes namespace UID. A recreated
  namespace or a second controller replica produces a different identity.
- **Prevent:**
    - Run exactly one controller replica. The chart key is top-level
      `replicas`.
    - Protect the controller namespace from pruning and deletion.
    - Clear a stale identity with the CLI. Pass `--yes`; without it the
      command stops at its prompt and changes nothing. Full steps are in
      [`radar-ng/RUNBOOK.md`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/personal-projects/radar-ng/RUNBOOK.md).

    ```bash
    temporal worker deployment manager-identity unset \
      --namespace <temporal-namespace> \
      --deployment-name <k8s-namespace>/<workerdeployment-name> \
      --identity '<old status.managerIdentity>' --yes
    ```

### Versions that never went live are not deleted

- **Symptom:** versions scaled to zero stay forever.
- **Cause:** a version superseded before it became current or ramping is
  **Inactive**, not Drained. The upstream controller does not retire Inactive
  versions
  ([PR #577](https://github.com/temporalio/temporal-worker-controller/pull/577)).
- **Prevent:** do not release faster than a rollout completes. Monitor the
  version count per deployment.

### Old workers overwrite shared settings

- **Symptom:** schedules return to old settings after a rollout.
- **Cause:** every worker writes its schedules at start. Old pods start too.
- **Prevent:** only the current Build ID writes schedules. Compare a spec hash
  before writing. Do not write when the ownership check fails.

### A rollout kills work in progress

- **Symptom:** activities fail or restart during every rollout.
- **Cause:** the default 30-second termination grace period is shorter than
  the activity.
- **Prevent:**
    - Set `terminationGracePeriodSeconds` longer than the longest activity.
    - Heartbeat long activities so they resume.
    - Leave capacity for three versions at once: current, target, and draining.

### Healthy status that is not true

- **Symptom:** dashboards are green, but work does not complete.
- **Cause:**
    - The controller owns the image field through server-side apply, so Argo
      CD can show Synced while the old image runs. A hard refresh fixes the
      view.
    - The controller ignores the deprecated `TemporalWorkerDeployment` and
      `TemporalConnection` kinds, so those objects look healthy but never roll.
- **Prevent:**
    - Treat "deployed" and "working" as two separate checks.
    - Run a gate workflow on every version.
    - Alert on completed workflows, on-time schedules, and active pollers.
    - Read the controller release notes before each upgrade. Check for renamed
      CRDs and changed defaults.

## Platform rules

- Upgrade one layer at a time: server, Helm chart, controller, then SDK. Check
  compatibility for each.
- Run schema migrations as an Argo CD Sync hook with `activeDeadlineSeconds`.
  A hook with no deadline can block every later sync.
- Keep the chart shims disabled. With shims on, the wave `-1` schema hook
  waits for a ConfigMap that is created later.
- Do not let automation restart the only Temporal database. A recreate takes
  every history shard offline.
- Postgres major versions do not upgrade in place. Never auto-merge a major
  database bump.
- Require human review for Temporal, controller, and database updates.

## Test plan

Run these in a staging cluster before production. Each line gives the action
and the expected result.

| # | Action | Expected result |
|---|---|---|
| 1 | Release an image whose gate workflow fails. | The rollout stops. The current version keeps serving. Argo CD shows Degraded. |
| 2 | Delete a new-version pod during the ramp. | The activity retries and the workflow completes. |
| 3 | Delete old-version pods while a pinned workflow runs. | The orphan or overdue-schedule alert fires. |
| 4 | Push a workflow change with no patch marker. | CI replay fails. No image is published. |
| 5 | Release two versions a few minutes apart. | No unexpected version remains after the sunset timers. |
| 6 | Recreate the controller namespace. | Rollouts continue after identity recovery. |
| 7 | Restart the Temporal database. | Schedules resume. No timer is lost. |
| 8 | Change only the namespace, then only one config value. | Each result matches the Build ID rules above. |

## Homelab habit, production habit

| Homelab | Production |
|---|---|
| Delete it and redeploy. | Fix forward with a new version. Never revert the image or move traffic by hand. |
| Terminate stuck workflows. | Prevent them with timeouts and alerts. Keep a runbook. |
| "Argo CD says Synced." | Prove that work completes. |
| Upgrade everything together. | Upgrade one layer at a time, after the release notes. |
| Auto-merge dependency updates. | Review Temporal, controller, and database updates. |
| Fix it live. | Ship every change through Git, a PR, Argo CD, and a gate. |

## Sources of truth

- [Temporal safe worker deployments](safe-deployments.md): release, watch, and
  fix-forward procedures for this cluster
- [Temporal worker versioning](https://docs.temporal.io/production-deployment/worker-deployments/worker-versioning)
- [Recover pinned workflows](https://docs.temporal.io/production-deployment/worker-deployments/recover-pinned-workflows)
- [Temporal Worker Controller](https://github.com/temporalio/temporal-worker-controller)
- [Temporal Safe Deploys lab](https://syntaxsugar.io/lab/temporal-safe-deploys/) by Michael Jones
- [Controller values](https://github.com/mitchross/talos-argocd-proxmox/blob/main/infrastructure/platform/temporal-worker-controller/values.yaml)
- [Manifest tests](https://github.com/mitchross/talos-argocd-proxmox/blob/main/scripts/tests/test_temporal_deployments.py)
