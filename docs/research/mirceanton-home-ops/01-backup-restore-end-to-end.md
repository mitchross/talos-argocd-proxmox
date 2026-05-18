# mirceanton/home-ops — Backup & Restore, End to End

Author: research (study mode)
Date: 2026-05-18
Source: `mirceanton/home-ops` @ main + "How I Back Up My Kubernetes Cluster"

> External reference. Not this repo's design. No comparison drawn here.

---

## 0. One-paragraph mental model

Flux renders a reusable Kustomize **Component** that, for each app, emits
four resources: an ExternalSecret (Restic repo creds from 1Password), a
**ReplicationSource** (scheduled Restic backup of the app's PVC to S3), a
**ReplicationDestination** (manual-triggered restore), and the **PVC
itself wired with `dataSourceRef`** so the destination repopulates it on
creation. A MutatingAdmissionPolicy injects a random sleep into every
backup mover Job to de-synchronize the herd. A Taskfile + bash scripts
wrap the manual operations.

---

## 1. The platform prerequisites

| Concern | File | What it does |
|---|---|---|
| VolSync operator | `apps/storage-system/volsync/app/helm-release.yaml` | `manageCRDs: true`, `replicaCount: 1`, runs as UID/GID 1000 non-root, metrics auth disabled. Single replica (single-node homelab). |
| Operator wiring | `apps/storage-system/volsync/app.ks.yaml` | Flux Kustomization, `targetNamespace: storage-system`, `dependsOn: []` (no deps — it's a base layer). |
| Beta API enablement | `talos/patches/mutating-admission.yaml` | kube-apiserver `feature-gates: MutatingAdmissionPolicy=true` + `runtime-config: admissionregistration.k8s.io/v1beta1=true`. Required for the jitter policy in §5. |
| Jitter policy | `apps/storage-system/volsync/app/mutating-admission-policy.yaml` | Deployed as part of the volsync app (see §5). |
| Observability | `apps/storage-system/volsync/app/prometheus-rule.yaml`, `grafana-dashboard.yaml` | Alerting/dashboards for mover health (not central to the data flow). |

VolSync is a pure base dependency: apps that want backups declare
`dependsOn: volsync` (storage-system) and `1password-connect`
(security-system) in their own Flux Kustomization.

---

## 2. The reusable Component (the per-app surface)

`components/volsync/kustomization.yaml`:

```yaml
apiVersion: kustomize.config.k8s.io/v1alpha1
kind: Component
resources:
  - external-secret.yaml
  - replication-source.yaml
  - replication-destination.yaml
  - pvc.yaml
```

A `kind: Component` is a reusable bundle mixed into any Kustomization.
Every resource inside is templated with `${VAR:=default}` placeholders
resolved by **Flux post-build substitution** after `kustomize build`.

The only mandatory variable is **`APP`** — it names every resource:

| Resource | Name |
|---|---|
| PVC | `${VOLSYNC_PVC:=${APP}}` (defaults to `${APP}`) |
| ReplicationSource | `${APP}` |
| ReplicationDestination | `${APP}-dst` |
| ExternalSecret | `${APP}-volsync` |
| Generated Secret | `${APP}-volsync-secret` |

### 2.1 How an app opts in (`apps/media/jellyfin/app.ks.yaml`)

```yaml
spec:
  targetNamespace: media
  path: ./apps/media/jellyfin/app
  components:
    - ../../../../components/volsync/
  postBuild:
    substitute:
      APP: &-style anchor → jellyfin
      VOLSYNC_CAPACITY: 10Gi
      VOLSYNC_PUID: "568"
      VOLSYNC_PGID: "568"
  dependsOn:
    - {name: 1password-connect, namespace: security-system}
    - {name: volsync,           namespace: storage-system}
```

Net per-app cost: one `components:` line + a few `substitute:` values.
Everything else comes from component defaults.

---

## 3. The four generated resources (verbatim semantics)

### 3.1 ExternalSecret — `components/volsync/external-secret.yaml`

- Store: `ClusterSecretStore/onepassword`.
- One 1Password item, anchored: **"Garage HomeOps Backups Key"**.
- Pulls: `username` → access key, `password` → secret key, `url` →
  endpoint, `bucket`, `RESTIC_PASSWORD`.
- Templates a Secret `${APP}-volsync-secret` whose
  `RESTIC_REPOSITORY = s3:{{endpoint}}/{{bucket}}/volsync/${APP}`.

**Key design fact:** the Restic repo path is
`s3://…/<bucket>/volsync/<app>` — **no namespace in the path**. This is
deliberate and is what makes namespace migration work (§6.3).

### 3.2 ReplicationSource (backup) — `replication-source.yaml`

- `sourcePVC: ${VOLSYNC_PVC:=${APP}}`.
- `trigger.schedule: "0 */2 * * *"` — every 2 h on the hour, **identical
  for every app** (the herd problem §5 solves).
- `restic.copyMethod: ${VOLSYNC_COPYMETHOD:=Snapshot}` — CSI snapshot →
  temp volume → backup reads the frozen copy; app uninterrupted.
- `repository: ${APP}-volsync-secret`.
- `volumeSnapshotClassName: ${VOLSYNC_SNAPSHOTCLASS:=openebs-snapshots}`.
- Cache: `cacheCapacity 5Gi`, `cacheStorageClassName openebs-zfs`,
  `cacheAccessModes [ReadWriteOnce]`.
- `storageClassName: ${VOLSYNC_STORAGECLASS:=openebs-zfs}`.
- `moverSecurityContext`: runAs/fsGroup default **1000**, override per app
  (Jellyfin → 568), `fsGroupChangePolicy: OnRootMismatch`.
- `pruneIntervalDays: 14` (prune is expensive — not every run).
- `retain: {hourly: 24, daily: 7}`.

### 3.3 ReplicationDestination (restore) — `replication-destination.yaml`

- `metadata.labels: kustomize.toolkit.fluxcd.io/ssa: IfNotPresent` — Flux
  only sets it if absent, so a manual `trigger.manual` patch isn't
  immediately reverted.
- `trigger.manual: restore-once` — **manual, not cron**. A restore only
  fires when the trigger value changes (fresh create, or a manual patch).
- Same repo / cache / snapshot class / moverSecurityContext as the source.
- `capacity: ${VOLSYNC_CAPACITY:=5Gi}`.
- **`enableFileDeletion: true`** — restored volume matches the backup
  exactly (Restic restores are additive by default; this makes it a
  mirror).
- **`cleanupCachePVC: true`**, **`cleanupTempPVC: true`** — scratch
  volumes removed after restore.

### 3.4 PVC — `components/volsync/pvc.yaml`

```yaml
metadata:
  name: ${VOLSYNC_PVC:=${APP}}
  annotations:
    kustomize.toolkit.fluxcd.io/prune: disabled   # Flux must NOT delete the data PVC
spec:
  storageClassName: ${VOLSYNC_STORAGECLASS:=openebs-zfs}
  accessModes: [${VOLSYNC_ACCESSMODES:=ReadWriteOnce}]
  dataSourceRef:
    kind: ReplicationDestination
    apiGroup: volsync.backube
    name: ${APP}-dst
  resources: {requests: {storage: ${VOLSYNC_CAPACITY:=5Gi}}}
```

The `dataSourceRef` → ReplicationDestination is the hinge of the whole
automatic-restore mechanism (§6.1). `prune: disabled` ensures Flux pruning
never deletes the actual data volume.

---

## 4. Backup data flow (scheduled run)

1. Cron `0 */2 * * *` fires; VolSync controller reconciles the
   ReplicationSource.
2. `copyMethod: Snapshot` → VolSync asks the CSI driver
   (`zfs.csi.openebs.io`, class `openebs-snapshots`) for a VolumeSnapshot
   of `sourcePVC`, then provisions a temporary PVC from it. App keeps
   running against the live volume.
3. VolSync creates a mover Job named `volsync-src-<app>-…` with label
   `app.kubernetes.io/created-by: volsync`.
4. The MutatingAdmissionPolicy (§5) intercepts the Job CREATE and prepends
   a `jitter` init-container that sleeps a random 0–30 s.
5. After the sleep, the Restic mover pod runs: mounts the temp snapshot
   volume + the `${APP}-volsync-secret` env, runs `restic backup`. First
   run full; subsequent runs incremental, block-level dedup.
6. Every 14 days the run also `restic prune`s (reclaims forgotten
   snapshots). Retention enforced: 24 hourly, 7 daily.
7. Mover terminates; temp PVC + VolumeSnapshot deleted; ReplicationSource
   `.status` updated (last/next sync, result, logs).

---

## 5. The "thundering herd" fix

`apps/storage-system/volsync/app/mutating-admission-policy.yaml` — a
`MutatingAdmissionPolicy` + `MutatingAdmissionPolicyBinding`
(`admissionregistration.k8s.io/v1beta1`):

- **matchConstraints:** `batch/v1` `jobs`, CREATE + UPDATE.
- **matchConditions:** name starts with `volsync-src-` AND label
  `app.kubernetes.io/created-by == "volsync"`.
- **failurePolicy: Fail**, `reinvocationPolicy: IfNeeded`.
- **mutation (JSONPatch via CEL):** add `initContainers: []` then append
  a container:
  - image `ghcr.io/home-operations/busybox:1.37.0@sha256:026ed7…`
  - command `sh -c "sleep $(shuf -i 0-30 -n 1)"`

Effect: every backup mover waits a random 0–30 s before starting, so 20+
apps sharing `0 */2 * * *` naturally spread over a 30 s window instead of
hammering disk/network/NAS simultaneously. Requires the Talos apiserver
feature-gate patch (§1).

---

## 6. Restore data flow

### 6.1 Automatic restore on PVC creation (the GitOps path)

Triggered with zero manual action whenever the PVC is (re)created — fresh
cluster, deleted volume, **namespace move**, or storage migration.

1. Flux renders the component → ExternalSecret + RS + RD + PVC created
   together.
2. PVC's `dataSourceRef` points at `${APP}-dst`. Kubernetes' volume
   populator hands provisioning to VolSync.
3. VolSync runs a Restic **restore** mover from `s3://…/volsync/${APP}`
   into a freshly provisioned volume.
4. `enableFileDeletion: true` → restored content exactly matches the
   backup. `cleanupCachePVC/TempPVC` → scratch cleaned up.
5. PVC binds **only after** restore completes; the app then starts with
   data already in place.

**First-ever run:** no snapshots exist → restore finds nothing → PVC
binds **empty**, app starts fresh. He documents this as expected
first-run behaviour. (Noted here as a property of the design, not judged.)

### 6.2 Manual restore into a running app (the Taskfile path)

`task volsync:restore APP=<app> [NS=<ns>] [TS=<RFC3339>]`

Taskfile (`.taskfiles/volsync.yaml`) preconditions: `${APP}-volsync-secret`
exists AND `replicationdestination ${APP}-dst` exists. Then runs
`.scripts/volsync-restore.sh APP NS TRIGGER [TS]`. Exact sequence:

1. `flux suspend helmrelease ${APP} -n ${NS}` — stop Flux fighting back.
2. `kubectl scale deployment -l app.kubernetes.io/instance=${APP}
   --replicas=0` then `kubectl wait pod … --for=delete --timeout=120s`.
3. `kubectl patch replicationdestination ${APP}-dst` →
   `spec.trigger.manual = restore-<UTC ts>` and
   `spec.restic.restoreAsOf = <TS>` (or `null` for latest). **`restoreAsOf`
   is the point-in-time control** — newest snapshot at/before that time.
4. Poll until `.status.lastManualSync == TRIGGER`, printing the
   `Synchronizing` condition reason each 5 s; then assert
   `.status.latestMoverStatus.result == "Successful"` (else print
   `.status.latestMoverStatus.logs`, exit 1).
5. `flux resume helmrelease ${APP}` +
   `flux reconcile helmrelease ${APP} --with-source --force` → app scales
   back up onto restored data.

### 6.3 Namespace migration (why §3.1 matters)

Because the Restic path is namespace-agnostic
(`s3://…/volsync/<app>`): delete the app from namespace A (PVC and all),
deploy the identical Kustomization into namespace B. B's new PVC's
`dataSourceRef` triggers a restore from the *same* repo → data follows.
Flux handled state; VolSync handled data. This is also exactly how he
**migrated the whole cluster off Ceph onto OpenEBS** (see doc 02 §5).

---

## 7. The full manual operations surface

`.taskfiles/volsync.yaml` → thin CLI; logic in `.scripts/volsync-*.sh`:

| Task | Script | Behaviour |
|---|---|---|
| `volsync:snapshots APP NS` | `volsync-snapshots.sh` | `kubectl run` a throwaway `restic/restic:latest` pod, `args:[snapshots]`, `envFrom ${APP}-volsync-secret`; poll phase 2 s (≤60 s); print logs; delete pod. |
| `volsync:backup APP NS` | `volsync-backup.sh` | Patch RS `spec.trigger.manual=backup-<ts>`; poll until `lastManualSync==trigger`; assert result Successful (else dump mover logs, exit 1). |
| `volsync:backup-all [NS]` | `volsync-backup-all.sh` | Enumerate all RS (namespace or `-A`); fan out `volsync-backup.sh` in parallel (bg PIDs); `wait` each; collect + report failures. |
| `volsync:restore APP NS [TS]` | `volsync-restore.sh` | §6.2. |

All tasks default `NS` to the current kubeconfig namespace and validate
preconditions before mutating anything.

---

## 8. End-to-end summary diagram (textual)

```
1Password "Garage HomeOps Backups Key"
        │ (ESO / ClusterSecretStore onepassword)
        ▼
${APP}-volsync-secret  (RESTIC_REPOSITORY=s3://…/volsync/${APP})
        │
   ┌────┴───────────────────────────────┐
   ▼                                     ▼
ReplicationSource ${APP}            ReplicationDestination ${APP}-dst
 cron 0 */2 * * *                    trigger: manual
 copyMethod Snapshot                 enableFileDeletion / cleanup*
   │                                     ▲
   │ CSI VolumeSnapshot (openebs-snapshots)│ dataSourceRef
   ▼                                     │
 temp PVC ──► Restic mover Job ──► S3 (Garage on NAS)
              ▲ jitter init (sleep 0-30s, MutatingAdmissionPolicy)
                                          │
                          PVC ${APP} (dataSourceRef → ${APP}-dst,
                          prune: disabled, sc openebs-zfs)
```

Backup = top path (RS → snapshot → mover → S3).
Restore = S3 → mover → new PVC, driven by the PVC's `dataSourceRef`
(auto) or a manual `trigger` patch on the RD.
