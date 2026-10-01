# Live prerequisite reconciliation gate

Current read-only procedure for staged changes to this repository's four
ApplicationSets (`infrastructure`, `monitoring`, `my-apps`, `database`). It
answers whether the exact prerequisite state for a dependent phase exists now.
It never merges a PR, refreshes Argo, changes a finalizer or deletes a resource.

The September 28 infrastructure regroup merged phase B only 29 seconds after
phase A. Git contained preservation, but the live controller still had old
paths/finalizers. A merged commit and `Healthy` are insufficient. See
[the entrypoint model](entrypoints.md) for controller ownership and waves.

## Inputs and read-only checks

Use Python 3.12+, git, kubectl and optionally authenticated `gh` for `--pr`.
Review a JSON expectation plan alongside the prerequisite PR. Explicitly name
the Kubernetes context/server, affected AppSets/Applications and persistent
resources that must survive. Record resource UIDs and PVC-to-PV bindings
**before the migration**; collecting replacement UIDs after an incident cannot
prove survival. For a stateful move include its Namespace, PVCs and PVs, not
just the Application. An empty resources list makes no persistence claim.

```sh
# Use the actual full merged SHA, not a pre-squash feature commit.
python3 scripts/gitops-live-gate.py --plan /tmp/prerequisite.json \
  --commit <40-character-merged-sha> --pr <pr-number>
python3 scripts/gitops-live-gate.py --plan /tmp/prerequisite.json \
  --commit <40-character-merged-sha> --pr <pr-number> --format json \
  > /tmp/prerequisite-evidence.json
```

The gate fetches `origin/main` and proves the commit is its ancestor; `--pr`
additionally verifies the specific PR is merged into main at that SHA. The
context must resolve to the reviewed server. All cluster commands are `get` or
`config view` with an explicit context; only the supported resource kinds can
be queried, never Secret objects.

Root must use this repository's entrypoint path, be Synced/Healthy, and have a
**Succeeded operation whose `syncResult.revision` is the prerequisite SHA**.
The comparison revision must agree with that operation. This avoids combining
an old successful operation with a newer comparison/cache revision. By default
require the exact SHA. `--allow-descendant` permits a later operation only if
Git proves it contains the prerequisite, is itself merged on main, and every
expected live field still matches. Unknown/unfetched revisions block.

Directly verify the AppSet's expected fields, generated Application source
paths/destinations, ownerReference UID/controller, expected resources-finalizer
presence/absence and consistency with live preservation policy. Each affected
Application must be Synced at the accepted revision, Healthy (or an explicitly
reviewed `acceptable_health` list), and have no failed or in-progress operation.
Persistent objects must keep baseline UIDs, not be terminating, match expected
fields, and PVCs must be Bound with the expected PV binding.

## Plan shape

This abbreviated example uses the **current** registry ownership. Before the
September move it was in `kube-system`; do not reuse current names/baselines to
verify historical safety. Replace placeholders with reviewed desired fields
and observations; this example is not an executable production plan.

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

`fields` uses RFC 6901 JSON pointers with exact expected JSON values; encode `/`
in annotation keys as `~1`. Missing fields fail even when the expectation is
null. Use the complete expected generator paths when the next phase depends on
path broadening; proving preservation alone does not prove those paths are live.

## Staged PR workflow and failure path

1. Open the prerequisite PR (paths/safety first, no directory move).
2. Wait for the user to explicitly merge that specific PR. Validation never
   authorizes an agent merge.
3. Run this gate against its actual merge SHA with the reviewed expectations.
4. Only after PASS, prepare/open the dependent move PR. The user explicitly
   merges that specific PR; rerun the gate immediately before that merge.
5. Verify the move and surviving UIDs, then prepare any separate cleanup PR.

A BLOCK exits 1. Unreachable APIs, absent resources, wrong ownership/fields,
missing revision evidence and unsupported input all block. Continue read-only
investigation; repair desired state through a separately reviewed PR. Do not
strip finalizers, delete/recreate Apps or storage, or force a sync to get a PASS.

JSON evidence records the commit, cluster identity, observation/completion
times, exact field checks and a five-minute `valid_until`. It is a snapshot,
not a lock or perpetual authorization: rerun after expiry, relevant changes or
immediately before the dependent action. No automatic consumer should accept a
saved PASS without enforcing those conditions. Backup recoverability still
needs separate snapshot/restore evidence; existence/UID checks prove only the
listed resources survived, not all cluster resources or absence of every prune.

CI runs offline regression tests only and receives no production credentials.
A trusted external runner could execute this same gate for a merge check later;
that integration and GitHub settings require separate authorization. The script
is independent of the static checker so both tooling PRs can be reviewed in
parallel; their validation responsibilities remain distinct.
