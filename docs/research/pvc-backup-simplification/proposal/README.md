# Proposal — full migration off pvc-plumber to declarative VolSync (author-spec + MAP)

Status: PROPOSAL on exploratory branch (`claude/analyze-k8s-backup-transcript-eRrS2`). Not for merge. No PR.
Date: 2026-05-21.

Goal — as close to `mirceanton/home-ops` as ArgoCD allows, **pvc-plumber
gone entirely**, and a single MAP-based safety interlock for the one
failure class (hard-unreachable backend) that the populator alone can't
fail-closed on.

## Three pieces

| Dir | What | Per-app or cluster-wide |
|---|---|---|
| `chart/` | Local Helm chart inflated via Kustomize `helmCharts:` per app. Renders ExternalSecret + ReplicationSource + ReplicationDestination (+ optionally the PVC). Mirrors `mirceanton/home-ops/components/volsync/` 1:1 in shape, adapted to Kopia. | per-app |
| `cluster/` | MutatingAdmissionPolicy + Binding that inject a `wait-for-rustfs` init container into every VolSync mover Job. Plus the 4-line Talos patch enabling the MAP feature gate. | cluster-wide (once) |
| `ops/` | Taskfile + 3 scripts — manual `snapshots` / `backup` / `restore` (incl. `restoreAsOf` point-in-time). Argo+Kopia port of author's Flux+Restic originals. | operator UX |

## What's NOT here

- pvc-plumber. By design. Decommissioned in `../migration-plan.md` Phase 4.
- Per-PVC admission webhook. Replaced by the cluster MAP (Job-level gate, not PVC-level).
- An operator pod of any kind. The whole point.

## How an app consumes this

Worked example in `chart/README.md` — open-webui changes from a ~19-line
`pvc.yaml` + a one-line `backup: "daily"` label to:

- `pvc.yaml` gains a static `dataSourceRef → storage-dst` + a `restore-policy: strict` label
- `kustomization.yaml` gains a ~10-line `helmCharts:` entry pointing at `chart/`

The chart renders the per-PVC ES/RS/RD. The MAP gates the mover. Argo
prune handles cleanup. No operator generates anything.

## How the safety story holds together

See `../00-compare-and-contrast.md`. Short version:

| Failure class | Author-spec alone | This proposal | Old pvc-plumber |
|---|---|---|---|
| Backup exists, app deployed | Restores ✓ | Restores ✓ | Restores ✓ |
| No backup, fresh deploy | Binds empty ✓ | Binds empty ✓ | Allows empty ✓ |
| Backend hard-unreachable | Mover stays failing → PVC `Pending` (likely; T2) | **MAP fails Job explicitly** → Job retries with backoff → PVC `Pending` | Webhook DENY → ArgoCD backoff |
| Backend reachable, repo silently mispointed (rotated creds / wrong prefix) | **Binds empty** ✗ | **Binds empty** ✗ | **Allows empty** ✗ (also vulnerable — pvc-plumber decision-stateless) |
| pvc-plumber operator down | n/a | n/a | **All backup PVC creates DENIED cluster-wide** (SwarmUI incident) |

The soft-mispointed class is accepted future-burn (Kopia append-only +
`restoreAsOf` makes it recoverable until prune). The cluster-wide-deny
class disappears entirely.

## Order to read

1. `../00-compare-and-contrast.md` — the argument.
2. `../migration-plan.md` — phases, MUST-HAVES, decommission, rollback.
3. `../test-plan.md` — what to verify in what order. T2 is the only gate
   between Phase 0 and Phase 1; T7 verifies the MAP.
4. `cluster/README.md` then `chart/README.md` then `ops/README.md`.
