# Kopia / VolSync Repository Maintenance

> **Status: VERIFIED HEALTHY.** Investigated read-only on 2026-06-01 after restore drills
> repeatedly logged `Found too many index blobs (~1400)`. Scheduled maintenance is healthy.
> Manual full maintenance is not required.

## Headline finding

**Maintenance is already automated, healthy, and was specifically tuned for this warning.**
A GitOps-managed CronJob `kopia-maintenance` (`clusters/talos/infra/volsync/kopia-maintenance-cronjob.yaml`)
runs every 6 h. The "too many index blobs" message is a **known, benign steady-state warning** — the
CronJob's header documents that the 6 h cadence was introduced on 2026-05-21 precisely to keep this
sustainable on RustFS. **No new maintenance job is required.** A one-off **full** maintenance is *optional*.

## What exists

| Item | Value |
|---|---|
| Repository | `s3://volsync-kopia/cluster` on RustFS (`192.168.10.133:30292`, TLS off) |
| Secret | `volsync-kopia-repository` (ClusterExternalSecret-fanned; `KOPIA_PASSWORD`, `AWS_*`, `KOPIA_REPOSITORY`, `KOPIA_S3_*`) |
| Maintenance owner | `maintenance@cluster` (`--override-hostname=cluster --override-username=maintenance`) |
| CronJob | `volsync-system/kopia-maintenance`, schedule `37 */6 * * *`, `concurrencyPolicy=Forbid`, `activeDeadlineSeconds=7200`, image `kopia/kopia:0.22.3` |
| Policy | `--quick-interval=24h --full-interval=168h`; runs `kopia maintenance run` (kopia picks quick vs full) |
| Recent jobs | last 3 all `Complete 1/1` (~15–18 s) — zero failures |
| Retention (per PVC) | `hourly:24, daily:7, weekly:4, monthly:2` |

## Why the warning appears (and is not a problem)

Kopia 0.22 uses **epoch-based indexing**. Index blobs accumulate within the current epoch; quick
maintenance advances/compacts epochs. The job history shows healthy compaction roughly every ~30 h
(e.g. `Compacted 751(318143) index blobs for epoch 5`). The count oscillates: it climbs toward ~1400
(the warning threshold), then an epoch advance compacts it back. The restore-drill burst (manual
`restore-drill-*-backup` snapshots) plus 24 PVCs on hourly/daily schedules is normal churn the CronJob
absorbs. **It is self-healing.**

## Backup activity / timing (why a window matters)

- Movers cluster in the **02:00–02:58 UTC daily storm** (all `* 2 * * *` schedules).
- Hourly backups fire at minutes `:00 :10 :17 :18 :27 :30 :34`.
- Maintenance fires at `:37` every 6 h.

## Procedure

### Option A — DO NOTHING (recommended)
The CronJob handles this. The next scheduled **full** maintenance (168 h interval) does a deeper
index compaction + snapshot GC and reclaims drill-snapshot space automatically. Just verify the
CronJob keeps succeeding. Lowest risk.

### Option B — Force ONE full maintenance now (optional)
Only to knock the index count down immediately / reclaim expired-drill-snapshot space sooner. Needs a
**one-off Job running `kopia maintenance run --full`** (the CronJob's default run stays *quick* until
the 168 h interval). Clone the live CronJob's `.spec.jobTemplate.spec`, change only the final command
to append `--full`, keep the same secret mount + connect logic + `--override-username=maintenance
--override-hostname=cluster`. **Never add `--safety=none`.** `kubectl create job --from=cronjob/...`
will **not** force full (it runs the default which stays quick) — a custom `--full` Job is required.

## Should backups be paused first?
**No.** Kopia maintenance is concurrency-safe: it holds a repo lock and full GC runs with default
`--safety=full`, keeping a time margin so it never deletes blobs an in-flight backup could reference.
Quick maintenance is fully safe alongside movers. The only hazard is `--safety=none` (break-glass only).

## Safest window (Option B)
Avoid **02:00–03:00 UTC** and the hourly minute marks (`:00 :10 :17 :18 :27 :30 :34`) and `:37`. A
clean window is any non-02 hour at ~`:45–:55` (e.g. `14:50 UTC`). The repo is small (~6 GiB dominant),
so a full run finishes in minutes, well under the 2 h deadline.

## Verification (before / after)
Connect as `maintenance@cluster` (throwaway pod) or read the next CronJob run's logs:
- `kopia maintenance info` — owner, quick/full intervals, last-run times.
- `kopia repository status` — reachable/consistent.
- `kopia index list | wc -l` — before ≈ ~1400, after full should drop substantially.
- `kopia content stats` / `kopia blob stats` — space before/after.
- `kopia snapshot list --all | wc -l` — confirm drill snapshots aged out per retention.
- Post-run: a normal mover backup still succeeds; `/audit` stays `already-matches`.

## Risks
1. Heavy full GC during the 02:xx storm → extra RustFS load (not data-unsafe; use the quiet window).
2. `--safety=none` → could delete blobs referenced by in-flight backups. **Never use it here.**
3. Manual one-off Job vs the scheduled `:37` run — kopia's repo lock serializes them, but run the
   one-off when no `:37` job and no movers are active.
4. RustFS unreachable mid-run — the maintenance Job has **no** `wait-for-rustfs` gate (that MAP only
   injects into mover Jobs), so it just fails to connect and exits non-zero (`backoffLimit`). Safe.

## No-go conditions
- RustFS / S3 endpoint unhealthy or flapping.
- A `:37` maintenance Job currently `Active`, or multiple movers mid-backup (i.e. don't run at 02:xx).
- `maintenance@cluster` owner can't be confirmed via `kopia maintenance info`.
- Any intent to pass `--safety=none`.

## Rollback
Kopia maintenance is **not a mutation you roll back** — operations are atomic. A failed/interrupted
run leaves the repo consistent; delete the failed Job and re-run or let the CronJob proceed. No
snapshots are deleted beyond what retention already dropped; `--safety=full` protects live data.

## Recommendation
**Option A (do nothing)** unless you specifically want the index/space reclaimed today. The maintenance
is already correct and GitOps-managed. If you want Option B, author the one-off `--full` Job from the
live CronJob spec and run it in a quiet window with before/after verification.
