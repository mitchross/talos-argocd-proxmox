# Cluster-scoped pieces

Two things deploy once for the whole cluster (not per-app):

| File | What | Applied via |
|---|---|---|
| `mutating-admission-policy.yaml` | MAP + Binding that injects a `wait-for-rustfs` init container into every VolSync mover Job. Fail-closed on hard-unreachable backend. | ArgoCD (Kustomize) — eventually `infrastructure/storage/volsync-backup-cluster/`. |
| `talos-patch.yaml` | 4-line Talos apiserver patch enabling `MutatingAdmissionPolicy=true` feature gate + `admissionregistration.k8s.io/v1beta1=true` runtime-config. Required for the MAP above to be accepted. | Omni (merge into `omni/cluster-template/cluster-template.yaml`, rolling apply). |

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

1. Apply the Talos patch via Omni first (rolling reboot of control plane).
   Verify with: `kubectl api-resources | grep mutatingadmissionpolicies`.
2. Then apply the MAP/Binding (kubectl apply -k . or via ArgoCD).
3. Verify with `kubectl get mutatingadmissionpolicy,mutatingadmissionpolicybinding`.
4. Sanity test with T7 in `../../test-plan.md` — both T7a (backup-side
   injection sanity) and **T7b (restore-side, the load-bearing safety
   proof — PVC stays Pending while RustFS unreachable, then populates
   when it returns)**. T7b is *the* Phase-0 proof that the chain
   `dataSourceRef → populator → volsync-dst- Job → MAP → wait-for-rustfs
   → mover → bind` holds end to end.

Only then begin per-PVC chart cutover per `../../migration-plan.md`.

## Bootstrap-chaos sizing notes

The `wait-for-rustfs` init container is configured with a 1-hour timeout
(was 10 minutes in an earlier draft — bumped after noting that a real
cold-start can easily exceed 10 min: 1P Connect at wave 0 → ESO
materialising the per-PVC `volsync-<pvc>` Secret → RustFS pod scheduling
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
