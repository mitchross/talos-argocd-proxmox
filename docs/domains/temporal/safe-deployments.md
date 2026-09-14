# Temporal safe worker deployments

Use this runbook to release workers without losing the ability to run an older
version. **Status:** desired release contract; application code and GitOps image
changes must both be reviewed before rollout. Tests described below run locally;
they do not establish that production has deployed or passed a restore drill.

## What was verified

The review used Talos `4158062b5`, Radar `f012385`, News Reader `8bd5269` on
Gitea, Deal Scout `d72509a`, the installed controller's v1.10.1 base, and all nine
clickable steps of [Michael Jones's guide](https://syntaxsugar.io/lab/temporal-safe-deploys/).
Its HTML contains all sections, but JavaScript turns them into nine pages.
The tutorial repository defaults to `starter`; its
[finished `main` branch](https://github.com/mikeacjones/temporal-safe-deploys-lab/tree/main)
contains the versioned worker and state-preserving handoff.

| Area | Keep or improve |
|---|---|
| Server | Keep the persistent Temporal/Postgres/kopiur setup and schema-hook ordering. It is a single Postgres instance, not database HA. A declared backup is not a demonstrated recovery. |
| Controller | Keep `WorkerDeployment` / `Connection`, separate controller and CRD charts, and the pinned inactive-retirement fork. [Upstream PR 577](https://github.com/temporalio/temporal-worker-controller/pull/577) was still open at review; do not remove the fix with an upstream image swap. |
| Worker identity | Keep workload-specific queues and overlapping worker versions. New finite News Reader and Deal Scout runs use `PINNED`; short duration does not guarantee safe replay. |
| Long-lived state | Radar carries frame/notification state, lifetime counters, and queued alerts through Continue-as-New. Only the per-run bound counter resets. Existing pinned runs need a separate, reviewed migration. |
| Promotion | All seven versioned worker resources declare a candidate gate. Existing ramps remain; Radar retains `AllAtOnce`, which controls promotion while old versions coexist. |

### A lifecycle correction

For the deployed v1.10.1 implementation, scale-down waits `scaledownDelay`
after the version becomes **Drained**. Deletion waits **`scaledownDelay +
deleteDelay` after Drained**, and also requires zero replicas and deletion
eligibility. With this repository's settings that is at least 10 minutes and
70 minutes, respectively. These are not timers measured from promotion.

The [controller implementation](https://github.com/temporalio/temporal-worker-controller/blob/v1.10.1/internal/planner/planner.go)
adds the delays, despite the shorter description in its concepts document.
Recheck the implementation when upgrading the controller. Do not alter the
manifest delays just to match the tutorial's prose.

## Release configuration belongs to a worker version

Radar's [release environment patch](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/development/radar-ng/temporal-workers/release-env-patch.yaml)
copies settings into every worker's pod template during Kustomize rendering.
A config edit changes the template and therefore the Build ID. An old generated
Deployment keeps its original literal environment when replacing a pod.
The old `radar-ng-temporal-config` ConfigMap remains frozen in Git for existing
versions that still use `envFrom`.

News Reader's image contains LiteLLM authentication. New workers no longer need
an init container to rewrite application source. Its hashed script ConfigMap
and source file remain rendered, unchanged, so an old worker can still restart.
Keep that generator until the last referencing Deployment is retired, including
scaled-to-zero versions retained for recovery. A later PR can remove it after
checking references. Do not edit the frozen script or remove it at promotion.

Application pruning stays enabled. Credential rotation remains a separate
lifecycle: environment-based secrets require replacement pods to pick up a new
value. Digest pins prevent registry tag reuse from changing an old worker's code.
The registry must also retain the referenced image layers.

## Before merging a release

Prerequisites: reviewed application PRs, published candidate images, `git`,
`kustomize`, `kubectl`, `jq`, and a Temporal CLI configured for the intended
namespace. Repository changes go through branches and PRs; merge requires the
operator's explicit approval. No direct Kubernetes template edits are needed.

1. Run the application tests and build the actual worker images. Radar's image
   build replays every retained synthetic history. Its integration test exercises
   V1→V2 with alerts on both sides of handoff; it uses SDK 1.30.0 against a local
   Temporal dev server. Production here declares server 1.32.0; the local CLI
   1.8.3 embeds 1.31.2, so the first staged rollout must verify that combination.
2. Pin each candidate by digest and enable its registered gate in the **same**
   GitOps PR. A gate against an older image that lacks the workflow will block.
   Record the image's source revision. Branch candidate images can be reviewed
   without merging application source first; stable release promotion follows
   the application's normal release pipeline after review. When that pipeline
   publishes a stable tag, update the SHA-tagged reference by PR to the stable
   tag and its verified digest; semver-only Renovate rules may skip SHA tags.
3. Render and test from the Talos repository root:

   ```bash
   kustomize build my-apps/development/radar-ng > /tmp/radar-workers.yaml
   kustomize build my-apps/development/news-reader > /tmp/news-workers.yaml
   kustomize build my-apps/utility/deal-scout > /tmp/deal-workers.yaml
   python -m unittest discover -s scripts/tests -p test_temporal_deployments.py -v
   ```

   Expect changed worker templates, registered gate names, image digests, the
   unchanged legacy ConfigMaps, and passing Lua health/config-lifetime tests.
4. Check overlap capacity and placement. The declared five Radar pools request
   6.75 CPU / 11 GiB for one generation; two complete generations need 13.5 CPU /
   22 GiB, before other apps. They share tile-server placement and RWO volumes.
   Do not add replicas without checking that node's actual available capacity.
5. After approval and merge, verify Argo and Temporal as below. A successful
   build, a green Pod, or elapsed ramp time alone is insufficient.

## Observe promotion

```bash
kubectl get workerdeployments -A -o json | jq '.items[] | {
  namespace: .metadata.namespace, name: .metadata.name,
  generation: .metadata.generation, observed: .status.observedGeneration,
  conditions: .status.conditions,
  target: .status.targetVersion.buildID,
  gates: .status.targetVersion.testWorkflows,
  current: .status.currentVersion.buildID
}'
```

Expect the current generation to be observed, each candidate gate to complete,
and `Ready=True` after promotion. Inspect the actual status field spellings if
upgrading CRDs. Argo remains `Progressing` for pollers, ramping, or stale status;
it reports `Degraded` for connection/auth/spec/plan failures and terminal failed
gate workflows. A failed gate may leave the controller's ordinary conditions
at `WaitingForPromotion`, so the health script checks gate status too.

| Gate | What it proves | Remaining boundary |
|---|---|---|
| Radar | Configured palettes, real PNG transformation, role-specific native libraries, scratch fsync/rename/read on all three volumes | No full forecast, upstream-feed or push-delivery test |
| News Reader | RSS fixture and bounded authenticated LiteLLM inference | Does not fetch every feed or publish a digest; uses a tiny inference request |
| Deal Scout | Parser fixture, required configuration, authenticated API read and database readiness | No scrape/browser job; checks eBay credential presence, not OAuth validity |

Each activity has a 90-second total schedule-to-close bound and at most two
attempts. If one fails, inspect its error and dependency, publish a corrected
candidate and open another PR. Do not remove the gate as a recovery shortcut.
Adding a gate to an already-current unchanged version is not a fresh validation;
these releases also change the image/template to create a new candidate.

## Verify old-version restartability

List all ConfigMaps referenced by retained generated Deployments:

```bash
kubectl -n news-reader get deployments -o json | jq -r '.. | objects | .configMapRef?.name // .configMap?.name // empty' | sort -u
kubectl -n radar-ng get deployments -o json | jq -r '.. | objects | .configMapRef?.name // .configMap?.name // empty' | sort -u
```

Every returned name must still exist in that namespace and remain in Git. New
Radar workers have literal release settings; new News Reader workers have no
script mount. Before removing a legacy ConfigMap, check **all** retained
Deployments, not just current pods. Treat image retention and shared storage
schema compatibility as dependencies too. Old and new code still share data.

The post-merge operational acceptance drill is to replace one retained
old-version pod during a controlled window and confirm it mounts its original
dependencies, registers its original Build ID, and resumes synthetic pinned
work. This review did not restart production pods. Do not remove a resource
merely because the new version is Healthy or because `PruneLast` finished.

## Rollback and existing pinned runs

1. Revert the faulty worker template through a GitOps PR to stop new traffic
   reaching it. Keep the bad version's image and configuration while its runs
   are investigated. Do not fight the controller with manual current/ramping
   changes; its manager identity owns routing.
2. Identify the affected execution and Run ID using read-only `temporal workflow
   describe` and version-filtered visibility queries. A rollout rollback does
   not move already-pinned executions. Visibility can lag; verify drainage and
   individual descriptions before declaring a version unused.
3. For Radar runs pinned to pre-fix code, keep their old workers alive. Replay a
   private export of the selected history with the fixed image. Existing patch
   markers preserve old command paths, but retained synthetic fixtures alone
   do not prove every real history is compatible. Do not commit real histories.
4. Only after explicit approval of the exact execution and destination, use
   Temporal's [pinned-workflow recovery procedure](https://docs.temporal.io/production-deployment/worker-deployments/recover-pinned-workflows).
   A pinned version override can be sticky: inspect it and explicitly clear it
   after the repaired version has processed the execution, verifying subsequent
   handoff and version assignment. Do not call the CLI override a one-time move
   or bulk-switch all workflows to `AUTO_UPGRADE`. Resetting stateful watches to
   their initial arguments loses accumulated state and can repeat side effects.
5. Verify the selected run's state, buffered alerts, new Run ID and assigned
   version. Stop if replay fails or state is incomplete. State discarded by an
   older completed handoff cannot be recovered merely by deploying this fix.

The Radar `wakeUpSignal` is optional; its existing 60-second polling also
generates workflow tasks. The version-change notification is remembered until
the safe boundary because a later task can clear the server's notification.
Upgrade-on-Continue-as-New remains an SDK Public Preview feature.

## Availability and recovery checks

Radar preserves its graceful worker shutdown and observe-only schedule
watchdog. Its new liveness file measures local event-loop progress; readiness
measures Temporal connectivity. A shared Temporal outage should affect
readiness without restarting every worker. Readiness itself does not stop SDK
polling. Compare poll-failure metrics, queue latency/backlog, and controller
registration when an apparently healthy process stops doing work.

Before claiming disaster recovery, perform a separate approved restore drill
in an isolated environment using the [kopiur recovery runbook](../../disaster-recovery.md):
start a synthetic workflow, record its state, capture a successful Postgres
backup, restore it, and demonstrate that the same execution resumes with its
recorded history and expected result. Avoid duplicate external side effects by
using fake activities and isolated endpoints. Record snapshot identity, restore
time, resumed Run ID and result. Do not test by overwriting production Postgres.

Per-version autoscaling through `WorkerResourceTemplate` remains an option
after measuring capacity and backlog. It is not required for this repair and
does not replace correct version retirement.

## Sources of truth

- [Controller values and retained fork](https://github.com/mitchross/talos-argocd-proxmox/blob/main/infrastructure/controllers/temporal-worker-controller/values.yaml)
- [Argo health mapping](https://github.com/mitchross/talos-argocd-proxmox/blob/main/infrastructure/controllers/argocd/values.yaml)
- [News worker manifest](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/development/news-reader/temporal-workers/temporal-worker-deployment.yaml)
- [Radar worker pools](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/development/radar-ng/temporal-workers/worker-pools.yaml)
- [Deal Scout worker manifest](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/utility/deal-scout/temporal-workers/temporal-worker-deployment.yaml)
