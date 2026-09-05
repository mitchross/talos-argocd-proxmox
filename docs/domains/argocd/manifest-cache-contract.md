# Manifest cache dependency contract

Argo resolves relative `manifest-generate-paths` entries against an Application's
`source.path`. Repeating the repository path without a leading slash therefore
creates a doubled, nonmatching path. An unrelated commit may reuse the cache;
a change to an input must not.

The root registry's Kustomize patches own the effective hints for its children:

- standalone Applications and ordinary ApplicationSets: `.`;
- the `my-apps` ApplicationSet: `.;/my-apps/common`;
- the separately seeded root Application: `.` in `root.yaml`.

The raw entrypoint files can still contain historical hints; the rendered registry
is authoritative. This central patch keeps all entrypoints consistent without
renaming Applications, changing their sources, changing sync waves, or changing
prune behavior. New shared directories must be added to the consuming template's
hint and tests before use. This is a cache-dependency declaration, not an
application discovery filter.

## Verification

```sh
python -m unittest discover -s scripts/tests -p test_argocd_cache_paths.py -v
kustomize build infrastructure/controllers/argocd/apps > /tmp/argocd-entrypoints.yaml
python scripts/validate-argocd-cache-paths.py /tmp/argocd-entrypoints.yaml infrastructure/controllers/argocd/root.yaml
```

The manually seeded root is not self-managed. After merging, reapply the root
seed with the normal bootstrap ownership convention (no workload edits):

```sh
kubectl apply -f infrastructure/controllers/argocd/root.yaml
kubectl -n argocd annotate application root argocd.argoproj.io/refresh=hard --overwrite
```

Verify the rendered child annotations and live Application annotations agree.
Use a disposable application's ConfigMap to verify an app-local edit propagates.
Then verify a shared Component edit changes every affected desired render. An
unrelated application's edit must not count as a dependency. Compare actual
manifest content, not only `status.sync.revision`.

This fixes a concrete dependency declaration error; it does not prove the cause
of every historical stale-cache incident. Existing hard-refresh/cache-expiry
settings are unchanged. Rollback is reverting this PR; do not delete Applications.

Upstream semantics: https://argo-cd.readthedocs.io/en/stable/operator-manual/high_availability/#manifest-paths-annotation
