# kopiur trial — replacing pvc-plumber (complete, now production)

> **Complete.** PR #1489 merged 2026-06-26; kopiur fully replaced the retired
> pvc-plumber + VolSync stack on 2026-06-27 and is the production backup system.
> Retained as the trial/decision record — it originally stood kopiur up alongside
> pvc-plumber and converted one canary app (**karakeep**) onto explicit kopiur CRs.
>
> Strategic companion (fit verdict, kopiur facts, config shapes):
> [`domains/storage/kopiur-evaluation.md`](domains/storage/kopiur-evaluation.md).

## The canary: karakeep

The DR-doc worked example — two RWO PVCs (`data-pvc` = SQLite bookmarks + assets,
`meilisearch-pvc` = search index). Non-critical, easy to drill.

## What the cutover changed

| Area | old (pvc-plumber) | kopiur |
|---|---|---|
| Per-PVC config | 3 labels + `dataSourceRef → ReplicationDestination` | explicit `SnapshotPolicy` + `SnapshotSchedule` + `Restore`, `dataSourceRef → Restore` |
| Operator | `infrastructure/controllers/pvc-plumber/` (Wave 2) | `infrastructure/controllers/kopiur-operator/` Kustomize `helmCharts:` (OCI chart, Wave 2) |
| Repo config | `volsync-kopia-repository` ClusterES | `infrastructure/controllers/kopiur/` (ns + ESO + `ClusterRepository`, Wave 3) |
| kopia repo | `s3://volsync-kopia/cluster` | `s3://kopiur/` (dedicated, isolated bucket) |
| Namespace gate | `pvc-plumber.io/managed-namespace` | `allowedNamespaces` on the ClusterRepository |

Deploy is pure GitOps (merge to `main`, ArgoCD reconciles — no `kubectl apply`):
- **Wave 2** `kopiur-operator` — renders the OCI chart `oci://ghcr.io/home-operations/charts/kopiur`
  (version pinned in `infrastructure/controllers/kopiur-operator/kustomization.yaml`),
  installs the CRDs + operator + webhook.
  `ServerSideApply=true` avoids the 256KB last-applied-config limit on CRDs.
- **Wave 3** `kopiur-config` — namespace + ESO + `ClusterRepository`.
- **Wave 6** the my-apps AppSet renders the app with the kopiur CR bundle and the
  repointed PVCs.

Watch:
```
kubectl get applications -n argocd | grep kopiur
kubectl -n kopiur-system get pods,clusterrepository
kubectl -n karakeep get snapshotpolicy,snapshotschedule,snapshot,restore
```

## The restore-before-bind drill

`dataSourceRef` is immutable, so a live PVC still points at its original source;
the populator only proves out on **recreate**:

1. Confirm at least one kopiur `Snapshot` for `karakeep/data-pvc` exists in the repo.
2. Scale karakeep web to 0 → delete `data-pvc` → let ArgoCD recreate it.
3. Expect: the PVC sits **Pending** while `Restore/data-pvc-restore` populates it,
   then binds **with data**; karakeep starts on the real SQLite (bookmarks intact).
   That `Pending`-until-restored is the whole point.
4. ArgoCD's `/spec/dataSourceRef` diff is masked by the per-PVC `ServerSideApply=false`
   annotation + the my-apps AppSet `ignoreDifferences` (handles the immutable-field compare).

## Notes carried forward

- **Fresh repo.** kopiur reads a new kopia repo and does not see old VolSync
  snapshots; a repo protects data only from its first kopiur snapshot forward.
- **Per-PVC YAML** (~30 lines of `SnapshotPolicy`+`Schedule`+`Restore`) is wrapped
  in the `my-apps/common/kopiur-backup` Kustomize component to stay DRY.
- **Backend-down safety** is kopiur's repo health-probe / preflight, not the old
  `wait-for-rustfs` MAP.
