# Check a risky change before merge

`scripts/gitops-risk-check.py` compares two Git commits and reports changes that can make Argo CD delete Applications or storage.
Run it before you open a PR that moves app folders, edits an ApplicationSet, or changes persistent objects.
It reads only Git. It does not prove that the live cluster is safe, and it is not an Argo CD simulator.

The check exists for one failure in particular.
A folder move can keep every final Application name the same and still delete Applications.
That happens when the controller reads the new folder tree with the old ApplicationSet paths.
[Entrypoints and sync waves](entrypoints.md#move-folders-and-change-applicationset-paths-in-separate-prs) has the rule.

## Before you start

- Install Python 3.12+, PyYAML, Kustomize 5.8.3 and Helm 4.3.1. These match Cluster CI and Argo CD.
- Commit the scoped changes on a feature branch. The check reads committed Git trees and ignores working-tree edits.

## Run the check

```sh
python3 scripts/gitops-risk-check.py
python3 scripts/gitops-risk-check.py --format json > /tmp/gitops-risk.json
python3 -m unittest discover -s scripts/tests -p test_gitops_risk.py -v
```

By default the check fetches current `origin/main` and compares it with `HEAD`.
It rejects a candidate that does not contain current main. Update the feature branch and run the check again.
CI checks the proposed merge tree the same way.

`--base <commit> --head <commit> --no-fetch` compares two explicit commits offline.
Do not use it to hide a stale PR base.

The check uses no cluster credentials. It makes no cluster writes, no Git writes, and no merges.
The fetch updates remote tracking refs only. Rendering happens in temporary extracted trees.

## Read the result

| Result | Exit code | Meaning | What to do |
|---|---|---|---|
| PASS | 0 | No modeled transition risk found | Continue with normal review |
| WARN | 0 | A path, controller, or sync change needs review | Review the named change and any live prerequisite. A WARN does not authorize a merge |
| BLOCK | 1 | A modeled dangerous transition, or a failed or unsupported check | Stop the dependent phase. Investigate, or stage the migration |

An intentional retirement that returns BLOCK still needs explicit scope, recovery evidence, and human review.
The check has no blanket override switch.
Add a separately reviewed exception mechanism before you make this check required for intentional deletions.

The JSON output contains the exact base and head SHAs, the Application counts for all four states, the findings with old and new values, and the status.

## What the check models

### Which Applications exist

The rendered root entrypoints plus the manually seeded `root.yaml` define the active controllers.
For each Git directory ApplicationSet, the check models four states:

| Generator | Tree |
|---|---|
| old | old |
| old | new |
| new | old |
| new | new |

The two mixed states are the important ones. They model the time when the controller has one half of the change.

The check uses slash-bounded glob matches and exclude precedence.
A directory does not need a kustomization to be discovered, and intermediate category directories are included.
The supported Go templates are the forms this repo uses: path, basename, normalized basename, and indexed path segment.
An unsupported generator, template, or repository revision returns BLOCK, not PASS.

### What it reports

| Change | Result |
|---|---|
| An Application disappears, or its identity, owner, project, destination, explicit finalizer, generator path, or preservation policy changes | Reported |
| A source path is missing for a time, but the Application stays discovered | WARN, because a render failure differs from a deletion by the generator |
| A source moves while discovery stays stable | WARN, because the prerequisite can still be absent live |
| Preservation is removed | BLOCK |
| A change enables prune, Force, or Replace | BLOCK |
| Another Application sync policy changes | WARN |

### Persistent objects

The check renders each affected Application root at both revisions with Kustomize and Helm.
The render includes local resource and Component dependencies.
It compares Helm-rendered resources. It does not infer them from values files.

It compares persistent object identities and owners, the storage class, binding, and reclaim policy of PVCs and PVs, StatefulSet claim templates, and relevant finalizers.
A removal, a rename, or a storage transition returns BLOCK.

## Limits

A PASS cannot prove that no risk exists. Keep the normal render and schema CI, backup verification, and scoped review.

The check does not model these things:

- Claims that an operator creates.
- Mutable chart downloads.
- External or multi-source generators.
- Indirect workload data lineage.
- Every possible Argo CD prune interaction.

The ownership comparison covers the rendered affected roots.
The resources of an unchanged owner can need an additional render or a live inspection.

The test fixtures are a reduced copy of the monitoring tree.
They prove that the check flags the old-generator, new-tree disappearance even when the final identities match.
They do not reproduce live controller timing or hook order.

## After the check: stage the migration

A static PASS and a merged prerequisite PR do not prove that the live cluster reconciled.

1. Open a prerequisite PR that broadens paths or preserves resources, and moves nothing.
2. Wait for the user to merge it explicitly.
3. Verify the required fields, Applications, finalizers, and preserved resources **live**. Use the [live prerequisite check](live-prerequisite-gate.md).
4. Prepare the move PR only after that check passes.
5. Verify the move before you open a separate cleanup PR.

On a failure, continue read-only investigation and repair through a new PR.
Do not delete Applications, strip finalizers, or recreate storage to make a check pass.
