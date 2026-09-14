# News Reader Temporal workers

This directory is part of the `news-reader` Argo application. It deploys a
namespace-scoped `Connection` and `WorkerDeployment` into **`news-reader`**;
application code and the image build live in
[the News Reader repository](https://gitea.vanillax.me/vanillax/news-reader/src/branch/main/temporal).

**Status:** release contract. Use the [safe deployment runbook](../../../../docs/domains/temporal/safe-deployments.md)
for validation, old-version retention, and recovery of already-pinned runs.
The [Temporal server](../../temporal/README.md) is a separate application.

## Release flow

1. Build and test the application image, which includes LiteLLM authentication
   and registers `NewsDeploymentSmokeWorkflow`. Record its source revision.
2. Open a GitOps PR updating the digest-pinned image in
   [the worker manifest](temporal-worker-deployment.yaml). The controller derives
   the Build ID from the pod template; it is not simply the image tag.
3. After approval and merge, the candidate gate runs a bounded authenticated
   inference and RSS fixture check. Only a passing gate permits the existing
   10%/2-minute, then 50%/5-minute ramp to progress to full traffic.
4. Inspect `Ready`, gate outcomes and current/target Build IDs. A failed gate
   blocks promotion. Publish a corrected candidate through another PR.

New finite digest workflows are pinned for each run. The long-lived user-state
workflow carries state and requests an upgrade at Continue-as-New. Existing
runs retain their previous policy until their own safe boundary or an explicitly
reviewed recovery. A brief ramp does not by itself prove meaningful work ran.

## Configuration lifetime

New pods use authentication packaged in the image. The app's
[Kustomization](../kustomization.yaml) deliberately retains the **unchanged**
legacy script generator for older versions that mount its hashed ConfigMap.
Do not edit or remove that script until every referencing Deployment is retired,
including versions scaled to zero for recovery. Keep app pruning enabled.

Retirement starts from **Drained**, not promotion. With the installed v1.10.1
controller and these settings, scale-down is eligible after 10 minutes and
version deletion after **70 minutes** (the two delays are added). Actual deletion
also requires zero replicas and eligibility; old pinned runs can delay drainage.

## Read-only checks

Run with `kubectl` configured for this cluster:

```bash
kubectl -n news-reader get workerdeployments,connections
kubectl -n news-reader get workerdeployment news-digest -o yaml
kubectl -n news-reader get deployments
kubectl -n news-reader logs -l app=news-reader-temporal-worker --tail=100
```

Expect current-generation status, a completed gate and `Ready=True` after the
ramp. Old versioned Deployments can remain present while their workflows finish.
If promotion fails, follow the [central recovery procedure](../../../../docs/domains/temporal/safe-deployments.md#rollback-and-existing-pinned-runs);
reverting traffic does not rescue workflows already pinned to a faulty build.

Per-version autoscaling is deferred until this single-user workload needs it.
Use `WorkerResourceTemplate` for a future HPA instead of targeting a generated
Deployment name directly.
