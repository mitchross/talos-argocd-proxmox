# Cluster-scoped pieces — operator-free VolSync safety interlock

ArgoCD-managed under `clusters/talos/argocd/core-dependencies/volsync-backup-cluster-app.yaml`
at sync wave 2 (same as pvc-plumber — both coexist safely during the
full migration off pvc-plumber; the MAP targets Jobs while pvc-plumber
webhooks target PVCs, no admission conflict).

| File | What | Applied via |
|---|---|---|
| `clusterexternalsecret.yaml` | Creates one shared `volsync-kopia-repository` Secret in every namespace labeled `volsync.backube/privileged-movers=true`. The inline `ReplicationSource`/`ReplicationDestination` resources reference this Secret directly. | ArgoCD (Kustomize). |
| `mutating-admission-policy.yaml` | MAP + Binding that injects a `wait-for-rustfs` init container into every VolSync mover Job. Fail-closed on hard-unreachable backend. Uses `admissionregistration.k8s.io/v1` (MAP is GA on K8s 1.34+). | ArgoCD (Kustomize). |
| `talos-patch.yaml` | **NOT APPLIED on this cluster.** Retained as documentation only — captures the apiserver dependency for pre-1.34 clusters. K8s 1.36+ has MAP at `admissionregistration.k8s.io/v1` GA by default. Deliberately not listed in `kustomization.yaml`. | Omni (only if needed). |

Verified 2026-05-21 via `kubectl api-resources --api-group=admissionregistration.k8s.io`:
`mutatingadmissionpolicies` at `admissionregistration.k8s.io/v1`.

## What this buys back

The MAP is the *single* residual safety the migration keeps from pvc-plumber:
"refuse to run the mover when the backend can't be reached, so a fresh
empty PVC never gets captured into the repo." See
`../../00-compare-and-contrast.md` §Option C for the full reasoning. Unlike
pvc-plumber it:

- has no operator pod (no SPOF binary, no CrashLoop deadlock — the 2026-05-17
  SwarmUI incident class disappears),
- is scoped to mover Jobs only — PVC creation is never gated, so the cluster-
  wide blast radius pattern is structurally impossible,
- reuses author's existing jitter-MAP shape (`mirceanton/home-ops`
  `apps/storage-system/volsync/app/mutating-admission-policy.yaml`).

## What it consciously does NOT cover

The "soft authoritative no-snapshot" class — RustFS is reachable but the
repo is silently mispointed (rotated creds, wrong prefix, post-migration
first boot). The MAP probe passes; the mover runs; Kopia returns "no
snapshots"; the populator binds empty. Same exposure as the author. This
is accepted future-burn territory, mitigated by Kopia's append-only +
`restoreAsOf` recoverability until prune.

## Sequencing during cutover

ArgoCD owns sync; the standalone Application lands the MAP at wave 2.

1. Verify MAP is available (K8s 1.34+):
   `kubectl api-resources --api-group=admissionregistration.k8s.io` should
   show `mutatingadmissionpolicies` at `admissionregistration.k8s.io/v1`.
2. Confirm the shared repository Secret fans out:
   `kubectl get externalsecret -A | grep volsync-kopia-repository`.
3. Confirm the MAP+Binding are synced:
   `kubectl get mutatingadmissionpolicy,mutatingadmissionpolicybinding`.
4. Sanity test with T7 in `docs/research/pvc-backup-simplification/test-plan.md`
   — T7a (backup-side injection sanity) and **T7b (restore-side, the
   load-bearing safety proof)**.

## Bootstrap-chaos sizing notes

The `wait-for-rustfs` init container is configured with a 1-hour timeout
(was 10 minutes in an earlier draft — bumped after noting that a real
cold-start can easily exceed 10 min: 1P Connect at wave 0 → ESO
materialising the shared `volsync-kopia-repository` Secret → RustFS pod scheduling
on Longhorn → VolSync mover container actually starting). If the Job
fails inside that window, the Job's `backoffLimit` (default 6) will burn
retries in a fresh-cluster scenario and you can end up with a
permanently-failed restore Job that doesn't self-heal.

Things to verify live in T7b before relying on the current values:

- `kubectl get job <volsync-dst-...> -o jsonpath='{.spec.backoffLimit}'`
  (how many retries before Permanent Failed)
- `kubectl get job <volsync-dst-...> -o jsonpath='{.spec.activeDeadlineSeconds}'`
  (if VolSync sets a Job-level deadline — could cap wait-for-rustfs
  effectively shorter than 1h regardless of init timeout)

Tune the 1h init timeout downward only if you have evidence the
bootstrap chain is faster than that on this cluster. Upward only if T7b
shows the 1h ceiling getting hit during deliberate cold-start tests.
