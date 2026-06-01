Add automatic backup to PVC(s) in `$ARGUMENTS`.

> **STATUS** (2026-05-22): pvc-plumber v4 re-adoption is in planning — see
> [`docs/pvc-plumber-v4-prd.md`](../../docs/pvc-plumber-v4-prd.md). Until that
> rollout begins, the **inline `ReplicationSource` + `ReplicationDestination`
> per PVC** pattern below is the live truth. It is GitOps-native (no chart, no
> operator, no Helm templating). When the v4 operator goes live in audit/
> permissive mode, this command will be updated to emit the namespaced
> `pvc-plumber.io/*` labels in addition to the inline resources, then later
> to drop the inline RS/RD once the operator owns them.

## Pattern (post-pvc-plumber decommission, 2026-05-21 → v4 rollout)

Backups are declared **per PVC** as inlined VolSync resources:

1. The PVC carries a static `dataSourceRef → ReplicationDestination/<pvc>-dst`.
2. A `ReplicationSource` schedules the backup against the shared kopia repo.
3. A `ReplicationDestination` defines the restore target the populator uses.

> **DR-completeness — the `dataSourceRef` is mandatory.** A managed PVC with **no**
> `dataSourceRef` recreates **EMPTY** (the populator never engages) — it is backed up
> but cannot be restored on recreate. Always include `dataSourceRef → <pvc>-dst`.
> If you ever need to *add* a dsr to an already-Bound no-dsr PVC, follow the
> **"Restore drill runbook"** in [`docs/volsync-storage-recovery.md`](../../docs/volsync-storage-recovery.md):
> commit the dsr, then **hard-refresh and wait until `application.status.sync.revision == dsr commit`
> before deleting the PVC** (else Argo's stale render recreates it empty — be ready for a
> double-recreate), and **manually restore RS/RD triggers** afterward (pvc-plumber does not
> revert manual trigger drift).

The shared kopia repo Secret `volsync-kopia-repository` is fanned out to every
namespace labeled `volsync.backube/privileged-movers: "true"` by
`ClusterExternalSecret/volsync-kopia-repository` at
`infrastructure/storage/volsync-backup-cluster/`. A `wait-for-rustfs` init
container is auto-injected on every mover Job by
`MutatingAdmissionPolicy/volsync-mover-backend-availability` (Job-level
fail-closed gate; cannot brick cluster-wide PVC creation).

There is **no Helm chart**, **no `helmCharts:` entry**, and **no `helmGlobals.chartHome`**.
The YAML below is the truth.

## Steps

1. **Identify the PVC(s)** in the specified app directory needing backup. For
   each: capture `name`, `namespace`, `storage`, `storageClassName`,
   `accessModes`, and the **mover UID/GID** (must match the workload's
   filesystem ownership — VolSync runs as this user when reading/writing
   the volume).

2. **Confirm the namespace has the privileged-movers label.** If
   `namespace.yaml` does not already carry
   `volsync.backube/privileged-movers: "true"`, add it. Without this label,
   `volsync-kopia-repository` Secret will not materialize in the namespace
   and every mover Job will fail at credential load.

3. **Edit each PVC manifest.** Convert the file into a multi-document YAML:
   PVC first, then `ReplicationSource`, then `ReplicationDestination`. Use
   the conventions from `my-apps/ai/open-webui/pvc.yaml`:

   - PVC labels: `restore-policy: "strict"` (source-of-truth data) or
     `"best-effort"` (disposable/reproducible).
   - PVC annotation: `argocd.argoproj.io/compare-options: ServerSideDiff=false`
     — required so Argo's server-side diff does not attempt to mutate the
     immutable `dataSourceRef` on a Bound PVC.
   - PVC `dataSourceRef` → `ReplicationDestination/<pvc-name>-dst`.
   - ReplicationSource: `metadata.name = <pvc-name>` (bare), `kopia.username = <pvc-name>`,
     `kopia.hostname = <namespace>`, schedule with a unique cron minute (use
     `python -c "import zlib; print(zlib.adler32(b'<ns>/<pvc>') % 60)"` or
     pick by hand to avoid thundering-herd 02:00 clusters).
   - ReplicationDestination: `metadata.name = <pvc-name>-dst`,
     `trigger.manual: restore-once` (static — only fires when value changes),
     `kopia.sourceIdentity` mirrors the RS, `capacity` **must equal**
     `pvc.spec.resources.requests.storage`.

   Canonical template — copy and replace `<pvc-name>`, `<namespace>`,
   `<storage>`, `<schedule>`, `<uid>/<gid>`:

   ```yaml
   ---
   apiVersion: v1
   kind: PersistentVolumeClaim
   metadata:
     name: <pvc-name>
     namespace: <namespace>
     annotations:
       argocd.argoproj.io/compare-options: ServerSideDiff=false
     labels:
       app.kubernetes.io/name: <namespace>
       restore-policy: "strict"
   spec:
     accessModes:
       - ReadWriteOnce
     resources:
       requests:
         storage: <storage>
     storageClassName: longhorn
     dataSourceRef:
       apiGroup: volsync.backube
       kind: ReplicationDestination
       name: <pvc-name>-dst
   ---
   apiVersion: volsync.backube/v1alpha1
   kind: ReplicationSource
   metadata:
     name: <pvc-name>
     namespace: <namespace>
     labels:
       app.kubernetes.io/managed-by: argocd
       volsync.backup/pvc: <pvc-name>
   spec:
     sourcePVC: <pvc-name>
     trigger:
       schedule: "<minute> 2 * * *"   # daily; or "<minute> * * * *" for hourly
     kopia:
       repository: volsync-kopia-repository
       username: <pvc-name>
       hostname: <namespace>
       compression: zstd-fastest
       parallelism: 2
       retain:
         hourly: 24
         daily: 7
         weekly: 4
         monthly: 2
       copyMethod: Snapshot
       storageClassName: longhorn
       volumeSnapshotClassName: longhorn-snapclass
       cacheCapacity: 2Gi
       moverSecurityContext:
         runAsUser: <uid>
         runAsGroup: <gid>
         fsGroup: <gid>
   ---
   apiVersion: volsync.backube/v1alpha1
   kind: ReplicationDestination
   metadata:
     name: <pvc-name>-dst
     namespace: <namespace>
     labels:
       app.kubernetes.io/managed-by: argocd
       volsync.backup/pvc: <pvc-name>
   spec:
     trigger:
       manual: restore-once
     kopia:
       repository: volsync-kopia-repository
       username: <pvc-name>
       hostname: <namespace>
       sourceIdentity:
         sourceName: <pvc-name>
         sourceNamespace: <namespace>
         sourcePVCName: <pvc-name>
       copyMethod: Snapshot
       storageClassName: longhorn
       volumeSnapshotClassName: longhorn-snapclass
       cacheCapacity: 2Gi
       accessModes:
         - ReadWriteOnce
       capacity: <storage>
       moverSecurityContext:
         runAsUser: <uid>
         runAsGroup: <gid>
         fsGroup: <gid>
   ```

4. **Ensure the file is listed in `kustomization.yaml`.** Inline RS/RD live
   in the same `pvc.yaml` document, so no new files are added — but verify
   `pvc.yaml` is under `resources:` (it usually already is).

## Helm-rendered PVCs (gitea, n8n, posthog data layer, temporal)

When the PVC is owned by an upstream Helm chart, the chart-rendered PVC
manifest cannot be edited directly. Instead:

- Add a Kustomize `patches:` entry against `kind: PersistentVolumeClaim` to
  inject the `ServerSideDiff=false` annotation and `dataSourceRef`. See
  `my-apps/development/gitea/kustomization.yaml`.
- Provide the sibling RS/RD as `extraDeploy:` entries in the chart's values
  file. See `my-apps/development/gitea/values.yaml` and
  `my-apps/development/posthog/data-layer/`.

## Schedule Guide

- **Hourly** (`<minute> * * * *`) — frequently-changing data (databases,
  active state). Cron minute should hash the PVC identity:
  `python -c "import zlib; print(zlib.adler32(b'<ns>/<pvc>') % 60)"`.
- **Daily** (`<minute> 2 * * *`) — most apps. Same hash for the minute;
  hour pinned to 02:00 UTC.

Pick the minute manually and check for collisions in nearby apps to avoid
RustFS contention spikes.

## Restore-policy Guide

- `restore-policy: "strict"` — source-of-truth data. Future pvc-plumber
  strict mode will fail-closed on unknown backup state for these PVCs.
- `restore-policy: "best-effort"` — disposable / reproducible (NAS-backed
  caches, model downloads). Future pvc-plumber permissive mode default.

## What NOT to back up with this system

- **CNPG database PVCs** — they use Barman to S3 in a separate code path.
  See `infrastructure/database/cloudnative-pg/`.
- System-namespace PVCs (kube-system, volsync-system, argocd, longhorn-system,
  cert-manager, external-secrets, 1passwordconnect, snapshot-controller).
- Temporary / cache data — use the `backup-exempt: "true"` label **plus** the
  fully-qualified `storage.vanillax.dev/backup-exempt-reason: "<reason>"`
  annotation. The bare `backup-exempt-reason` key is silently ignored and the
  PVC is denied on CREATE — invisible until recreate/DR. The CI job
  `backup-exempt-contract` enforces FQ key usage.
- Non-Longhorn PVCs (kopia mover needs CSI volume snapshots; NFS-backed PVCs
  cannot be snapshotted).

## Verification

```bash
# 1. Confirm the three resources exist after ArgoCD sync
kubectl get pvc,replicationsource.volsync.backube,replicationdestination.volsync.backube -n <ns>

# 2. Confirm ClusterExternalSecret materialized the kopia repo Secret in-namespace
kubectl get secret volsync-kopia-repository -n <ns>

# 3. Trigger a manual backup
kubectl patch replicationsource.volsync.backube <pvc-name> -n <ns> --type=merge \
  -p '{"spec":{"trigger":{"manual":"verify-'$(date +%s)'"}}}'

# 4. Watch the mover pod come up; confirm wait-for-rustfs init container ran
kubectl get pods -n <ns> -l app.kubernetes.io/created-by=volsync
kubectl logs -n <ns> <mover-pod> -c wait-for-rustfs

# 5. Confirm snapshot landed in the kopia repo
kubectl exec -n volsync-system deploy/kopia-ui -- \
  kopia snapshot list <pvc-name>@<namespace>
```

## Removing Backups

1. Delete the `ReplicationSource` and `ReplicationDestination` documents
   from the app's `pvc.yaml`.
2. Remove the `dataSourceRef` block from the PVC spec.
3. Optionally remove the `restore-policy` label and `ServerSideDiff=false`
   annotation.
4. Push. ArgoCD prune will tear down the RS/RD; the PVC stays bound.

If the PVC should keep historical backups but stop being further backed up,
keep the `ReplicationDestination` (for future restore on recreate) and
delete only the `ReplicationSource`.

## Reference

- **Canonical inline pattern**: `my-apps/ai/open-webui/pvc.yaml`
- **Application guidelines** (full template + multi-PVC examples): `my-apps/CLAUDE.md`
- **Multi-PVC reference**: `my-apps/home/paperless-ngx/`, `my-apps/development/posthog/data-layer/`
- **Helm-rendered PVC reference**: `my-apps/development/gitea/`
- **Cluster-wide ClusterES + MAP safety interlock**: `infrastructure/storage/volsync-backup-cluster/`
- **VolSync operator**: `infrastructure/storage/volsync/`
- **RustFS lifecycle policy**: `infrastructure/storage/rustfs-lifecycle/`
- **Credential conventions**: `docs/rustfs-credential-runbook.md`
- **Migration history (decommissioned chart)**: `docs/research/pvc-backup-simplification/`
- **pvc-plumber v4 PRD (planned re-adoption)**: `docs/pvc-plumber-v4-prd.md`
