# kopiur trial: replacing pvc-plumber (complete, now production)

> **Complete.** PR #1489 merged 2026-06-26. kopiur fully replaced the retired
> pvc-plumber + VolSync stack on 2026-06-27 and is the production backup system.
> This page is the trial and decision record. The trial first ran kopiur alongside
> pvc-plumber and converted one canary app (karakeep) onto explicit kopiur CRs.
>
> For the fit verdict, kopiur facts, and config shapes, see
> [`domains/storage/kopiur-evaluation.md`](domains/storage/kopiur-evaluation.md).

## The canary: karakeep

This is the worked example in the DR doc. It has two RWO PVCs: `data-pvc` (SQLite bookmarks + assets) and `meilisearch-pvc` (search index). The app is non-critical and easy to drill.

## What the cutover changed

| Area | old (pvc-plumber) | kopiur |
|---|---|---|
| Per-PVC config | 3 labels + `dataSourceRef → ReplicationDestination` | explicit `SnapshotPolicy` + `SnapshotSchedule` + `Restore`, `dataSourceRef → Restore` |
| Operator | `infrastructure/controllers/pvc-plumber/` (Wave 2) | `infrastructure/backup/kopiur-operator/` Kustomize `helmCharts:` (OCI chart, Wave 2) |
| Repo config | `volsync-kopia-repository` ClusterES | `infrastructure/backup/kopiur/` (ns + ESO + `ClusterRepository`, Wave 3) |
| kopia repo | `s3://volsync-kopia/cluster` | `s3://kopiur/` (dedicated, isolated bucket) |
| Namespace gate | `pvc-plumber.io/managed-namespace` | `allowedNamespaces` on the ClusterRepository |

Deploy is pure GitOps. Merge to `main` and ArgoCD reconciles. Do not `kubectl apply`.
- **Wave 2** `kopiur-operator` renders the OCI chart `oci://ghcr.io/home-operations/charts/kopiur`
  (version pinned in `infrastructure/backup/kopiur-operator/kustomization.yaml`)
  and installs the CRDs, operator, and webhook.
  `ServerSideApply=true` avoids the 256KB last-applied-config limit on CRDs.
- **Wave 3** `kopiur-config` creates the namespace, ESO, and `ClusterRepository`.
- **Wave 6** the my-apps AppSet renders the app with the kopiur CR bundle and the
  repointed PVCs.

Watch:
```
kubectl get applications -n argocd | grep kopiur
kubectl -n kopiur-system get pods,clusterrepository
kubectl -n karakeep get snapshotpolicy,snapshotschedule,snapshot,restore
```

## The restore-before-bind drill

`dataSourceRef` is immutable, so a live PVC still points at its original source.
The populator only runs on **recreate**:

1. Confirm at least one kopiur `Snapshot` for `karakeep/data-pvc` exists in the repo.
2. Scale karakeep web to 0, delete `data-pvc`, and let ArgoCD recreate it.
3. Expect the PVC to sit **Pending** while `Restore/data-pvc-restore` populates it.
   Then it binds **with data**, and karakeep starts on the real SQLite (bookmarks intact).
   Pending until restored is the intended behavior.
4. ArgoCD's `/spec/dataSourceRef` diff is masked by the per-PVC `ServerSideApply=false`
   annotation and the my-apps AppSet `ignoreDifferences`. Together they handle the immutable-field compare.

## Notes carried forward

- **Fresh repo.** kopiur reads a new kopia repo and does not see old VolSync
  snapshots. A repo protects data only from its first kopiur snapshot forward.
- **Per-PVC YAML.** About 30 lines of `SnapshotPolicy`, `Schedule`, and `Restore`
  live in the `my-apps/common/kopiur-backup` Kustomize component to stay DRY.
- **Backend-down safety.** kopiur's repo health-probe and preflight provide it, not the old
  `wait-for-rustfs` MAP.
