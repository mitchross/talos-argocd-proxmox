# Radar NG handoff — 2026-09-02

This is the continuation brief for Claude Fable 5.1 (or another engineer). It
records verified state, not guesses. Read the repository `CLAUDE.md` files
before changing anything. Use clean `/tmp` clones/worktrees; the user's main
Talos checkout has unrelated uncommitted work that must not be reset, staged,
or exported accidentally.

## Goal and architecture call

Radar NG is the priority product: a shareable React Native weather app backed
by self-hosted NOAA ingestion, immutable radar/forecast tiles, and Temporal.
Keep Temporal and use it seriously; this is also a Temporal learning project.

The target shape is:

- Keep the shared `maps.vanillax.me` VersaTiles service for generic basemaps.
  Radar owns a provider/fallback contract, so it is not trapped by that service.
- Give dynamic Radar artifacts a dedicated Radar RustFS bucket. Do not make NFS,
  SMB, Longhorn RWX, or one shared RWO filesystem the final tile architecture.
- Put only small authoritative metadata in a Radar-owned Postgres catalog on a
  two-replica Longhorn V1 storage class with Kopiur backups.
- Use bounded node-local `emptyDir` for render scratch.
- Keep NFS/SMB for static bulk assets, basemaps, and backup-style workloads.
- Keep Open-Meteo as one `Recreate` pod with one RWO PVC and two containers.
- Build a dedicated Radar Temporal control plane in Kubernetes namespace
  `radar-temporal`, logical Temporal namespace `radar-ng`, 32 immutable history
  shards, and three replicas each for frontend/history/matching/internal-worker
  spread over wired nodes. Use plain Postgres, not CNPG. The cluster still has
  one control-plane/etcd node, so do not claim full HA until that is fixed.

## Safety boundaries

- GitOps only for cluster configuration.
- Never purge the Temporal DLQ.
- Never use a manual Schedule trigger as proof of timer health.
- Do not cut schedules to isolated queues until the observe-only worker image is
  verified on all six workers.
- Do not restore, force-detach, format, or manually salvage the current Temporal
  PVC. Its original replica recovered.
- Do not merge draft render-once or observe-only work without the gates below.
- The user granted temporary permission to merge reviewed PRs in this session.
  Confirm again if there is any doubt after handoff.
- iPhone/device validation is intentionally deferred by the user. Keep
  `CAROUSEL_WINDOW=1` until that validation happens.

## Repository state and remotes

- Talos GitOps: `/home/vanillax/programming/talos-argocd-proxmox`, GitHub remote
  `origin`, default branch `main`.
- Radar source: `/home/vanillax/programming/radar-ng`, GitHub remote `github`,
  default branch `master`. Its `origin` is the older private Gitea mirror.
- The root Talos checkout is dirty and behind. In particular, it contains an
  uncommitted HP Elite worker block in
  `omni/cluster-template/cluster-template-prod-v2.yaml` plus
  `omni/machine-classes/hp-elite-worker.yaml`, along with unrelated Omni,
  SurfSense, and README work. Do not infer branch cleanliness from it.
- Before publishing a node-tag PR, ask whether the HP Elite Omni work is meant
  to be retained and published. A safe alternative is to tag only already
  committed wired nodes first.

## Merged in this continuation

Radar NG:

- #43 backend release-image CI — merge `55e8fe0`.
- #44 truthful/accessibile mini-map state — merge `3d52748`.
- #47 native connectivity/offline lifecycle — merge `aea1d3b`.
- #45 corrected production release documentation — merge `4984d8b`.
- #42 unified Open-Meteo serve/sync artifact — merge `b65075a`.

Talos GitOps:

- #2180 corrected Phase 1 queue-cutover runbook — merge `00b2b53`.
- #2178 Temporal timer-DLQ alert/runbook — merge `efbba4f`.
- #2181 dormant `longhorn-wired-ha` StorageClass — merge `906b7bd`.
- #2176 all six Radar workers to v1.1.27 — merge `ec69930`.

The final post-merge Talos CI for `ec69930` passed. Argo initially cached the
old manifest while reporting the new revision as Synced. The documented
`argocd.argoproj.io/refresh=hard` annotation cleared the stale render and the
real rollout began. This was cache invalidation, not a manual workload patch.

## Live production state at handoff

### Recovered outage

The HP Elite node `192.168.10.172` stopped heartbeating at about 21:36Z and
returned around 22:19Z. The Temporal Postgres volume had one Longhorn replica
only, on disk UUID `88f6ad4c-e87c-44e1-a59d-5f531d2f637a`. The same disk UUID
returned. Longhorn auto-salvaged the original replica at 22:20:59Z without a
manual action. PostgreSQL performed WAL recovery, became writable, and
`pg_is_in_recovery()` returned false. DB-backed Temporal CLI checks passed.

The latest pre-outage backup object is
`temporal-postgres-data-hourly-20260902210600`, Kopia ID
`a94a426bd9ecb51c06f112f04915076f`. Its recovery point is the Longhorn
snapshot at about 21:06:12Z, not the 21:24 upload completion time. Had a restore
been required, acknowledged-history exposure was roughly 30–32 minutes.

The v2 timer DLQ still contains exactly five previously inventoried messages.
Do not purge or casually merge them; some belong to live News schedules.

### HRRR fix is proven

The natural 22:45Z `ingest-hrrr` Schedule action ran on pinned build
`radar-ng/radar-ng-worker:v1.1.27-59f5`. It completed in about 91 seconds,
processed all 18 forecast hours, and each hour rendered `radar-hrrr`.

The live manifest published 18 consecutive hourly frames from
`2026-09-02T22:00:00Z` through `2026-09-03T15:00:00Z`. A real tile returned
HTTP 200, `image/png`, a valid PNG signature, and
`Cache-Control: public, max-age=86400, immutable`.

Final rollout check: all six WorkerDeployments reached current=target v1.1.27,
all six new pods were Ready, and Argo was Synced/Healthy. The new MRMS pod had
briefly been Pending because the GPU node lacked 2 requested CPUs during the
old/new overlap; an old drained pool then terminated and MRMS scheduled without
manual intervention or ingestion downtime. The old v1.1.26 legacy and MRMS
pods were still Ready because pinned work/drain retention had not completed.
That is expected; do not delete them manually. Re-verify after handoff:

```sh
kubectl get workerdeployments -n radar-ng
kubectl get pods -n radar-ng -o wide
kubectl get application -n argocd my-apps-radar-ng
```

The version and Argo acceptance gates passed. Still verify fresh MRMS/nowcast
health, unchanged DLQ count, and natural old-version drainage. Do not reduce
the drain delay merely to make the dashboard green; object-store separation
will eventually remove the single-node rollout bottleneck.

## Ready PR that must wait for the worker rollout

Talos #2183: https://github.com/mitchross/talos-argocd-proxmox/pull/2183

- Exact image for both containers:
  `ghcr.io/mitchross/radar-ng-open-meteo-worker:v1.1.9@sha256:0387cac5a2c691a67680e7d696b687fb91f135b3b6c7a733e7c3d0c1bab422f9`
- Source revision `b65075ada2bf6c05777f3c117272fa39ce12ece2`.
- Same immutable image in serve and sync containers, `IfNotPresent`, explicit
  `/app/openmeteo-api` serve command, TCP probes, 40-second termination grace,
  one `Recreate` pod, same RWO PVC, and package-specific Renovate automerge off.
- All six GitHub checks and local validation passed; no review blocker.

Merge #2183 only after the six-worker v1.1.27 rollout is settled and no
Open-Meteo sync activity is running. Then require one pod transition, 2/2
Ready, identical image IDs for both containers, a successful forecast request,
and the next natural sync. Roll back by reverting the GitOps commit.

## Render-once / Phase 2

Existing draft PR: https://github.com/mitchross/radar-ng/pull/41

Remote draft head is older. The finished local branch is:

- Worktree:
  `/tmp/claude-1000/-home-vanillax-programming-talos-argocd-proxmox/ba2ae3fe-5e56-41f5-ab2c-d39992bdfb7f/scratchpad/wt-radar`
- Branch: `feat/render-once`
- Clean HEAD: `695dc4628f017bb0c3120f5c7c421b5f60105771`
- Tests: 174 backend/Temporal passed plus 36 subtests; Ruff, formatting, and
  diff checks passed.

It now fixes publication identity, legacy migration, real fsync error handling,
run-scoped nowcast grid keys/generation pruning, and publication locking. The
schema stays v2 with optional `frame.grid_key`; a new reader falls back to old
timestamp-only frames.

Before pushing this head to PR #41, run one fresh independent review of exact
`695dc462`. Keep the PR draft until the rollout plan is explicit: deploy the
compatible API reader first, then the writer emitting run-scoped keys. Rollback
in reverse only after the old writer has published a timestamp-addressed
manifest. Production/PVC canary and physical MapLibre decode remain release
gates. Benchmark before final fixes was roughly 7.77s/6.9MiB/134MiB peak for
legacy versus 2.12s/0.9MiB/7MiB indexed cold.

## Temporal observe-only / Phase 1 prerequisite

Draft PR #46: https://github.com/mitchross/radar-ng/pull/46

It removes automatic trigger/delete/recreate/terminate behavior, avoids no-op
Schedule updates, preserves operator state as far as SDK 1.30 permits, starts
pollers before reconciliation, makes retry failures non-fatal to polling, and
renders useful redacted critical log fields. Its local/remote reviewed head was
`6b70ba6`; full tests were 106 passed plus 63 subtests.

Do not merge #46 yet. First finish the replay gate below. Then merge/rebase the
observe-only work, let the exact image publish, and roll the same immutable
artifact to all six workers while schedules still target legacy `radar-ng`.
Only after a natural soak should legacy's sole
`USE_ISOLATED_TASK_QUEUES` flag change from `0` to `1`. Keep legacy as the only
Schedule seeder/observer and keep `SKIP_SCHEDULE_SEED=1` on all five role pools.

## Temporal replay gate — local work is rejected for now

- Clone: `/tmp/radar-ng-temporal-replay.HsrXIM/repo`
- Local commit: `4159503505d7de1944bb88f4a4cb270fe87052c1`
- Not pushed.

The registry is currently complete for all 12 workflow types, includes
AirQuality, and retains old Register/Delete push-token workflows. The tests and
sanitized synthetic histories pass, but an independent review correctly
rejected it as a flagship release gate.

Required fixes:

1. Gate the exact image in every build path by adding
   `RUN python -m unittest -q temporal.workflows.test_replay` to
   `temporal/Dockerfile` after source copy and `PYTHONPATH`, before `CMD`.
2. Remove/reject `temporal-worker` from both generic retag workflows:
   `.github/workflows/ghcr-retag-from-latest.yml` and
   `.gitea/workflows/retag-from-latest.yml`. A rescue retag must execute the
   embedded replay unittest inside pulled `latest` and fail closed for old
   images.
3. The private Gitea build and `backend/scripts/build-push.sh` publish directly;
   the Dockerfile gate must cover them too. Disable anonymous writes to the
   private registry outside this repo and restrict publishing credentials to
   protected CI.
4. Replace shallow one-per-workflow happy/no-op fixtures with immutable,
   versioned scenario paths. Add sanitized success, partial, ActivityError,
   signal, timer, geometry fanout, push, and continue-as-new histories for
   MRMS, HRRR, AQM, PollAlerts, and WatchStorm.
5. Allow multiple retained histories per workflow. Generate v1.1.26 fixtures
   from the old release image with synthetic inputs; never use production
   histories.
6. Independently discover decorated workflow classes and compare them with the
   registry, schedules/API routes, role registrations, and full legacy role so
   a future workflow cannot be omitted from both registry and fixture list.

After fixing, re-review before push. Merge the replay gate before any new
Temporal worker source release.

## Frontend alert freshness — local work needs one fix

- Clone: `/tmp/radar-ng-alert-freshness.6HgZb8/repo`
- Local commit: `195656e5d912f166e1e896dbe47d0691f7c26887`
- Base: `4984d8b`; current master additionally contains unrelated Open-Meteo
  merge `b65075a`.
- Not pushed.
- Existing checks: 23 suites / 162 tests, TypeScript, lint, and diff check pass.

The CAP lifecycle semantics are otherwise sound: `effective` is primary start,
`onset` fallback, `expires` is the hard end, earlier `ends` also closes the
alert, malformed present bounds fail closed, cached valid alerts survive
offline, and accessibility state is explicit.

One high-priority review fix remains: `useAlerts.ts` derives freshness without
`query.isStale`, `isFetching`, or `dataUpdatedAt`. A cached empty response after
hours in the background can therefore show “No active alerts” while foreground
refetch is still running. Treat stale/in-flight cached emptiness as
checking/unverified and reserve all-clear for a recent successful response.
Add a foreground-resume/stale-empty regression. Then rebase onto current master,
rerun the full frontend checks, obtain a fresh review, push, and open a PR.

## Storage migration

The merged `longhorn-wired-ha` class is deliberately dormant and not default:
Longhorn V1, two replicas, ext4, best-effort locality/autobalance, hard replica
node/zone/disk anti-affinity, and required Longhorn node tag `wired-storage`.
No current PVC changed.

Next sequence:

1. Resolve the user's uncommitted HP Elite Omni desired state.
2. Add `wired-storage` as a Longhorn node tag to trustworthy wired storage
   nodes; preserve hardware-specific disk tags.
3. Verify live Longhorn Node tags.
4. Provision a disposable PVC on `longhorn-wired-ha`; prove replicas land on
   different nodes/zones and rebuild after a controlled failure.
5. Only then restore/copy Temporal Postgres into a distinct restore-before-bind
   PVC on this class. Preserve the old PVC/PV/replica until acceptance.
6. Verify Postgres, Temporal DB-backed queries, Schedule timers, DLQ inventory,
   natural application runs, and a new Kopiur checkpoint before retiring old
   storage.

Longer term, move Radar tile/grid artifacts to a dedicated RustFS bucket and a
small Radar Postgres catalog. Keep current Open-Meteo and PMTiles RWO volumes.

## Plan status

- Phase 0, stop bleeding: merged and live.
- Phase 1, per-role pools: deployed; queue cutover deliberately not done.
- Phase 2, indexed render-once: locally complete at `695dc462`, needs exact-head
  independent review, draft PR update, API-reader-first canary, and device test.
- Phase 3, RustFS objects + Postgres catalog + stateless tile origin: designed,
  implementation not started.
- Phase 4, frontend: truthful status and offline lifecycle merged; alert
  freshness needs the one fix above; carousel stays at window 1 until device QA.
- Phase 5, dedicated 32-shard Radar Temporal + HA persistence/CoreDNS: designed,
  not deployed.
- Phase 6, load/failure testing: not started. Include worker drain/replay,
  object-store loss, Postgres failover/restore, DNS failure, upstream NOAA/NWS
  failure, cache correctness, and mobile poor-network scenarios.

## First commands for the next session

```sh
gh pr list --repo mitchross/radar-ng --state open
gh pr list --repo mitchross/talos-argocd-proxmox --state open
kubectl get nodes
kubectl get application -n argocd my-apps-radar-ng
kubectl get workerdeployments -n radar-ng
kubectl get pods -n radar-ng -o wide
kubectl -n temporal exec deploy/temporal-admintools -- \
  tdbg dlq list --print-json
```

Then finish the v1.1.27 acceptance, roll #2183 by itself, fix/review replay,
fix/review alert freshness, independently review/push render-once, and only then
return to the observe-only image and isolated queue cutover.

## Mink references

- `resources/temporal-postgres-and-radar-hrrr-recovery-completed-2026-09-02.md`
- `resources/temporal-postgres-outage-2026-09-02-the-hp-elite-node-19216810172-stopped-k.md`
- `resources/temporal-backup-completion-time-is-not-the-recovery-point.md`
- `resources/longhorn-wired-ha-contract-for-radar-and-temporal-use-the-opt-in-longhorn-wired.md`
- `resources/radar-open-meteo-unified-image-gitops-rollout-contract.md`
- `resources/radar-render-once-publication-and-durability-contract.md`
- `resources/radar-temporal-replay-safety-implementation-contract.md`
- `resources/radar-mobile-nws-alert-freshness-implementation.md`
- `projects/talos-argocd-proxmox/radar-ng-dedicated-temporal-and-storage-blueprint.md`
