# Component-specific knobs (Argo CD, Temporal, Cilium)

## Argo CD prerelease bumps

- There may be no GA yet: check the newest RC/stable on the releases API.
- Diff the vendored CRDs (`infrastructure/controllers/argocd/crds/`) against `manifests/crds/` at the new tag.
- Read the tag's `hack/tool-versions.sh` and move the CI Helm/Kustomize pins in `cluster-ci.yml` and `gitops-risk.yml` (plus `docs/domains/argocd/argocd.md`) to match, because CI must render like the repo-server.
- Keep the hard-refresh safeguards while the server-side-diff issue they cite is still open, and grep the repo for the old tag string so README, bootstrap script and comments move together.

## Argo CD: a synced edit never reaches live

Symptom: the app stays OutOfSync on one resource, the controller logs `serverside-applied` in a selfHeal loop, `operationState` says Succeeded, but the live object's `metadata.generation` and the `argocd-controller` managedFields `time` don't move. Every apply is a no-op.

Known suspects. None is confirmed as the sole cause, so test each before blaming it:
- `ignoreDifferences` paths inside a CRD list (`.spec.rules[].backendRefs[].weight`, `.spec.sources[].readOnly`) plus `RespectIgnoreDifferences=true`. CRD lists have no patch merge key, so Argo can copy the whole live list into the target (argo-cd#25284, #26588, open since at least v3.4). Removing these ignores and spelling out the API defaults in Git is safe, with a CI check that keeps them spelled out. But on its own, with the controller restarted, that did NOT unstick an HTTPRoute, so something else also blocks it.
- The my-apps appset sets `ServerSideDiff=false` (a migration-era stopgap). Client-side diff is why default-field ignores exist at all. Server-side diff applies CRD defaults to both sides. Before re-enabling it, check that live PVC `dataSourceRef` matches Git for every PVC (render each kustomize dir and compare), because a mismatch gives a ComparisonError.
- ApplicationSet template edits (e.g. removing an appset ignore) reach the Applications only after the appset itself syncs. Check `kubectl -n argocd get appset <name> -o jsonpath='{.spec.template.spec.ignoreDifferences}'` before assuming the change is live.

Diagnostics, in this order:
1. Argo's own normalized diff: `GET /api/v1/applications/<app>/managed-resources` on `http://argocd-server.argocd.svc` (needs an Argo token). It shows the target and live states Argo actually compares.
2. API-side check, which needs `patch` on the kind, so it's the user's command unless granted: `kubectl kustomize <dir> | yq 'select(.kind=="<Kind>" and .metadata.name=="<n>")' | kubectl apply --server-side --dry-run=server --field-manager=argocd-controller -f - -o yaml`. If the new fields show up, the API accepts the change and Argo is sending stale content.
3. A full sync (all resources) with Respect Ignore Differences off. It's safe once PVC restore fields match Git. If that applies, the respect-ignore path is to blame.

Rules: Mitch expects "sync all" to always be safe. Never offer a selective one-resource sync, or a rename of the resource, as the fix; at most offer it as a diagnostic. Before you claim when a bug started, search Hindsight for earlier incidents with the same symptom. An unmerged earlier fix PR means the bug was never fixed.

## Temporal namespace retention

- Retention is set only at create time (`seed-namespaces.sh` under `my-apps/development-infra/temporal/`), so editing `--retention` there never reaches existing namespaces. Make the seed loop also run `temporal operator namespace update --retention <dur> -n <ns>` for existing namespaces; the PostSync job reruns when its generated ConfigMap changes.
- Before shortening one, check live retention works (`temporal workflow count -n <ns> -q "CloseTime < '<now minus retention>'"` should be 0, via `kubectl -n temporal exec <admintools pod>`), and grep the app for `list_workflows`/history reads of closed runs.
- "Too many workflows in the UI" is usually retention × runs/day, not a cleanup job to schedule.
- After merge: `kubectl -n temporal logs job/temporal-namespace-seed` shows `setting retention <dur>` per namespace, and `temporal operator namespace describe -n <ns> | grep Retention` shows the new value.

## Cilium agent flags

- Flags with no Helm value go in `extraConfig` in `infrastructure/networking/cilium/values.yaml`; confirm the name in the pinned tag's `pkg/option/config.go`.
- Agents don't restart on config changes (`rollOutCiliumPods` is off; only the operator rolls), so a merge changes nothing until each agent restarts. Say so in the PR.
- Raising `k8s-sync-timeout` past the 3 m default fits under the chart startupProbe's 600 s.
