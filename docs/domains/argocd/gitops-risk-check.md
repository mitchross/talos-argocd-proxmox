# Static GitOps transition check

This is the current V1 pre-PR check for this repository's directory-based
ApplicationSets, not a proof of live safety or an Argo CD simulator. It exists
because the September 28 reorganization kept final Application names stable
while the controller's old path spec against the new tree deleted Applications.
See [entrypoints and preservation behavior](entrypoints.md).

## Run before opening a PR

Use Python 3.12+, PyYAML, Kustomize 5.8.1 and Helm 4.3.0 (the Cluster CI/Argo
versions). Commit the scoped changes on a feature branch first; the checker
reads committed Git trees and ignores working-tree edits.

```sh
python3 scripts/gitops-risk-check.py
python3 scripts/gitops-risk-check.py --format json > /tmp/gitops-risk.json
python3 -m unittest discover -s scripts/tests -p test_gitops_risk.py -v
```

The default fetches current `origin/main` and compares it with `HEAD`. It rejects
an outdated candidate that does not contain current main: update the feature
branch and rerun. CI checks the proposed merge tree with the same behavior.
`--base <commit> --head <commit> --no-fetch` supports explicit offline/historical
comparisons; it must not be used to disguise a stale PR base.

- **PASS**, exit 0: no modeled transition risks found.
- **WARN**, exit 0: review the named path/controller/sync change and any required
  live prerequisites; this does not authorize merging.
- **BLOCK**, exit 1: a modeled dangerous transition or failed/unsupported check.
  Stop the dependent phase. Investigate or stage the migration; an intentional
  retirement still needs explicit scope, recovery evidence and human review.
  V1 has no blanket override switch. A separately reviewed exception mechanism
  is needed before making this check required for intentional deletions.

JSON contains exact base/head SHAs, Application counts for all four states,
findings with old/new values and the resulting status. No cluster credentials,
cluster writes, Git writes or automatic merges are used (fetch updates remote
tracking refs only). Rendering happens in temporary extracted trees.

## What is checked

The rendered root entrypoints plus manually seeded `root.yaml` define active
controllers. For each Git directory ApplicationSet, model **old generator/old
tree**, **old/new**, **new/old**, **new/new** using slash-bounded glob matches and
exclude precedence. A directory need not contain a kustomization to be discovered;
intermediate category directories are included. Supported Go templates are the
path, basename, normalized basename and indexed path-segment forms used here.
Unsupported generators/templates/repository revisions block rather than pass.

Report disappearing Applications and changed identities, owners, projects,
destinations, explicit finalizers, generator paths and preservation policy.
A temporarily missing source path warns when the Application remains discovered:
render failure is different from generator-driven deletion. Source moves warn even
if discovery remains stable: the prerequisite may still
be absent live. Removing preservation blocks. Changes enabling prune or
Force/Replace block; other Application sync policy changes warn.

Render affected Application roots at both revisions with Kustomize/Helm,
including local resource/component dependencies. Compare persistent object
identities, owners, PVC/PV storage classes/bindings/reclaim policy, StatefulSet
claim templates and relevant finalizers. Removal/rename and storage transitions
block. Helm-rendered resources are compared, not inferred from values files.

## Limits and next phase

This V1 does not model operator-created claims, mutable chart downloads,
external/multi-source generators, indirect workload data lineage or every
possible Argo prune interaction. Ownership comparison covers rendered affected
roots; an unchanged owner's resources may require an additional render/live
inspection. PASS cannot prove absence of risk. Keep normal render/schema CI,
backup verification and scoped review.

The reduced monitoring fixtures prove the checker flags the old-generator/new-
tree disappearance even when final identities match. They do not reconstruct
historical cluster timing or prove that a hook would have run before the incident.

For a migration, open a prerequisite PR that broadens paths/preserves resources
without moving them; the user explicitly merges it. Verify the required fields,
Applications/finalizers and preserved resources **live** before preparing the
move PR. Then verify the move before a separate cleanup PR. Neither a static
PASS nor a merged prerequisite proves live reconciliation. On failure, continue
read-only investigation and repair through a new PR; do not delete Applications,
strip finalizers or recreate storage to make a gate pass.
