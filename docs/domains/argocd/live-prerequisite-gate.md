# Check the live cluster before the next phase

`scripts/gitops-live-gate.py` answers one question. Does the live cluster have the exact state that the next PR depends on?
Run it between the phases of a staged change to one of the four ApplicationSets (`infrastructure`, `monitoring`, `my-apps`, `database`).
The check is read-only. It never merges a PR, refreshes Argo CD, changes a finalizer, or deletes a resource.

A merged commit is not a live change.
Git can contain a safety setting while the live controller still has the old paths and finalizers.
A second phase that merges seconds after the first can therefore delete Applications.
An Application that reads `Healthy` does not prove the change applied either.
[Entrypoints and sync waves](entrypoints.md) explains which controller owns what, and the wave order.

## Before you start

- Install Python 3.12+, git, and kubectl. Install an authenticated `gh` to use `--pr`.
- Write a JSON expectation plan and review it alongside the prerequisite PR. [Plan shape](#plan-shape) has an example.
- Record resource UIDs and PVC-to-PV bindings **before the migration**. UIDs collected after an incident cannot prove survival.

The plan names these things:

- The Kubernetes context and server.
- The affected ApplicationSets and Applications.
- The persistent resources that must survive.

For a stateful move, include the Namespace, the PVCs, and the PVs, not only the Application.
An empty resources list makes no claim about persistence.

## Run the check

```sh
# Use the actual full merged SHA, not a pre-squash feature commit.
python3 scripts/gitops-live-gate.py --plan /tmp/prerequisite.json \
  --commit <40-character-merged-sha> --pr <pr-number>
python3 scripts/gitops-live-gate.py --plan /tmp/prerequisite.json \
  --commit <40-character-merged-sha> --pr <pr-number> --format json \
  > /tmp/prerequisite-evidence.json
```

A PASS means every expectation in the plan matched the live cluster at that moment.
A BLOCK exits 1. [When the check blocks](#when-the-check-blocks) lists the causes.

## What the check verifies

### The commit

The check fetches `origin/main` and proves that the commit is its ancestor.
With `--pr`, it also verifies that the PR merged into main at that SHA.

### The cluster

The context must resolve to the reviewed server.
Every cluster command is `get` or `config view` with an explicit context.
The check queries only supported resource kinds, and never Secret objects.

### The root Application

The root Application must meet all of these conditions:

- It uses this repo's entrypoint path.
- It is Synced and Healthy.
- It has a **Succeeded operation whose `syncResult.revision` is the prerequisite SHA**.
- Its comparison revision agrees with that operation.

The last two conditions stop the check from combining an old successful operation with a newer comparison or cache revision.

By default the check requires the exact SHA.
`--allow-descendant` permits a later operation only under three conditions.
Git must prove that the later commit contains the prerequisite. The later commit must be merged on main.
Every expected live field must still match.
An unknown or unfetched revision returns BLOCK.

### ApplicationSets and Applications

The check verifies these items:

- The expected fields of the ApplicationSet.
- The source path and destination of each generated Application.
- The ownerReference UID and controller.
- The expected presence or absence of the resources finalizer, and its consistency with the live preservation policy.

Each affected Application must be Synced at the accepted revision and have no failed or in-progress operation.
It must be Healthy, or match a reviewed `acceptable_health` list.

### Persistent objects

Each persistent object must keep its baseline UID, must not be terminating, and must match its expected fields.
Each PVC must be Bound to the expected PV.

## Plan shape

This shortened example uses the container registry's current path and namespace.
Replace every placeholder with a reviewed desired field or a recorded observation.
The example is not an executable production plan.

```json
{
  "context": "<reviewed-kubectl-context>",
  "server": "<reviewed-kubernetes-server-url>",
  "application_sets": [{
    "name": "infrastructure",
    "fields": {
      "/spec/syncPolicy/preserveResourcesOnDeletion": true,
      "/spec/generators/0/git/directories": [{"path": "infrastructure/platform/container-registry"}, {"path": "<include all other expected paths>"}]
    }
  }],
  "applications": [{
    "name": "infrastructure-container-registry",
    "owner_appset": "infrastructure",
    "resources_finalizer": "absent",
    "fields": {
      "/spec/source/path": "infrastructure/platform/container-registry",
      "/spec/destination/namespace": "container-registry"
    }
  }],
  "resources": [{
    "kind": "PersistentVolumeClaim",
    "name": "<actual-registry-claim>",
    "namespace": "container-registry",
    "uid": "<pre-migration-claim-uid>",
    "fields": {"/spec/volumeName": "<pre-migration-pv>", "/spec/storageClassName": "longhorn"}
  }, {
    "kind": "PersistentVolume",
    "name": "<pre-migration-pv>",
    "uid": "<pre-migration-pv-uid>",
    "fields": {"/spec/claimRef/uid": "<pre-migration-claim-uid>"}
  }, {
    "kind": "Namespace",
    "name": "container-registry",
    "uid": "<pre-migration-namespace-uid>",
    "fields": {}
  }]
}
```

`fields` uses RFC 6901 JSON pointers with exact expected JSON values.
Encode `/` in an annotation key as `~1`.
A missing field fails, even when the expected value is null.

Use the complete list of expected generator paths when the next phase depends on broader paths.
Proof of preservation alone does not prove that those paths are live.

Record baselines from the cluster as it is before the migration.
Names and UIDs recorded after a move cannot verify the state before it.

## Staged PR workflow

1. Open the prerequisite PR. It changes paths or safety settings and moves no directory.
2. Wait for the user to merge that specific PR. A passing check never authorizes an agent to merge.
3. Run this check against the actual merge SHA with the reviewed expectations.
4. After a PASS, prepare and open the dependent move PR.
5. Run the check again immediately before the user merges that PR.
6. Verify the move and the surviving UIDs. Then prepare any separate cleanup PR.

## When the check blocks

These conditions all return BLOCK:

- An unreachable API.
- An absent resource.
- Wrong ownership or wrong fields.
- Missing revision evidence.
- Unsupported input.

Continue read-only investigation. Repair the desired state through a separately reviewed PR.
Do not strip finalizers, delete or recreate Applications or storage, or force a sync to get a PASS.

## What the evidence proves

The JSON evidence records the commit, the cluster identity, the observation and completion times, the exact field checks, and a five-minute `valid_until`.
It is a point-in-time record. It is not a lock, and it does not authorize anything after it expires.
Run the check again after expiry, after a relevant change, or immediately before the dependent action.
An automatic consumer must not accept a saved PASS without enforcing those conditions.

The existence and UID checks prove only that the listed resources survived.
They do not cover every cluster resource, and they do not prove that nothing else was pruned.
Whether a backup can be restored needs separate backup and restore evidence.

## How CI uses this script

CI runs offline regression tests only and receives no production credentials.
A trusted external runner could run this check as a merge check.
That integration and the GitHub settings need separate authorization.

This script is independent of the [static check](gitops-risk-check.md).
The static check reads Git before a PR. This check reads the live cluster after a merge.
