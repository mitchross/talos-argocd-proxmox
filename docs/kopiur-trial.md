# kopiur trial — replacing pvc-plumber (branch `claude/kopiur-trial`)

> **Status: scaffold, not yet applied.** This branch stands kopiur up *alongside*
> pvc-plumber and converts **one canary app (karakeep)** off pvc-plumber labels and
> onto explicit kopiur CRs. Nothing here deploys until you point an ArgoCD
> Application at this branch (the existing apps sync from `main`). It is fully
> reversible — delete the branch, or revert the karakeep PVCs.

## Why karakeep
It's the DR-doc worked example: two RWO PVCs (`data-pvc` = SQLite bookmarks +
assets, `meilisearch-pvc` = search index), both previously pvc-plumber hourly.
Non-critical, easy to drill.

## What changed

| Area | pvc-plumber (today) | kopiur (this branch) |
|---|---|---|
| Per-PVC config | 3 labels + `dataSourceRef → ReplicationDestination` | explicit `SnapshotPolicy` + `SnapshotSchedule` + `Restore`, `dataSourceRef → Restore` |
| Operator | `infrastructure/controllers/pvc-plumber/` (Wave 2) | `core-dependencies/kopiur-operator-app.yaml` Helm (Wave 2) |
| Repo config | `volsync-kopia-repository` ClusterES | `infrastructure/controllers/kopiur/` (ns + ESO + `ClusterRepository`, Wave 3) |
| kopia repo | `s3://volsync-kopia/cluster` | `s3://volsync-kopia/kopiur-trial/` (**fresh, isolated**) |
| Namespace gate | `pvc-plumber.io/managed-namespace` | removed (kopiur uses `allowedNamespaces` on the ClusterRepository) |

Files added: `infrastructure/controllers/kopiur/*`, `core-dependencies/kopiur-{operator,config}-app.yaml`,
`my-apps/media/karakeep/kopiur/{data-pvc,meilisearch-pvc}.yaml`.
Files edited: the two karakeep PVCs (de-fused, `dataSourceRef` repointed), namespace, kustomization.

## ⚠️ VERIFY before you apply (kopiur is pre-1.0 / alpha — CRD fields churn)
1. **Chart tag** — `kopiur-operator-app.yaml` pins `targetRevision: "0.4.13"`. Confirm the tag format on the releases page (`0.4.13` vs `v0.4.13`).
2. **CRD field names** — after the operator installs, run:
   `kubectl explain clusterrepository.spec.backend.s3` · `snapshotpolicy.spec` · `restore.spec`.
   I assembled these from the upstream `deploy/examples` on `main`; reconcile any drift.
3. **RustFS HTTP/TLS** — `clusterrepository.yaml` sets `backend.s3.insecure: true` as a guess for "no TLS". The real field may be `disableTls` / an `http://` endpoint. RustFS here is plain HTTP on `:30292`.
4. **Secret keys** — confirm the S3 backend reads `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` (the ESO writes those). Adjust `externalsecret.yaml` if kopiur wants different keys.
5. **CRDs via ArgoCD** — the chart ships CRDs as templates; SSA + large CRDs can be fiddly. If it fights you, `helm install kopiur deploy/helm/kopiur -n kopiur-system --create-namespace --set installScope=cluster` once by hand (kopiur's own quickstart) and keep only `infrastructure/controllers/kopiur/` in GitOps.

## How to run the trial
1. Add a throwaway ArgoCD Application pointing at this branch's `core-dependencies/` (or apply the two app manifests by hand). The operator (Wave 2) installs CRDs + webhook; config (Wave 3) creates the ClusterRepository.
2. Watch kopiur create the repo and take the first karakeep snapshots:
   `kubectl -n karakeep get snapshotpolicy,snapshotschedule,snapshot,restore`
   `kubectl -n kopiur-system get clusterrepository`
3. The first `Snapshot` captures karakeep's **current** data into the fresh repo (the live PVCs are already Bound; `dataSourceRef` is a no-op until recreate).

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
