# kopiur trial — replacing pvc-plumber (branch `claude/kopiur-trial`)

> **Status: open as PR #1489** (branch `claude/kopiur-trial`). Stands kopiur up
> *alongside* pvc-plumber and converts **one canary app (karakeep)** off
> pvc-plumber labels onto explicit kopiur CRs. Nothing deploys until the PR is
> merged to `main` (Argo GitOps — no manual apply). Fully reversible: revert the PR.
>
> **Why this trial exists (the decision + analysis):** see
> [`domains/storage/kopiur-evaluation.md`](domains/storage/kopiur-evaluation.md) —
> fit verdict, community landscape, maintainer conversation, kopiur code map, verified facts.

## Why karakeep
It's the DR-doc worked example: two RWO PVCs (`data-pvc` = SQLite bookmarks +
assets, `meilisearch-pvc` = search index), both previously pvc-plumber hourly.
Non-critical, easy to drill.

## What changed

| Area | pvc-plumber (today) | kopiur (this branch) |
|---|---|---|
| Per-PVC config | 3 labels + `dataSourceRef → ReplicationDestination` | explicit `SnapshotPolicy` + `SnapshotSchedule` + `Restore`, `dataSourceRef → Restore` |
| Operator | `infrastructure/controllers/pvc-plumber/` (Wave 2) | `kopiur-operator-app.yaml` → `infrastructure/controllers/kopiur-operator/` Kustomize `helmCharts:` (OCI chart, Wave 2) |
| Repo config | `volsync-kopia-repository` ClusterES | `infrastructure/controllers/kopiur/` (ns + ESO + `ClusterRepository`, Wave 3) |
| kopia repo | `s3://volsync-kopia/cluster` | `s3://kopiur/` (**dedicated bucket, isolated**) |
| Namespace gate | `pvc-plumber.io/managed-namespace` | removed (kopiur uses `allowedNamespaces` on the ClusterRepository) |

Files added: `infrastructure/controllers/kopiur/*`, `core-dependencies/kopiur-{operator,config}-app.yaml`,
`my-apps/media/karakeep/kopiur/{data-pvc,meilisearch-pvc}.yaml`.
Files edited: the two karakeep PVCs (de-fused, `dataSourceRef` repointed), namespace, kustomization.

## ⚠️ VERIFY before you apply (kopiur is pre-1.0 / alpha — CRD fields churn)
1. **Chart version** — ✅ the operator renders the OCI chart `oci://ghcr.io/home-operations/charts/kopiur` pinned to `version: 0.4.13` in `infrastructure/controllers/kopiur-operator/kustomization.yaml` (chart version == app version; no `v` prefix). The Application tracks our repo `main`, not the upstream git tag.
2. **CRD field names** — after the operator installs, run:
   `kubectl explain clusterrepository.spec.backend.s3` · `snapshotpolicy.spec` · `restore.spec`.
   Assembled from upstream `deploy/examples` on `main`; reconcile any drift.
3. **RustFS HTTP/TLS** — ✅ RESOLVED: `backend.s3.tls.disableTls: true` + bare `host:port` endpoint (vs `deploy/examples/backends/s3-minio-http.yaml`).
4. **Secret keys** — ✅ RESOLVED: backend reads `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `KOPIA_PASSWORD` — exactly what the ESO writes.
5. **CRDs via ArgoCD** — the chart ships CRDs as templates (not a `crds/` dir), so ArgoCD applies them on sync. `ServerSideApply=true` (set on the operator app) renders them without the 256KB last-applied-config limit. No cert-manager hook (webhook tls.mode=self), so no API-server-wedge risk.

## How to run the trial (pure GitOps — merge, don't apply)
The operator + config Applications are wired into the root app-of-apps
kustomization (`infrastructure/controllers/argocd/apps/kustomization.yaml`) and
track `main`. **There is no `kubectl apply` step** — open a PR, merge to `main`,
and Argo deploys it (this is a real deploy to the live cluster):
- **Wave 2** `kopiur-operator` — renders the chart from the upstream git tag
  `0.4.13` → installs the 7 CRDs + operator + webhook.
- **Wave 3** `kopiur-config` — namespace + ESO + ClusterRepository.
- **Wave 6** the my-apps AppSet re-renders karakeep with the kopiur CR bundle and
  the repointed PVCs.

Watch:
```
kubectl get applications -n argocd | grep kopiur
kubectl -n kopiur-system get pods,clusterrepository
kubectl -n karakeep get snapshotpolicy,snapshotschedule,snapshot,restore
```
The first `Snapshot` captures karakeep's current data into the fresh repo (live
PVCs are Bound; `dataSourceRef` is a no-op until recreate — the drill below).

> Merging deploys to the live cluster. pvc-plumber + VolSync stay untouched for
> every other app; only karakeep moves. karakeep's VolSync backups stop on merge
> (labels gone) and kopiur's begin once the repo is healthy — the manual karakeep
> backup covers the gap. Roll back by reverting the PR.

## Cutover & the real test (restore-before-bind drill)
`dataSourceRef` is **immutable**, so the live PVCs still point at the VolSync RD.
The kopiur populator only proves out on **recreate**:
1. Confirm at least one kopiur `Snapshot` for `karakeep/data-pvc` exists in the repo.
2. Scale karakeep web to 0 → delete `data-pvc` → let ArgoCD recreate it from this branch.
3. Expect: PVC sits **Pending** while `Restore/data-pvc-restore` populates it, then binds **with data**; karakeep starts on the real `gitea`-style SQLite (bookmarks intact). That `Pending`-until-restored is the whole point.
4. ArgoCD diff on `/spec/dataSourceRef`: the per-PVC `ServerSideApply=false` annotation + the my-apps AppSet `ignoreDifferences` mask already handle the immutable-field compare (same mechanism pvc-plumber relied on).

## Friction surfaced so far (the honest "how far I got")
- **No shared repo with VolSync.** kopiur reads a *fresh* kopia repo, so it does **not** see your existing VolSync snapshots. Trial only protects data from its first kopiur snapshot forward. (A real migration would seed/copy, or run both until kopiur has history.)
- **Per-PVC YAML is back.** Each volume is now ~30 lines of `SnapshotPolicy`+`Schedule`+`Restore` vs 3 labels — exactly the DX gap from the Discord thread. If kept, wrap it in a Kustomize component to stay DRY.
- **Backend-down safety differs.** The `wait-for-rustfs` MAP gates *VolSync* mover Jobs; it does nothing for kopiur. Verify kopiur's repo health-probe / preflight actually blocks a snapshot Job when RustFS is unreachable, or you lose the "never snapshot over a black-holed backend" guarantee.
- **Webhook `failurePolicy: Ignore`** is set for the trial so a kopiur outage can't gate `Restore` CR creation during a rebuild. Re-evaluate before trusting DR.

## Rollback
Nothing on `main` changed. To abandon: delete branch `claude/kopiur-trial`.
To revert a partial live trial: restore pvc-plumber labels on the two karakeep PVCs,
repoint `dataSourceRef` to `*-dst`, re-add `pvc-plumber.io/managed-namespace`, and
delete the kopiur Applications + `infrastructure/controllers/kopiur/`.
