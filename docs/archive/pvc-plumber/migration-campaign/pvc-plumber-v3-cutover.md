> [!WARNING]
> Historical document.
> This file is preserved for context only and is not the current runbook.
> Start with: [docs index](../../../index.md) and [pvc-plumber start here](../../../pvc-plumber-start-here.md).

# pvc-plumber v3.0.0 cutover runbook

The 2026-05-08 incident post-mortem is in
[`docs/research/volsync-fork-vs-upstream-2026-05-08.md`](../../../research/volsync-fork-vs-upstream-2026-05-08.md).
This doc is the operational checklist for migrating the cluster from v2.1.1
(NFS-backed kopia + JobMutator-induced drift loop) to v3.0.0 (S3-backed
kopia + JobMutator removed).

## Pre-flight (before merging the v3.0.0 PR)

- [ ] **RustFS bucket `volsync-kopia` exists** with versioning OFF /
      object lock OFF. Verified via:
      ```
      kubectl run rustfs-verify --rm --restart=Never \
        --image=amazon/aws-cli:latest -n cloudnative-pg \
        --overrides='{"spec":{"containers":[{"name":"v","image":"amazon/aws-cli:latest","command":["sh","-c"],"args":["aws --endpoint-url http://192.168.10.133:30293 s3api head-bucket --bucket volsync-kopia"],"envFrom":[{"secretRef":{"name":"cnpg-s3-credentials"}}]}]}}'
      ```
- [ ] **1Password item `rustfs`** has the three required properties:
      `kopia_password`, `pvc-plumber-access-key`, `pvc-plumber-secret-key`.
      Same item, no schema change — just confirming it's there.
- [ ] **JobMutator emergency-disabled** in the live cluster (was
      patched in via `objectSelector: { matchLabels: { pvc-plumber.io/emergency-disabled: "2026-05-08" }}`
      during the outage). If you accidentally re-enabled it, disable
      again before the cutover.
- [ ] **All running VolSync mover Jobs are gone** (`kubectl get jobs -A
      -l app.kubernetes.io/created-by=volsync` returns empty). The
      JobMutator deadlock created Job thrash; let any in-flight cycles
      drain to Failed before we cut.

## The cutover (in one PR or three sequenced PRs — your call)

### One-PR variant (faster, riskier rollback)

1. Bump `infrastructure/controllers/pvc-plumber/deployment.yaml` image to
   `:3.0.0`. Drop `NFS_SERVER`, `NFS_PATH`, `KOPIA_REPOSITORY_PATH`,
   `BACKEND_TYPE=kopia-fs`. Add `BACKEND_TYPE=kopia-s3`,
   `KOPIA_S3_ENDPOINT=http://192.168.10.133:30293`,
   `KOPIA_S3_BUCKET=volsync-kopia`, `KOPIA_S3_DISABLE_TLS=true`.
   Drop the `repository` NFS volume + `/repository` mount. Add
   AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY env from
   `pvc-plumber-kopia` Secret (already mounted, just two new keys).
2. Extend `infrastructure/controllers/pvc-plumber/externalsecret.yaml` to
   pull `pvc-plumber-access-key` → AWS_ACCESS_KEY_ID and
   `pvc-plumber-secret-key` → AWS_SECRET_ACCESS_KEY in addition to the
   kopia password.
3. Delete the `mutate-job.pvc-plumber.io` block from
   `infrastructure/controllers/pvc-plumber/webhooks.yaml`. The emergency
   `objectSelector` is no longer needed.
4. Commit and push. ArgoCD syncs in about a minute.

### Three-PR variant (slower, safer rollback per stage)

1. **PR-1**: External-secret schema only. Extend `pvc-plumber-kopia` ES
   with the AWS keys. v2.1.1 ignores them harmlessly.
2. **PR-2**: Operator image bump to `:3.0.0` + deployment env-var
   migration + delete JobMutator webhook. The reconciler's one-time
   filesystem-→-S3 ES recycle fires here.
3. **PR-3**: (Cleanup, optional) Drop the disabled `mutate-job` webhook
   block from `webhooks.yaml` once you've confirmed `kubectl get
   mutatingwebhookconfiguration pvc-plumber -o yaml` doesn't reference
   it any more.

## Immediate post-cutover (within 5 minutes of ArgoCD Synced/Healthy)

1. **Run the verification script:**
   ```
   ./scripts/verify-pvc-plumber-v3-cutover.sh
   ```
   Should report all 9 checks green. If any fail, **stop**, investigate,
   and roll back via `git revert` of the cutover PR rather than trying to
   live-patch.

2. **Trigger fresh baselines on every RS** so the first S3 snapshot
   lands without waiting for the schedule:
   ```
   ./scripts/trigger-fresh-volsync-baselines.sh
   ```
   Each PVC uploads its current contents to S3 once. Watch:
   ```
   watch 'kubectl get rs -A'
   ```
   Largest first runs:
     - immich/library         (300Gi)
     - project-nomad/nomad-storage   (120Gi)
     - posthog/clickhouse-data-clickhouse-0 (100Gi)

   After the triggered runs finish, clear the manual trigger field so
   normal cron schedules resume:
   ```
   ./scripts/trigger-fresh-volsync-baselines.sh --clear-manual
   ```
   Verify scheduled sources have `nextSyncTime` again:
   ```
   kubectl get replicationsource -A -o json | \
     jq -r '.items[] | [.metadata.namespace,.metadata.name,
       (.spec.trigger.manual // ""),(.status.nextSyncTime // ""),
       (.status.conditions[-1].reason // "")] | @tsv'
   ```
   No row should retain a non-empty `trigger.manual` after cleanup.

3. **Spot-check the RustFS bucket** is filling up:
   ```
   aws --endpoint-url http://192.168.10.133:30293 \
       s3 ls s3://volsync-kopia/ --recursive --human-readable --summarize \
       | tail -5
   ```
   You should see kopia's blob layout (`_log/`, `_index/`, `pXX/`)
   appearing within a minute of the first triggered RS.

## Karakeep ultimate test (the v2 promise we never got to prove)

Once at least one RS for `karakeep/data-pvc-backup` has reported
`lastSyncTime` newer than the cutover timestamp:

1. **Pre-flight inventory** — record karakeep's current state:
   ```
   kubectl get pvc -n karakeep data-pvc -o yaml > /tmp/karakeep-pvc-pre.yaml
   kubectl exec -n karakeep deploy/karakeep-web -- ls -la /data | head -20
   # plus: open https://karakeep.vanillax.me, take a screenshot of one
   # known-good bookmark or note for later comparison
   ```
2. **Scale karakeep down** so the PVC is detached:
   ```
   kubectl scale -n karakeep deploy/karakeep-web --replicas=0
   kubectl scale -n karakeep deploy/karakeep-chrome --replicas=0
   # leave karakeep-meilisearch alone (different PVC)
   ```
3. **Delete the PVC**:
   ```
   kubectl delete pvc -n karakeep data-pvc
   ```
4. **Re-apply the PVC manifest** via ArgoCD sync (or manually
   `kubectl apply` the PVC YAML from the GitOps repo).
5. **Watch the v3 mutating webhook inject `dataSourceRef`**:
   ```
   kubectl get pvc -n karakeep data-pvc -o yaml | grep -A3 dataSourceRef
   ```
   Should show a `VolumePopulator` reference pointing at a generated
   `ReplicationDestination`.
6. **Wait for VolSync's populator** to finish. Watch:
   ```
   kubectl get rd -n karakeep -w
   ```
7. **Scale karakeep back up**:
   ```
   kubectl scale -n karakeep deploy/karakeep-web --replicas=1
   kubectl scale -n karakeep deploy/karakeep-chrome --replicas=1
   ```
8. **Verify data**: open `https://karakeep.vanillax.me` and confirm
   the bookmark/note from step 1 is back.

If the data is intact: the v3 restore-on-create killer feature is
proven. Document the test in
[`docs/volsync-storage-recovery.md`](../../../volsync-storage-recovery.md) and
celebrate.

## Rollback

If the cutover goes sideways, the rollback path is:

1. `git revert` the cutover commit + push.
2. ArgoCD syncs back to v2.1.1. Operator restarts on the old image.
3. **The legacy JobMutator webhook entry stays disabled** (the
   emergency-disabled objectSelector is still on it from 2026-05-08).
   You're back to "operator runs without JobMutator" — degraded but
   not in the drift loop. Backups continue to fail at the kopia-can't-
   reach-/repository step until the operator either re-enables
   JobMutator (don't) or you re-roll v3.0.0.
4. RustFS bucket `volsync-kopia` stays untouched. Any data already
   uploaded sits there. Next v3 attempt picks up where it left off.

The legacy NFS share at `192.168.10.133:/mnt/BigTank/k8s/volsync-kopia-nfs`
is **not deleted** by the v3 cutover. Keep it online for ~30 days as a
safety net — it still has the (stale) snapshots from before the outage.
After the v3 deployment has been healthy for a month, delete the share
manually on TrueNAS.

## What stays after v3.0.0 ships

- Two pvc-plumber webhooks (mutate-pvc, validate-pvc + validate-pvc-exempt)
- Operator's `/exists` HTTP API on :8080 (unchanged contract)
- Per-PVC `volsync-<pvc>` ExternalSecret (new schema; same name)
- VolSync mover Jobs (unchanged image, unchanged spec — kopia just talks
  to S3 now via env vars)

## What's gone after v3.0.0 ships

- JobMutator (the source of the outage)
- NFS dependency for backup data path
- The `repository` NFS volume + `/repository` mount on operator pods
- `KOPIA_REPOSITORY=filesystem:///repository` everywhere
