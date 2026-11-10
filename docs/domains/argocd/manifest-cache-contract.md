# Manifest cache contract

Argo CD caches the manifests it renders for each Application.
The `argocd.argoproj.io/manifest-generate-paths` annotation tells it which directories that render depends on.
This page states the values this repo uses and how to check them.
Read it before you add a shared directory that several Applications render from.

The contract has two sides. A commit that touches none of an Application's inputs may reuse the cache.
A commit that changes an input must not.

## Why the value is relative

Argo CD resolves a relative `manifest-generate-paths` entry against the Application's `source.path`.
An entry that repeats the repository path with no leading slash therefore becomes a doubled path that matches nothing.
Use `.` for the Application's own directory. Use a leading slash for a directory elsewhere in the Git repo.

## Where the values are set

The Kustomize patches in `infrastructure/controllers/argocd/apps/kustomization.yaml` set the effective hint for every entrypoint.

| Entrypoint | Hint |
|---|---|
| Standalone Applications and ordinary ApplicationSets | `.` |
| The `my-apps` ApplicationSet | `.;/my-apps/common` |
| The separately seeded root Application, in `root.yaml` | `.` |

The raw entrypoint files still contain other hint values.
The patches overwrite them at render time, so the rendered registry is authoritative.

One central patch keeps all entrypoints consistent.
It does not rename Applications, change their sources, change sync waves, or change prune behavior.

This hint declares a cache dependency. It is not an application discovery filter.

## Add a shared directory

Add the shared directory to the hint of the template that consumes it, and to the tests, before any app uses it.
The `my-apps` hint includes `/my-apps/common` for this reason. Its apps render Components from that directory.

## Verify

```sh
python -m unittest discover -s scripts/tests -p test_argocd_cache_paths.py -v
kustomize build infrastructure/controllers/argocd/apps > /tmp/argocd-entrypoints.yaml
python scripts/validate-argocd-cache-paths.py /tmp/argocd-entrypoints.yaml infrastructure/controllers/argocd/root.yaml
```

## Apply a change to the root seed

Argo CD does not manage the manually seeded root Application.
After a change to `root.yaml` merges, apply the root seed again with the normal bootstrap ownership convention.
Make no workload edits in the same step.

```sh
kubectl apply -f infrastructure/controllers/argocd/root.yaml
kubectl -n argocd annotate application root argocd.argoproj.io/refresh=hard --overwrite
```

Then check the live result:

1. Confirm that the rendered child annotations and the live Application annotations agree.
2. Edit the ConfigMap of a disposable app. Confirm that the edit reaches the cluster.
3. Edit a shared Component. Confirm that the desired render of every affected Application changes.
4. Confirm that an edit to an unrelated app does not count as a dependency.

Compare the actual manifest content, not only `status.sync.revision`.

## Limits and rollback

This contract corrects one error, a wrong dependency declaration.
It does not explain every stale-cache case.
The hard-refresh and cache-expiry settings are separate, and this contract does not change them.
For a stale render with correct hints, use the [stale render runbook](argocd.md#app-is-synced-at-head-but-the-cluster-runs-an-older-commit).

To roll back, revert the commit that changed the hints. Do not delete Applications.

Upstream semantics: <https://argo-cd.readthedocs.io/en/stable/operator-manual/high_availability/#manifest-paths-annotation>
