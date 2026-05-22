# VolSync/Kopia DR Validation Report

Generated: 2026-05-22

Repo: `talos-argocd-proxmox`

Cluster context: `omni-prod-talos-prod-cluster-talos-prod-sa`

Kubernetes server: `v1.36.0`

Scope: validate the operator-free, no-Helm, explicit PVC + ReplicationSource +
ReplicationDestination VolSync/Kopia disaster-recovery design. No destructive
actions were performed.

## Executive Summary

The target design is directionally correct, but the current repo + live cluster
state is **not ready for a nuke/rebuild/restore test**.

Static rendered wiring is good for the active manifests:

- 28 rendered backed-up PVCs after restoring karakeep's missing meilisearch
  resources to `my-apps/media/karakeep/kustomization.yaml`.
- Every rendered backed-up PVC has a matching ReplicationDestination.
- Every rendered backed-up PVC has a matching ReplicationSource.
- PVC names are preserved; workloads still mount the expected claim names.
- Installed CRDs accept the VolSync, External Secrets, PVC `dataSourceRef`, and
  MutatingAdmissionPolicy fields used by the manifests.
- No VolSync-specific Helm chart or `helmGlobals.chartHome` path remains in the
  rendered design.
- Argo CD no longer uses `--load-restrictor LoadRestrictionsNone`.

The live migration state still has blockers:

1. This working tree now adds temporary per-PVC `ServerSideDiff=false`
   annotations needed to avoid immutable PVC `dataSourceRef` dry-run failures,
   but live Argo remains wedged until those manifests are committed/applied and
   the apps are resynced.
2. `kopia-maintenance` still depends on deleted pvc-plumber-era
   `Secret/pvc-plumber-kopia`.
3. Several live ReplicationSources/ReplicationDestinations are still old
   chart-era objects using per-PVC repo secrets instead of
   `volsync-kopia-repository`.
4. Some VolSync YAML exists in source files but is not rendered by any active
   kustomization.
5. Karakeep was already live-broken; this working tree includes the manifest
   fix, but it has not been committed or applied by Argo yet.

Conclusion: **NO GO** for cluster nuke until the blockers below are fixed and
at least one non-destructive restore drill passes.

## Inventory

Full inventory is generated at `docs/volsync-dr-inventory.md` by:

```bash
python3 hack/validate-volsync-wiring.py \
  --exclude monitoring/prometheus-stack \
  --exclude infrastructure/database/cnpg-barman-plugin \
  --exclude infrastructure/storage/longhorn
```

Current generated totals:

- Rendered documents: 1105
- Render failures: 0 with the exclusions above
- Backed-up PVCs: 28
- Wiring failures: 0
- Inactive source VolSync docs: 6

The 28 rendered backed-up PVCs are:

| Namespace | PVCs |
|---|---|
| copyparty | `copyparty-data` |
| fizzy | `data` |
| frigate | `frigate-config` |
| gitea | `gitea-shared-storage` |
| home-assistant | `config` |
| homepage-dashboard | `config` |
| immich | `library` |
| jellyfin | `config` |
| karakeep | `data-pvc`, `meilisearch-pvc` |
| n8n | `data` |
| nginx-example | `storage` |
| open-webui | `storage` |
| paperless-ngx | `data`, `media` |
| perplexica | `perplexica-data` |
| posthog | `postgres-data`, `redis7-data`, `redpanda-data-kafka-0` |
| project-nomad | `flatnotes-data`, `mysql-data`, `nomad-storage`, `qdrant-data` |
| project-zomboid | `zomboid-data` |
| redis-instance | `redis-master-0` |
| swarmui | `swarmui-data`, `swarmui-output` |
| tubesync | `config-pvc` |

Inactive source VolSync docs:

- `my-apps/home/project-nomad/kolibri/pvc.yaml`: disabled app; contains
  `kolibri-data` RS/RD that are not rendered.
- `my-apps/media/copyparty/config-pvc.yaml`: contains `config` RS/RD that are
  not rendered.
- `my-apps/media/copyparty/media-pvc.yaml`: contains `copyparty-media` RS/RD
  that are not rendered.

## Static Validation

Command:

```bash
python3 hack/validate-volsync-wiring.py \
  --exclude monitoring/prometheus-stack \
  --exclude infrastructure/database/cnpg-barman-plugin \
  --exclude infrastructure/storage/longhorn \
  --json /tmp/volsync-wiring-summary.json
```

Result:

- Active rendered VolSync wiring: PASS
- Source-file inactivity check: FAIL until the six inactive source docs are
  removed, documented, or made active intentionally.

The exclusions are not hiding VolSync failures:

- `monitoring/prometheus-stack` renders a large upstream chart whose CRD YAML
  trips PyYAML parsing on a non-VolSync enum value.
- `infrastructure/database/cnpg-barman-plugin` and
  `infrastructure/storage/longhorn` require network access for remote sources
  or Helm charts in the sandbox.

Targeted renders:

- `kustomize build my-apps/media/karakeep --enable-helm`: PASS
- `kustomize build infrastructure/storage/volsync-backup-cluster --enable-helm`:
  PASS
- `kustomize build infrastructure/storage/volsync --enable-helm`: PASS render,
  but server-side dry-run is noisy on CRD annotation size, which is an upstream
  CRD/apply-mode issue rather than VolSync PVC wiring.

## Schema Validation

Live API checks:

- `kubectl version`: client `v1.35.4`, server `v1.36.0`
- `volsync.backube/v1alpha1`: installed
- `ReplicationSource`: installed
- `ReplicationDestination`: installed
- `KopiaMaintenance`: installed, though not used by the current manifests
- `external-secrets.io/v1`: installed
- `ClusterExternalSecret`: installed
- `admissionregistration.k8s.io/v1`: installed
- `MutatingAdmissionPolicy`: installed
- `VolumeSnapshotClass`: `longhorn`, `longhorn-snapclass` exist
- `StorageClass`: `longhorn` exists and is default

`kubectl explain` confirmed the installed VolSync CRDs support the fields used
by the repo:

- RS/RD `spec.kopia.repository`
- `username`
- `hostname`
- `sourceIdentity`
- `copyMethod: Snapshot`
- `storageClassName`
- `volumeSnapshotClassName`
- `cacheCapacity`
- `capacity`
- `accessModes`
- `moverSecurityContext`
- `retain`
- `compression`
- `parallelism`

PVC `spec.dataSourceRef` is accepted by the installed API and supports
non-core volume populators.

## Wiring Validation

Rendered manifest checks:

| Check | Result |
|---|---|
| PVC `dataSourceRef.kind=ReplicationDestination` has same-namespace RD | PASS |
| PVC `dataSourceRef.apiGroup=volsync.backube` | PASS |
| PVC requested size equals RD capacity | PASS |
| PVC storageClass equals RD storageClass | PASS |
| PVC accessModes equal RD accessModes | PASS |
| RD `copyMethod=Snapshot` | PASS |
| RD has `moverSecurityContext` | PASS |
| RS name/sourcePVC matches PVC | PASS |
| RS has schedule/manual trigger | PASS |
| RS has `moverSecurityContext` | PASS |
| RS/RD reference a rendered Secret, ExternalSecret, or ClusterExternalSecret | PASS |
| Workload `persistentVolumeClaim.claimName` references resolve | PASS |
| StatefulSet claim templates are not mistaken for standalone PVCs | PASS |
| Schedules are not all identical | PASS |

The desired Secret path is one shared ClusterExternalSecret:

- ClusterExternalSecret: `volsync-kopia-repository`
- Generated Secret name: `volsync-kopia-repository`
- Namespace selector: `volsync.backube/privileged-movers=true`
- Live status: `Ready=True`
- Live generated Secret exists in all currently-labeled backup namespaces.

No Secret values were printed during validation.

## Runtime Validation

Healthy/available:

- Argo CD core pods: Running
- VolSync controller: Running
- Longhorn pods: Running
- Snapshot controller: Running
- External Secrets Operator: Running
- 1Password Connect: Running
- `volsync-kopia-repository` Secret exists in labeled backup namespaces
- VolumeSnapshots observed are `READYTOUSE=true`
- Current VolSync CRDs and storage classes exist

Not healthy / not ready:

- `my-apps-karakeep` is live Degraded. The pod fails because
  `karakeep-configuration` is missing. This working tree fixes the
  kustomization.
- `kopia-maintenance` is broken:
  - Live pod: `volsync-system/kopia-maintenance-29656837-bxqx7`
  - State: `ContainerCreating`
  - Event: `MountVolume.SetUp failed for volume "kopia-credentials" : secret
    "pvc-plumber-kopia" not found`
- Argo applications with backed-up PVCs are still wedged by server-side diff on
  immutable PVC fields. Examples:
  - `my-apps-copyparty`
  - `my-apps-fizzy`
  - `my-apps-home-assistant`
  - `redis-instance`
- Live RS/RD state still includes old chart-era resources using repo secrets
  like `volsync-data`, `volsync-config`, `volsync-frigate-config`,
  `volsync-nomad-storage`, etc.

Live ReplicationSource repo-secret split:

- New desired path: `volsync-kopia-repository`
- Old path still live in several namespaces:
  - `copyparty`
  - `fizzy`
  - `frigate`
  - `home-assistant`
  - `homepage-dashboard`
  - `paperless-ngx`
  - `project-nomad`
  - `project-zomboid`
  - `nginx` stale namespace

Backup evidence:

- Many live RS have successful recent backups.
- Some are backing up to the old per-PVC repo secrets, not the new shared repo.
- Orphan RS with no live source PVC show errors:
  - `copyparty/config`
  - `copyparty/copyparty-media`
  - `project-nomad/kolibri-data`
  - `nginx/storage`

## Restore Drill

No restore drill was executed.

Reason: current live cluster is in a mixed migration state. A drill now would
either test old chart-era repo secrets or partially mask the new shared-repo
path. It would not be a clean proof of the final design.

Recommended next non-destructive restore drill after blockers:

1. Simple app: `jellyfin/config` or `nginx-example/storage`.
2. Multi-PVC app: `paperless-ngx/data` and `paperless-ngx/media`.

Use `hack/volsync-backup-all.sh --execute --namespace <ns>` only after
reviewing the selected app; the script defaults to dry-run.

## Nuke Readiness

Current status: **NO GO**.

Go/no-go gates:

| Gate | Current state |
|---|---|
| Active manifests render | PASS with documented exclusions |
| Static PVC/RD/RS wiring | PASS |
| Inactive VolSync source docs | FAIL |
| Argo apps with backed-up PVCs all Synced | FAIL |
| All live RS/RD use `volsync-kopia-repository` | FAIL |
| `kopia-maintenance` succeeds | FAIL |
| Karakeep live app healthy | FAIL until current fix is applied |
| Backup evidence in final shared repo | PARTIAL |
| Non-destructive restore drill | NOT RUN |

## Required Fixes

### P0: Apply Argo server-side diff fix for immutable PVC dataSourceRef

Evidence: live Application statuses show Argo's server-side diff dry-run tries
to null or change immutable `spec.dataSourceRef`/`spec.dataSource` and the API
rejects it.

Existing ignore rules and `RespectIgnoreDifferences=true` are not enough while
global `controller.diff.server.side=true` is enabled.

Temporary staged fix in this working tree:

- Every rendered PVC with a static VolSync `dataSourceRef` now carries
  `argocd.argoproj.io/compare-options: ServerSideDiff=false`.
- Gitea's chart-rendered `gitea-shared-storage` PVC gets the same annotation via
  the existing Kustomize patch in `my-apps/development/gitea/kustomization.yaml`.
- The ApplicationSet templates preserve manually-applied Application-level
  compare-options annotations during this migration. In this Argo CD version,
  the PVC-level annotation alone does not stop the global server-side diff
  dry-run; affected live Applications also need temporary
  `argocd.argoproj.io/compare-options: ServerSideDiff=false`.

This is intentionally not enforced by `hack/validate-volsync-wiring.py` as a
permanent design rule. Once every affected live PVC has been recreated with the
desired `dataSourceRef` from Git, or after a clean nuke/rebuild creates fresh
PVCs from Git, remove the PVC/Application annotations and the ApplicationSet
preservation rule, then verify Argo still converges with global server-side diff
enabled.

This is a correctness blocker because Argo cannot reliably converge the app
state while the PVC exists. It remains a live-cluster blocker until the staged
change is committed/applied and affected apps resync cleanly. Do not remove the
temporary annotations immediately after a normal sync: the existing Bound PVCs
will still have their old immutable `dataSourceRef` state until they are
recreated.

### P0: Fix kopia-maintenance secret dependency

File: `infrastructure/storage/volsync/kopia-maintenance-cronjob.yaml`

Current broken dependency:

- Mounts `Secret/pvc-plumber-kopia`
- That Secret no longer exists.

Minimal fix:

- Make `volsync-system` receive or own `Secret/volsync-kopia-repository`.
- Update the CronJob Secret mount and path from `pvc-plumber-kopia` to
  `volsync-kopia-repository`.
- Update stale comments so future readers do not chase pvc-plumber.

### P0: Converge live RS/RD repo-secret state

Rendered desired state references `volsync-kopia-repository`; live old
chart-era resources still reference per-PVC secrets.

Minimal fix:

- Stop/clear old long-running failed sync operations in Argo.
- Apply the Argo server-side diff fix.
- Sync apps so live RS/RD switch to `volsync-kopia-repository`.
- Verify a successful backup in the shared repo for every critical PVC before
  restore/nuke testing.

### P0: Apply karakeep kustomization fix

File changed in this working tree:

- `my-apps/media/karakeep/kustomization.yaml`

Reason:

- `karakeep-web` references `karakeep-configuration`.
- `karakeep-web` references `karakeep-meilisearch`.
- Neither the configMapGenerator nor meilisearch resources were rendered before
  this fix.

### P1: Resolve inactive source VolSync docs

Choices:

- Delete or archive inactive `copyparty/config-pvc.yaml` and
  `copyparty/media-pvc.yaml` if those PVCs are no longer real.
- Or add them to `my-apps/media/copyparty/kustomization.yaml` and update the
  workload mounts if they are intended to exist.
- Leave `project-nomad/kolibri/pvc.yaml` disabled, but document that the inline
  VolSync resources are dormant while Kolibri is disabled.

### P1: Clean old live orphans

After Argo convergence is fixed:

- Delete old orphan RS/RD/PVCs for `copyparty/config`,
  `copyparty/copyparty-media`, `project-nomad/kolibri-data`, and stale
  namespace `nginx`.

### P2: Documentation cleanup

Several docs and CLAUDE files still refer to the old VolSync Helm chart or
pvc-plumber era as current process. These are not runtime blockers, but they
will mislead the next maintenance pass.

## New Validation Artifacts

- `hack/validate-volsync-wiring.py`: static render + wiring validator.
- `docs/volsync-dr-inventory.md`: generated inventory.
- `docs/cluster-dr-nuke-restore-runbook.md`: gated full DR runbook.
- `hack/volsync-status.sh`: read-only live status.
- `hack/volsync-backup-all.sh`: dry-run-by-default backup trigger helper.
- `hack/volsync-restore-watch.sh`: live restore watcher.
