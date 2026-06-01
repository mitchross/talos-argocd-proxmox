# pvc-plumber — Cheat Sheet 🃏

> One-page poster. Full intro: [pvc-plumber-start-here.md](pvc-plumber-start-here.md).

## 📍 Current state (2026-06-01)
`v4.0.1` permissive · **24 PVCs / 18 namespaces** managed · **24/24 DR_COMPLETE** ·
25/25 backups Successful · 4 restore drills passed · Kyverno removed · Longhorn 0 faulted/0 degraded.

## 🏷️ The 3 labels that matter
```
namespace:  pvc-plumber.io/managed-namespace: "true"     # write-gate
PVC:        pvc-plumber.io/enabled:           "true"     # opt-in
PVC:        pvc-plumber.io/tier:              "hourly"   # cadence  (+ manage-volsync: "true")
```

## 🧱 The 4 systems involved
| System | Job |
|---|---|
| **Argo** | desired state (PVC + labels) from Git |
| **pvc-plumber** | owns RS/RD wiring + `/audit` |
| **VolSync + Kopia** | moves bytes → RustFS S3 |
| **Longhorn** | live volume (CSI), snapshots for clones |

## 🔎 5 questions when debugging
1. Is the **namespace gated**? (`managed-namespace=true`)
2. Is the **PVC opted in**? (`enabled` + `manage-volsync` + `tier`)
3. Do **RS *and* RD** exist and are both `managed-by=pvc-plumber`?
4. Does the PVC have **`dataSourceRef → <pvc>-dst`** (else it recreates EMPTY)?
5. Is the **last backup `Successful`**? → check `/audit` (`already-matches` / `stale=false`).

## 🧪 Restore drill quick path
```
sentinel (embed OLD uid + sha256) → manual RS backup → RD refresh (new latestImage)
→ scale app to 0 → delete PVC → recreate (with dsr!) → verify sentinel byte-identical
→ scale up → restore RS schedule + RD restore-once trigger
```
⚠️ **Wait for `application.status.sync.revision == dsr commit` before deleting** (or stale render
recreates it empty). pvc-plumber does **not** revert your manual trigger patches — restore them yourself.

## 💥 Common failure modes
| Symptom | Cause / fix |
|---|---|
| PVC recreates **empty** | no `dataSourceRef` → add it (or mark EMPTY_BY_DESIGN) |
| `ComparisonError ... PVC is invalid: Forbidden` | added dsr to a **Bound** PVC (immutable) — clears on delete |
| scale-up sync "Succeeded" but replicas stay 0 | Argo **stale cluster cache** → hard-refresh, wait OutOfSync, re-sync |
| double-recreate needed | deleted before render cache caught up → wait for reconciled rev |
| scheduled backups stopped after a drill | RS left on `manual` trigger → restore `schedule` |
| restored volume `degraded` briefly | Longhorn replica rebuild — wait, don't touch replicas |

## 🚫 Never-migrate list
- **CNPG** databases → Barman → S3 (native).
- **PostHog** PVCs → `backup-exempt` (disposable).
- **redis-instance/redis-master-0** → deferred (decide: exempt vs migrate).

## ⏭️ Next ops tasks
1. Kopia maintenance — healthy; full not needed (`docs/kopia-maintenance-plan.md`).
2. Rollback PV cleanup — 7 retained; reclaim reset-batch first, per-PV approval.
3. Longhorn replica/storage policy review (`docs/storage-architecture-future.md`).
4. redis-instance final decision.
5. (future) pvc-plumber v5 strict-mode plan — **not shipped**.
