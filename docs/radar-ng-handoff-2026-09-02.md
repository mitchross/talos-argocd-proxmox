# Radar NG end-to-end execution plan and handoff — 2026-09-02

This is the continuation brief and complete execution plan for Claude Fable
5.1 or a smaller coding model. It records verified state, explicit decisions,
ordered work packets, acceptance gates, and rollback boundaries. Read this
file once from top to bottom, then execute only one work packet at a time.

Facts marked live are a 2026-09-02 snapshot and must be refreshed before a
change. Plans are not deployed merely because they appear here. Read the
repository `CLAUDE.md` files before changing anything. Use clean `/tmp`
clones/worktrees; the user's main Talos checkout has unrelated uncommitted work
that must not be reset, staged, or exported accidentally.

## Source-of-truth order

Use this order when documents disagree:

1. read-only live evidence plus the Git commit Argo actually applied;
2. repository `CLAUDE.md` rules;
3. `my-apps/development/radar-ng/RUNBOOK.md` for current operations;
4. this handoff for cross-repository sequencing and verified local work;
5. Radar's `docs/reliability-and-scale-plan.md` for the long-term design.

The Radar canonical plan currently has stale status text and an unsafe old
queue step that transfers Schedule seeding to `aux`. Do not follow that step.
After Packet 0, open a small Radar docs-only PR that updates its live state,
marks HRRR/v1.1.27/Open-Meteo complete, points queue operations at the merged
runbook, and makes the indexed-PNG v1 choice explicit. Do not mix that cleanup
with code or a rollout.

## Goal and architecture call

Radar NG is the priority product: a shareable React Native weather app backed
by self-hosted NOAA ingestion, immutable radar/forecast tiles, and Temporal.
Keep Temporal and use it seriously; this is also a Temporal learning project.

The target shape is:

- Keep the shared `maps.vanillax.me` VersaTiles service for generic basemaps.
  Radar owns a provider/fallback contract, so it is not trapped by that service.
- Give dynamic Radar artifacts a dedicated Radar RustFS bucket. Do not make NFS,
  SMB, Longhorn RWX, or one shared RWO filesystem the final tile architecture.
- For the beta and flagship v1, publish pre-rendered immutable indexed PNGs to
  RustFS. COG/Zarr plus on-demand tiling remains a later measured R&D option;
  do not split the implementation across both models now.
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
- At the 23:12Z refresh, the root Talos checkout and `origin/main` were both
  `2d9e94d6`. The HP Elite worker desired state is committed there.
- The root checkout is still dirty with unrelated OpenTelemetry and SurfSense
  edits plus the local copy of this handoff. Never stage from that checkout or
  infer a task branch is clean from it.
- Before a node-tag PR, name the trusted wired nodes explicitly and verify
  their committed Omni definitions, live Longhorn disks, and topology zones.

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
- #2183 unified Open-Meteo v1.1.9 rollout — merge `7caae641`.
- HP Elite Talos worker desired state — commit `2d9e94d6`.

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

## Open-Meteo rollout now soaking

Talos #2183 merged at `7caae641`:
https://github.com/mitchross/talos-argocd-proxmox/pull/2183

- Exact image for both containers:
  `ghcr.io/mitchross/radar-ng-open-meteo-worker:v1.1.9@sha256:0387cac5a2c691a67680e7d696b687fb91f135b3b6c7a733e7c3d0c1bab422f9`
- Source revision `b65075ada2bf6c05777f3c117272fa39ce12ece2`.
- Same immutable image in serve and sync containers, `IfNotPresent`, explicit
  `/app/openmeteo-api` serve command, TCP probes, 40-second termination grace,
  one `Recreate` pod, same RWO PVC, and package-specific Renovate automerge off.
- All six GitHub checks and local validation passed; no review blocker.

At the 23:12Z refresh, Argo was `Synced/Healthy`, the new pod was 2/2 Ready,
and both containers used the exact digest above. The rollout still needs a
successful public forecast request and the next natural sync before it is
closed. If either fails, revert the GitOps merge through a PR; do not patch the
Deployment or PVC by hand.

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

1. Refresh the committed HP Elite Omni desired state and explicitly name the
   trustworthy wired nodes for the tag PR.
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

## Executor contract for a smaller model

This section is intentionally explicit. Do not infer missing permission or
skip a gate because a branch already exists.

### Status words

- **Live:** observed in Kubernetes or through the public endpoint.
- **Merged:** present on the default branch; it may still be waiting for Argo
  or an image rollout.
- **Ready local:** committed and tested in a worktree, but not yet pushed.
- **Draft:** pushed for review; never treat a green check as approval to deploy.
- **Planned:** architecture only. There is no runtime resource to operate yet.

When the state here conflicts with GitHub, Git, Argo, or Kubernetes, stop and
refresh the document. Git owns desired cluster state. Kubernetes proves actual
state. Neither one alone proves the user-visible result.

### One work packet at a time

For every packet below:

1. Read the root and nearest nested `CLAUDE.md`.
2. Refresh the remote default branch and current open PRs.
3. Record the starting commit, scope, invariants, tests, rollout, and rollback
   in the working notes before editing.
4. Use a clean worktree or clone based on the current remote default branch.
   Never develop in the dirty root Talos checkout.
5. Own a narrow set of files. Do not reformat or repair unrelated code.
6. Run focused tests first, then the complete relevant suite.
7. Ask an independent agent to review the exact final commit, not an earlier
   diff. Resolve every release blocker.
8. Push one coherent branch and open a draft PR. Verify the PR file list so no
   unrelated local work escaped.
9. Make the PR ready only when CI, review, rollout instructions, rollback, and
   observability are complete.
10. Merge only with current user authorization. The permission granted during
    this session should not be assumed after this handoff.
11. For GitOps, wait for Argo, inspect the actual image IDs and resources, then
    prove the application result. Never substitute a manual workload patch.
12. Save durable decisions, verified incidents, and runbooks to Mink. Do not
    save raw logs or guesses.

Before editing, fill out this packet header:

```text
Task ID:
Goal:
Non-goals:
Repository:
Base remote / branch / expected SHA:
Working directory:
Allowed files:
Dependencies already complete:
Source-of-truth evidence and UTC timestamp:
Exact requested change:
Tests required:
PR title and draft status:
Acceptance gates:
Rollback trigger:
Rollback action:
Post-rollback checks:
Stop conditions:
Next task unlocked:
```

One task uses one repository, branch, and PR. Source code merges and publishes
an immutable artifact before a separate GitOps PR deploys its digest. A rebase,
amend, or new commit invalidates earlier exact-head tests and review. Inspect
`gh pr diff`, `headRefOid`, and every required check before requesting merge.
Never use `kubectl apply`, `edit`, `patch`, `delete`, `rollout restart`, or
`rollout undo` for application state.

A finished packet reports:

```text
Starting SHA:
Final SHA:
PR:
Files changed:
Tests:
Independent review:
Desired-state result:
Live result:
Rollback:
Mink note:
Remaining risk:
```

### Universal stop conditions

Stop the active rollout and investigate if any of these occurs:

- a node becomes `NotReady`, a Longhorn volume is `Faulted`, or the Kopiur
  repository cannot be verified;
- Argo applies a revision other than the intended merge or stays
  `OutOfSync/Degraded`;
- a queue has no expected workflow or activity poller;
- the Temporal timer-DLQ count changes unexpectedly;
- MRMS exceeds the 10-minute stale page threshold or HRRR disappears;
- a new manifest advertises a missing, empty, partial, or undecodable tile;
- two renderer versions can write the same immutable output path;
- a migration would require deleting the only PVC, replica, database, bucket,
  or last-good manifest;
- a test needs production secrets or production Workflow history;
- the PR contains files outside the declared packet;
- an expected local-only worktree or exact commit no longer exists;
- acceptance would require a manual Schedule trigger or direct workload patch.

Do not “fix forward” across one of these boundaries. Keep the last good reader
and data, collect read-only evidence, then revert desired state through Git.

### Dependency map

```text
baseline soak
    |
    +--> replay-safe release gate
    |        |
    |        v
    |    observe-only worker on all six pools
    |        |
    |        v
    |    isolated queue cutover and soak
    |
    +--> render-once exact-head review
             |
             v
       API reader first -> one-role writer canary
             |
             v
       storage interfaces -> object shadow writes
             |
             v
       catalog/outbox -> stateless serving -> worker replicas
             |
             v
       publication fencing -> dedicated Temporal migration

Longhorn node tags -> disposable class canary -> catalog/Temporal PVCs

mobile truth/privacy -> backend alert/geocode contracts -> device performance
```

The independent frontend fixes may proceed while backend soak windows run.
The storage class canary may proceed before application migration, but no live
PVC moves until that canary passes.

## End-to-end work packets

### Packet 0 — refresh truth and protect the work

**Status: READY. Execute this first in every new session.**

**Goal:** start from evidence instead of the snapshot in this file.

Run from the appropriate clean checkout:

```sh
date -u
kubectl config current-context
git -C /home/vanillax/programming/talos-argocd-proxmox status --short --branch
git -C /home/vanillax/programming/talos-argocd-proxmox fetch origin main
git -C /home/vanillax/programming/talos-argocd-proxmox rev-parse HEAD origin/main
git -C /home/vanillax/programming/radar-ng status --short --branch
git -C /home/vanillax/programming/radar-ng fetch github master
git -C /home/vanillax/programming/radar-ng rev-parse HEAD github/master
git -C /home/vanillax/programming/radar-ng remote -v
gh pr list --repo mitchross/radar-ng --state open
gh pr list --repo mitchross/talos-argocd-proxmox --state open
git -C /home/vanillax/programming/radar-ng worktree list
kubectl get nodes -o wide
kubectl get application -n argocd my-apps-radar-ng
kubectl get workerdeployments,pods,pvc -n radar-ng
kubectl get snapshot.kopiur.home-operations.com -A
kubectl get nodes.longhorn.io -n longhorn-system -o yaml
```

Read the Schedule list, running Workflow inventory, and timer DLQ with the
documented Temporal admin commands in
`my-apps/development/radar-ng/RUNBOOK.md`; never purge it. The current shared
Temporal logical namespace is `default`. The future Radar logical namespace is
`radar-ng`; do not mix them.

Check the user-visible endpoints:

```sh
curl -sS https://radar-ng-api.vanillax.me/api/health | jq .
curl -sS https://radar-ng-api.vanillax.me/api/manifest.json | jq .
curl -sS https://radar-ng-api.vanillax.me/api/forecast/40.0/-83.0 | jq .
```

Record current default-branch SHAs, image digests, Argo revision, Schedule
queues, DLQ count, latest successful backup, manifest freshness, and open PR
heads. For every recorded local worktree, confirm its exact HEAD and clean
status before relying on it.

**Pass:** the six v1.1.27 WorkerDeployments are current=target, their new pods
are Ready, Argo is Synced/Healthy, HRRR and MRMS are fresh, Open-Meteo is 2/2,
and the remaining DLQ entries match the known inventory.

**Stop:** any mismatch means the next task is diagnosis, not implementation.

### Packet 1 — close the active Open-Meteo and worker rollouts

**Status: READY after Packet 0.**

**Goal:** finish the work already deployed before changing Temporal routing.

1. Confirm both Open-Meteo containers use the same v1.1.9 digest and have no
   restarts.
2. Make one real public forecast request.
3. Observe the next natural Open-Meteo sync activity. A manual trigger does not
   satisfy this gate.
4. Confirm all six v1.1.27 role/legacy workers keep their pollers.
5. Let old v1.1.26 legacy work drain naturally; do not delete pinned pods.
6. Observe fresh MRMS, nowcast, and the next natural HRRR publication.
7. Confirm the timer DLQ count does not grow.
8. Record two natural cadences for short schedules and enough time to include
   at least two six-hour GFS cadences before calling the broader soak complete.

**Pass:** natural Open-Meteo and radar cycles complete with fresh public data,
stable pods, and unchanged DLQ inventory.

**Rollback:** revert Talos #2183 through Git if the unified image fails. Keep
the RWO PVC and `Recreate` strategy intact.

### Packet 2 — finish mobile data truth and privacy

**Status: READY and independent of Packet 3.**

**Goal:** never tell a user “all clear” or “live” from unverified cached data,
and never leak exact coordinates through telemetry.

There are two local starting points:

- alert freshness:
  `/tmp/radar-ng-alert-freshness.6HgZb8/repo`, commit `195656e5`;
- manifest/privacy:
  `/tmp/radar-ng-frontend-privacy-manifest`, commit `d8a43fc`.

Do not delete, reset, or reclone these paths until their commits are preserved.
Do not blindly combine or cherry-pick them. Fetch current Radar `master`,
rebase each narrowly, inspect overlap with merged #44 and #47, and make
separate PRs if their responsibilities remain independent.

For alert freshness, fix the reviewed blocker: stale or in-flight cached empty
data must render checking/unverified, not “No active alerts.” Use
`isStale`, `isFetching`, and `dataUpdatedAt`; add a background-to-foreground
stale-empty regression. Keep valid cached alerts visible offline.

For manifest/privacy, retain runtime validation of network and MMKV manifests,
atomic frame/index publication, unchanged-data write avoidance, and
query-family-only telemetry. Re-run the privacy red-team after rebasing.

Run:

```sh
bun x tsc --noEmit
bun run lint
bun test
bun x expo install --check
git diff --check
```

The Expo dependency check had known SDK 57 patch drift. Do not hide it; either
fix it in a dedicated dependency PR or record it as pre-existing with exact
output.

**Pass:** stale-empty, offline cached alerts, malformed manifest, location
privacy, foreground refresh, and accessibility tests all pass.

**Rollback:** these are client-only changes. Revert the individual PR; do not
roll back the already-correct native connectivity foundation.

### Packet 2A — freeze the public API contract

**Status: READY as small source-only PRs; required for friends beta.**

**Goal:** old and new clients fail safely across server releases.

1. Define versioned typed contracts and checked-in fixtures for manifest,
   forecast, alerts, health/status, nowcast, inspect, wind, lightning, storms,
   tropical data, styles, and prefetch.
2. Generate JSON Schema or OpenAPI from the backend models and use the same
   fixtures in frontend tests.
3. Put manifest revision, coverage, source/issued/valid/ingested times,
   attribution, palettes, completeness, and freshness in the contract.
4. Decide and test whether clients consume a stable API tile route or the
   manifest's `tile_url_template`; do not publish a field the app ignores.
5. Reject unknown future schema majors while preserving the prior contract for
   at least one full reader/writer migration window.
6. Add one bounded error shape, typed client errors, ETags/304s, explicit cache
   headers, response-size caps, timeouts, cancellation, and request
   coalescing for identical forecast misses.
7. Split internal liveness/readiness/metrics from a sanitized public status.
8. Replace `/tmp/uvicorn.log` and background shell supervision with real
   process supervision or separate Caddy/API containers.

**Pass:** old-client/new-server and new-client/old-server suites pass;
malformed/oversized responses are never cached; stale last-good data is honest;
an API process death cannot leave a healthy-looking proxy pod.

### Packet 2B — close the public security boundary

**Status: READY after the public-route inventory; required for friends beta.**

**Goal:** expose only intended public reads.

1. Inventory the current Gateway route. Replace catch-all exposure with
   explicit public prefixes.
2. Keep metrics, FastAPI docs, detailed health, disk capacity, internal URLs,
   Temporal, RustFS, and Postgres cluster-only.
3. Add default-deny Radar NetworkPolicies with explicit Gateway, monitoring,
   DNS, Temporal, object, catalog, OTel, and upstream egress.
4. Give each workload a dedicated ServiceAccount; disable token automount when
   unused.
5. Apply non-root, dropped capabilities, seccomp, read-only root filesystem,
   and bounded writable scratch where compatible.
6. Strip untrusted forwarded headers and use a configured canonical public
   base URL.
7. Put route-specific rate, concurrency, request-size, and timeout limits at
   the Gateway. Tile traffic bypasses FastAPI, so API-only limits are not
   sufficient.
8. Lock Python dependencies, generate SBOM/provenance, scan images, and deploy
   only reviewed immutable digests.

**Pass:** an external scan reaches only documented reads; spoofed forwarding
headers do not change identity/origin behavior; automated log scans find no
coordinates, tokens, or credentials; a credential-rotation drill succeeds.

### Packet 2C — establish the measurement baseline

**Status: READY now and repeated at every canary.**

**Goal:** measure regressions during the migration, not only after it.

1. Replace handwritten API counters with Prometheus counters/histograms.
2. Instrument Caddy/tile-origin traffic because direct `/tiles/*` requests do
   not pass through FastAPI.
3. Measure source download/decode, render stages, tile bytes/count, publish
   lag, forecast horizon, queue wait, scratch, object/catalog operations,
   cache result, origin bandwidth, and HTTP duration.
4. Add external synthetic checks for manifest, one known real PNG, forecast,
   basemap style, glyph, sprite, and vector tile.
5. Propagate privacy-safe request/trace IDs without coordinates.
6. Add SLO recording rules, burn-rate alerts, and release markers.
7. Capture the current single-PVC/single-serving-pod capacity baseline. Repeat
   it after render-once, shadow writing, stateless reads, and every scale step.

**Pass:** dashboards answer whether data is fresh, publication is keeping up,
the CDN is helping, a resource is saturated, and a release changed the result.
A deliberately stale test page reaches a human and its recovery is recorded.

### Packet 3 — build a replay gate that covers every worker release

**Status: READY after Packet 1; blocks every new worker-source release.**

**Goal:** an incompatible Temporal Workflow can never be published by any
supported build or retag path.

Start from the ideas in local commit `4159503505d7de1944bb88f4a4cb270fe87052c1`,
but treat that commit as rejected, not merge-ready. Preserve its local clone
until replacement work is pushed.

1. Add the replay unittest inside `temporal/Dockerfile` after source copy and
   `PYTHONPATH`, before `CMD`. This gates GitHub, Gitea, and the manual image
   builder on the exact contents being shipped.
2. Remove `temporal-worker` from both generic retag workflows. If emergency
   retagging remains, it must execute the embedded replay test inside `latest`
   and reject older images that do not contain the gate.
3. Disable anonymous private-registry publishing outside this repository and
   restrict release credentials to protected CI.
4. Replace one shallow fixture per Workflow with immutable
   `<workflow>/<release>-<scenario>.json` fixtures.
5. Add sanitized success, partial, ActivityError, signal, timer, geometry
   fanout, push, and continue-as-new histories for MRMS, HRRR, AQM,
   PollAlerts, and WatchStorm.
6. Generate older fixtures from released images with synthetic inputs. Never
   copy production histories.
7. Independently discover decorated Workflow classes and compare discovery
   with the canonical registry, schedules, API routes, isolated roles, and
   legacy all-workflow role.
8. Retain Register/Delete token Workflows for compatibility even while public
   push routes remain disabled.

**Pass:** every image-publishing route fails closed on replay failure; multiple
versions/scenarios replay; registry omission and wrong-role tests fail when
intentionally perturbed; exact worker image builds.

**Rollback:** this packet changes release safety, not production behavior.
Revert only if it blocks all releases and the failure is proven to be in the
gate; never bypass it to ship an un-replayed Workflow.

### Packet 4 — merge and deploy observe-only schedule supervision

**Status: BLOCKED by Packet 3.**

**Goal:** workers observe and report Schedule stalls but never automatically
trigger, update, delete, recreate, terminate, or purge production work.

Use draft Radar #46 as the starting point. Rebase it after Packet 3. Preserve:

- semantic no-op Schedule reconciliation;
- current pause, note, limited-action, and remaining-action state;
- bounded retry of NOT_FOUND races;
- poller-first startup after Temporal namespace validation;
- safe error labels with no raw payloads or coordinates;
- background reconciliation failure isolation;
- critical logs with schedule, queue, next timer, and overdue duration;
- the documented SDK 1.30 update/CAS limitation.

Run the focused schedule/worker tests, full backend and Temporal suite, Ruff,
format, compile, exact image build, and replay gate. Obtain a new independent
review of the final rebased SHA.

Release one immutable worker artifact and update all six WorkerDeployments
together. Keep schedules on legacy `radar-ng`, keep legacy as the sole
seeder/observer, and keep all five role pools at `SKIP_SCHEDULE_SEED=1`.

**Pass:** all six run the same reviewed artifact; restart/HA tests perform no
no-op Schedule updates; natural actions continue; critical logs contain useful
fields but no secrets; DLQ count does not grow during the soak.

**Rollback:** Git-revert all six image refs together to v1.1.27. Do not restore
the destructive watchdog behavior as an improvised repair.

### Packet 5 — cut schedules to isolated role queues

**Status: BLOCKED by Packet 4 deployment and soak.**

**Goal:** CPU/memory failure in one ingest role cannot block the others.

This supersedes the stale canonical-plan instruction that handed seeding to
`aux`. `my-apps/development/radar-ng/RUNBOOK.md` wins for operations. Legacy
remains the only Schedule seeder and observer during this phase.

Expected isolated mapping, which must be re-derived from current code before
the change:

| Queue | Scheduled work |
|---|---|
| `radar-ng-mrms` | `ingest-mrms-base`, `ingest-mrms-composite` |
| `radar-ng-nowcast` | `nowcast` |
| `radar-ng-hrrr` | `ingest-hrrr` |
| `radar-ng-aux` | `ingest-airquality`, `ingest-lightning`, `ingest-tropical`, `tile-cleanup`, and the Open-Meteo orchestration Workflows |
| `radar-ng-alerts` | `poll-alerts`; also the unscheduled/API-driven WatchStorm work |
| `radar-ng-open-meteo` | Open-Meteo sync activities, not their Schedule-started orchestration Workflows |
| `radar-ng` | legacy all-Workflow/all-activity compatibility and draining |

WorkerDeployment names are `radar-ng-worker`, `radar-ng-worker-mrms`,
`radar-ng-worker-nowcast`, `radar-ng-worker-hrrr`, `radar-ng-worker-aux`, and
`radar-ng-worker-alerts`.

1. Inventory every Schedule and every producer/consumer, including
   Open-Meteo, tile-server Workflow routes, watch/lightning, and alerts.
2. Prove workflow and activity pollers exist on every destination queue.
3. Prove node CPU, memory, and PVC mount headroom during old/new overlap.
4. Change only legacy
   `USE_ISOLATED_TASK_QUEUES: "0"` to `"1"` through a Talos PR.
5. Leave `SKIP_SCHEDULE_SEED=1` on the five isolated pools.
6. Keep public Workflow routes disabled. Before later enabling alert routes,
   point tile-server's alerts client to `radar-ng-alerts` in a separate
   rollout.
7. Verify every Schedule's actual queue, then wait for one natural action per
   role.
8. Keep the legacy poller until every pinned legacy execution is understood
   and drained.
9. Soak for seven days while watching queue wait, slot use, OOM, schedule lag,
   publish lag, and data freshness.

**Pass:** a deliberately delayed nowcast does not delay MRMS; every role
continues natural actions; MRMS never crosses the stale page; no zero-poller
window occurs.

**Rollback:** first prove legacy pollers are healthy, then flip the one routing
flag back and let role-queue executions drain. Never point work at a queue
before its poller is visible.

### Packet 6 — finish render-once and canary it safely

**Status: READY for exact-head review; rollout waits for a quiet baseline.**

**Goal:** render each physical field once, publish scientifically correct
indexed PNGs, and retain an honest legacy rollback.

Start at the clean local head `695dc4628f017bb0c3120f5c7c421b5f60105771`
in the worktree documented above. Do not delete or reset it. Have an
independent agent review that exact commit. If clean, update draft Radar #41
and rerun all CI.

The rollout has two artifacts and an order:

1. Publish and deploy the compatible tile/API reader first. It must read both
   legacy timestamp-addressed frames and optional schema-v2 `grid_key`.
2. Keep every writer on `TILE_RENDERER=legacy`.
3. Prove the reader against old and new contract fixtures.
4. Select exactly one role, beginning with MRMS, using
   `TILE_RENDERER=indexed` plus its required canary-role setting.
5. Ensure every poller for that role runs the same image/settings; drain old
   pollers before resuming.
6. Verify marker identity, renderer algorithm, palette/nodata semantics,
   checksums, PNG decode/transparency, tile set completeness, render time,
   RSS, manifest integrity, and public serving.
7. Observe at least one full retention/prune cycle.
8. Promote one role at a time only after the prior role passes.

Make API-reader-first and writer-canary separate releases with separate
rollback points, even if the source PR contains both compatible code paths.

**Pass:** MRMS render stays under 10 seconds, nowcast under 90 seconds, cache
and RSS remain bounded, and no advertised pyramid is empty, partial, mixed, or
undecodable.

**Rollback:** drain the canary role, return all its pollers to legacy, prove
replacement pollers, then resume. Keep complete indexed winners immutable.
For reader rollback, first restore the legacy writer and wait for a
timestamp-addressed manifest.

### Packet 7 — prove the wired Longhorn tier before using it

**Status: READY only after Packet 0 identifies the trusted nodes.**

**Goal:** make replicated RWO storage a tested option for small authoritative
databases without touching live data.

The `longhorn-wired-ha` StorageClass is merged but dormant. It requires the
Longhorn node tag `wired-storage`. The earlier audit found no common node tag.
The HP Elite desired-state work has since been committed on Talos main; refresh
the exact commit and current dirty paths rather than repeating the old
uncommitted-work warning.

1. Name the trustworthy wired nodes in the task packet; a model must not choose
   them implicitly.
2. Add the common node tag through Omni's
   `node.longhorn.io/default-node-tags` path. Preserve per-disk hardware tags;
   do not invent a common disk tag and do not remove the class selector.
3. Verify eligible nodes have truthful, distinct Kubernetes topology zones.
4. Verify live Longhorn Node objects carry the tag.
5. Create a disposable canary PVC using `longhorn-wired-ha`.
6. Write and checksum test data; verify two replicas land on distinct eligible
   nodes/zones and reliable disks.
7. Exercise a controlled detach/reattach, one replica rebuild, and an isolated
   restore.
8. Verify filesystem integrity and measured RTO.
9. Remove the disposable canary through Git after recording results.

**Pass:** scheduling, attach, rebuild, restore, and checksum gates pass without
using unreliable micro nodes. V1 engine only.

**Stop:** never migrate Temporal or create the Radar catalog if tag placement,
replica anti-affinity, backup freshness, or rebuild proof fails.

### Packet 7A — protect the current shared Temporal database

**Status: BLOCKED by Packet 7; schedule as separate platform maintenance.**

**Goal:** remove the current one-replica Longhorn risk while the dedicated
Radar Temporal cluster is still future work.

The live claim is `temporal-postgres-data` in namespace `temporal`. Resolve and
record its exact PV, Longhorn volume, healthy replica, current SnapshotPolicy,
latest successful Kopiur snapshot ID/recovery point, and replacement claim
name before editing. Never restore in place.

1. Confirm the Kopiur repository is healthy and take/verify a fresh PostgreSQL
   CHECKPOINT-backed snapshot.
2. Create a distinct restore-before-bind PVC on proven
   `longhorn-wired-ha`, with a distinct Restore resource and two verified
   replicas.
3. Choose a maintenance window. Quiesce Temporal services through Git so no
   process can write while the database claim changes.
4. Restore and validate the new filesystem/database before pointing Temporal
   at it.
5. Change the Postgres Deployment claim through Git. Never run both database
   copies as writable instances.
6. Verify `pg_isready`, writable primary state, Temporal DB-backed Workflow and
   Schedule queries, exact DLQ inventory, all service health, natural Radar and
   other-application Schedules, then a new successful Kopiur backup.
7. Preserve the old PVC, PV, Longhorn replica, and backup until the rollback
   window closes.

**Pass:** the shared Temporal server survives a controlled Postgres pod/node
event on two replicas, all applications resume natural timers, and a new
restore point is usable.

**Rollback:** quiesce Temporal again, switch the Deployment back to the old
claim through Git, wait for Argo, and repeat all DB/Temporal/application
checks. Never switch storage under a running database.

### Packet 8 — introduce storage contracts with no behavior change

**Status: BLOCKED by Packet 6 merge.**

**Goal:** detach pipeline logic from PVC paths before moving data.

Land this after Packet 6 so it wraps the final publication boundary instead of
refactoring moving code.

Inventory every filesystem dependency before defining interfaces: tile trees
and cleanup walkers, `manifest.json` and its lock, grid binaries/metadata,
processed sets, nowcast status, storm/lightning/tropical JSON, alert snapshots,
push-token SQLite, storm-watch reads, prefetch `stat()` calls, inspect,
nowcast, wind-field, and health disk-usage checks. The packet is incomplete if
an API or serving pod still needs an undeclared path.

1. Add typed `TileStore`, `GridStore`, `CatalogStore`, and `StateStore`
   protocols.
2. Add local filesystem adapters that preserve today's paths and behavior.
3. Make source, transform, render, validation, and publication services
   callable without Temporal.
4. Keep Temporal activities as thin wrappers.
5. Define typed models for source identity, grid identity, renderer policy,
   publication epoch, catalog revision, frame status, and attribution.
6. Add contract tests that every adapter must pass, including idempotency,
   compare-and-set, list/pagination, checksum, cancellation, and partial
   failure.
7. Add one settings object and structured low-cardinality metrics.
8. Bound render scratch with `emptyDir` size, ephemeral-storage requests and
   limits, startup cleanup, and eviction alerts.

**Pass:** all existing production behavior and manifests are byte/semantic
equivalent under local adapters; no deployment or PVC changes.

**Rollback:** revert the code PR. Because no data moved, there is no storage
rollback.

### Packet 9 — provision the Radar object and catalog foundations

**Status: BLOCKED by Packet 7; code consumers wait for Packet 8.**

**Goal:** create unused, recoverable infrastructure before any dual write.

Use separate PRs for object IAM and the catalog database when practical.

Object store:

- dedicated Radar bucket, credentials, quota, and lifecycle;
- never reuse the Kopiur bucket;
- private cluster access only;
- ExternalSecret-managed least-privilege credentials;
- abandoned staging-key expiry, with live object deletion owned by catalog GC;
- load test alongside backup traffic because RustFS shares a NAS failure
  domain.

Catalog:

- separate plain Postgres from Temporal persistence;
- restore-before-bind PVC on the proven `longhorn-wired-ha` class;
- initial size around 10 GiB, adjusted from measured data;
- namespace Kopiur label, per-PVC stub, hourly schedule, correct data-owner
  mover UID/GID, exporter, probes, and app-owned VPA;
- schema migrations as repo-owned files and Argo hook Jobs, never inline YAML;
- transactionally stored publications, role/source epochs, object refs,
  outbox, source state, alerts, and push-token metadata.

**Pass:** no application traffic uses either service; S3 CRUD/checksum works;
Postgres migrations are repeatable; a non-empty Kopiur backup and an isolated
restore drill both pass.

**Rollback:** remove unused consumers/credentials through Git. Preserve backup
evidence; never delete the only restore source during testing.

### Packet 10 — shadow-write objects and build the catalog/outbox

**Status: BLOCKED by Packets 8 and 9.**

**Goal:** prove the new data plane without changing reads.

Freeze an object-key contract before writing production shadow data. The
initial v1 layout is:

```text
staging/v1/<publisher>/<attempt>/...
tiles/v1/<layer>/<source-run>/<valid-time>/<source-digest>/<renderer-policy>/<palette>/<z>/<x>/<y>.png
grids/v1/<layer>/<source-run>/<valid-time>/<grid-id>/<content-digest>.bin
manifests/v1/<monotonic-revision>.json
manifests/current.json
```

Use path-safe stable IDs and compact UTC timestamps. `source-digest`,
`renderer-policy`, and palette identity bind content/semantics so an upstream
correction or algorithm change cannot overwrite an older object. The current
pointer contains the revision and manifest checksum and may move only forward.

Start the catalog with explicit migrations for `source_runs`, `frames`,
`tile_sets`, `objects`, `publication_epochs`, `layer_heads`,
`manifest_revisions`, `outbox`, and `gc_candidates`. Schema names may improve
during the design PR, but the transaction/fencing relationships may not be
weakened.

1. Keep local publication authoritative.
2. Shadow-upload immutable tiles and retained grids under deterministic
   run/frame IDs with completion metadata.
3. Compare source identity, object count, path set, size, checksum, and
   representative decoded pixels with local output.
4. In one catalog transaction, verify the active per-source/role publication
   epoch, insert frame/object refs, allocate a monotonic revision, and append an
   outbox row.
5. Make an idempotent reconciler write
   `manifest/<revision>.json` and advance the current pointer only forward.
6. Keep bucket lifecycle limited to abandoned staging. Catalog-driven GC
   removes unreferenced live objects only after a grace period longer than
   every client/CDN cache.
7. Add an object-to-filesystem rehydration tool and test it before local writes
   are ever stopped.
8. Inject failures after upload, after DB commit, during snapshot write, during
   rehydration, and during GC. Prove repair and no backward pointer movement.
9. Benchmark small-object PUT/GET during Kopiur traffic.
10. Run at least seven days of parity before changing a reader.

**Pass:** every local publication has one matching object/catalog snapshot;
outbox repair converges; no leaked staging growth; shadow failure never blocks
the current local publish.

**Rollback:** disable shadow writes with the reviewed flag. Keep objects and
catalog for investigation; do not mass-delete during rollback.

### Packet 11 — switch to stateless serving

**Status: BLOCKED by Packet 10 parity.**

**Goal:** serving replicas can run on different nodes and do not require Radar
tile/grid PVCs.

1. Add an object/catalog reader behind a feature flag.
2. Give each serving pod a bounded last-good manifest and tile cache.
3. Configure Cloudflare immutable caching for content-addressed tile/object
   paths; measure HIT/MISS and home-uplink traffic.
4. Run two or more tile/API replicas with RollingUpdate, topology spread,
   required cross-node anti-affinity, a valid PDB, non-root security context,
   probes, VPA, and no tile/grid PVC mounts.
5. Canary reads, then gradually switch production.
6. Pause the catalog or object store and prove honest stale behavior. Warm
   clients should keep last-good data; cold-client limitations must be stated.
7. Keep old local PVCs and dual writes intact for at least seven clean days.

**Pass:** killing one serving pod or node does not blank maps; warm origin p95
is under 250 ms, public cold p95 under 800 ms, manifest p95 under 500 ms, and
ingest freshness is unchanged.

**Rollback:** switch the reader flag to the local origin through Git or
rehydrate from objects when explicitly tested. Do not delete old PVCs until a
rollback drill and retention window pass.

### Packet 12 — add safe worker replicas and backlog-based scaling

**Status: BLOCKED by authoritative catalog/object publication.**

**Goal:** a worker/node loss does not make observations stale.

Do this only after object publication is idempotent and catalog commits are
fenced.

1. Prove each activity can retry concurrently without corrupting state.
2. Remove shared RWO tile/grid coupling.
3. Add a second spread poller to MRMS and alerts first.
4. Use Temporal schedule-to-start/backlog and measured memory per activity for
   scaling. Do not scale only on CPU.
5. Bound per-role activity slots, memory, ephemeral storage, and render
   concurrency.
6. Add topology spread/anti-affinity and voluntary-disruption protection that
   does not block drains.
7. Kill one worker and one node during controlled tests.

Open-Meteo remains one `Recreate` pod on its RWO PVC until immutable model
snapshots and a separately benchmarked reader design exist.

**Pass:** another poller completes work inside the MRMS stale budget, no
duplicate publication wins, and backlog returns to baseline.

**Rollback:** reduce replicas through Git while leaving one proven poller per
queue. Never scale a queue to zero while a Schedule targets it.

### Packet 13 — rehearse the logical namespace migration

**Status: BLOCKED by Packet 12 and role-scoped publication fencing.**

**Goal:** practice Temporal migration on the shared control plane before
moving to a dedicated server.

1. Add role-scoped Schedule seed/pause/resume tooling. The current all-Schedule
   seeder cannot safely migrate one role at a time.
2. Use per-source/role publication epochs. One global epoch cannot safely
   support a role-by-role cutover.
3. Create logical Temporal namespace `radar-ng` on the current server with an
   initial 72-hour retention. Raise toward seven days only after measuring
   history and payload growth.
4. Replay retained histories, start destination pollers, and inventory
   long-lived WatchStorm/lightning executions.
5. Migrate one simple role first using the same fence/pause/drain/natural-run
   sequence required for the dedicated cluster.

**Pass:** the rehearsal produces no double publication, missed catch-up, or
unrecoverable Workflow, and rollback to `default` is tested.

### Packet 14 — build and migrate to dedicated Radar Temporal

**Status: BLOCKED by Packet 13.**

**Goal:** keep Temporal, use it fully, and remove Radar from the one-shard
shared control-plane failure domain.

Target:

- Kubernetes namespace `radar-temporal`;
- logical Temporal namespace `radar-ng`;
- a new persistence database initialized with exactly 32 immutable history
  shards;
- three spread replicas each for frontend, history, matching, and
  internal-worker where home-lab capacity permits;
- one UI/admin replica;
- separate plain Postgres, initially around 30 GiB, on a new proven
  two-replica Longhorn V1 PVC with Kopiur backup;
- advanced visibility without Elasticsearch or archival until measured need;
- no-surge, maxUnavailable=1 service rollouts;
- internal-only services, least-privilege credentials, metrics, alerts, and
  explicit resource budgets;
- three spread CoreDNS replicas through the Talos/Omni-owned path;
- a new Radar-specific Temporal `Connection`. Never repoint shared
  `Connection/cluster-temporal`, because other applications use it.

Migration:

1. Provision the new cluster with no Radar producers.
2. Prove DB backup and restore, service restart, DNS failure response, and DLQ
   monitoring.
3. Replay all retained Workflow histories on the destination worker image.
4. Inventory every Schedule, API client, Open-Meteo activity client, and
   long-lived watch/lightning execution.
5. Start destination pollers before any producer moves.
6. For each role: pause old Schedules, drain/inventory current runs, allocate a
   new role epoch that fences old writers, seed only the destination group,
   prove natural actions and catalog/object publication, then soak.
7. Suggested order is alerts, HRRR, nowcast, MRMS, then auxiliary publishers
   individually. Move destructive cleanup/GC and singleton outbox/Schedule
   management last.
8. Move tile-server and Open-Meteo clients only after their destination queues
   exist.
9. Keep old Temporal persistence and configuration intact through the rollback
   window.

**Pass:** restart destination Temporal and Postgres during a controlled test;
serving remains healthy, no duplicate catalog commit occurs, and Schedules
resume inside catch-up windows.

**Boundary:** this improves application control-plane availability, but the
cluster still has one Talos control-plane/etcd node and shared home power/WAN.
Do not call the whole service highly available.

**Rollback:** pause destination production, drain new writers, allocate a new
role epoch that fences them, prove old connection/pollers, then resume the old
role. Both clusters must never publish with the same valid epoch.

### Packet 15 — complete the public mobile/API contract

**Status: FUTURE; Packet 2 supplies its client foundation.**

**Goal:** every client surface uses one truthful Radar contract and public
upstreams do not scale linearly with phones.

1. Add a cached Radar backend endpoint for NWS alerts with coarse-cache policy,
   attribution, lifecycle validation, and abuse limits.
2. Proxy/cache search and reverse geocoding or explicitly document provider
   policy, identification, and quota.
3. Move Watch and CarPlay weather overlays/alerts onto Radar NG. Native system
   basemaps are allowed; a second radar data provider is not.
4. Wire playback speed, units, and map-mode settings end to end or remove them.
5. Project wind particles once per update, stabilize camera ownership, and
   stop wind, polling, playback, and prefetch within five seconds of background
   or unfocus.
6. Lazy-mount expensive mini-map/native map surfaces.
7. Add frontend contract fixtures and keep TypeScript, lint, unit, integration,
   offline, accessibility, and privacy checks required in CI.
8. Keep push/Workflow routes disabled until identity, quotas, key rotation,
   encrypted token storage, deletion/audit, durable deduplicated delivery, and
   abuse tests exist.
9. For long-lived Workflows, keep pinned builds and explicit patch/version
   markers. Use automatic upgrade only for replay-proven short scheduled
   Workflows.

**Pass:** one contract supplies app, Watch, and CarPlay; cached stale data is
honest; provider traffic is bounded; no exact coordinates or tokens enter
telemetry/logs.

### Packet 16 — keep basemaps portable and finish device performance

**Status: DEFERRED by user for the current backend push.**

**Goal:** prioritize Radar while retaining a reusable homelab map service.

- Keep the shared `maps.vanillax.me` VersaTiles profile in this homelab.
- Keep bundled Protomaps/PMTiles and bring-your-own style support in Radar.
- Never merge dynamic Radar rendering into VersaTiles.
- Do not remove the old Radar basemap Deployment/PVC until the deferred device
  rollback gate passes.
- Keep `CAROUSEL_WINDOW=1` until a supported iPhone and mid-range Android each
  complete 20 playback loops with zero blanks/crashes, at least 95% no-request
  warm transitions, p95 frame under 18 ms, p99 under 50 ms, no sample over
  100 ms, and less than 100 MiB memory growth.
- Test rapid scrub, palette/style/server changes, corrupt cache, malformed
  manifest, and background/foreground.

After the gate, enable five slots gradually. Only then may this homelab remove
its duplicate bundled basemap through GitOps. Bundled support remains in the
product repository.

### Packet 17 — observability, security, capacity, and failure proof

**Status: FUTURE; add instrumentation alongside earlier packets.**

**Goal:** replace architectural confidence with measured limits.

Observability:

- client-visible freshness, not only Workflow completion;
- source/download latency, render stages, publish lag, queue wait, slot use,
  object/cache results, catalog/outbox lag, and HTTP latency;
- low-cardinality labels only; no frame IDs, coordinates, tokens, or unbounded
  URLs;
- alerts routed to a human for stale MRMS/HRRR, zero pollers, Schedule overdue,
  timer DLQ writes, persistence errors, object/catalog failures, PVC health,
  and cache collapse.

Security:

- dedicated service accounts and ExternalSecrets;
- S3 and Postgres private to the cluster;
- NetworkPolicies for workers, API, object, catalog, and Temporal;
- non-root read-only containers where possible;
- route-specific request limits, body/concurrency caps, and trusted-proxy
  handling at the edge;
- credential rotation and revoked-token drills;
- an independent off-NAS backup before claiming site-level recovery, because
  RustFS and Kopiur currently share TrueNAS.

Capacity/failure matrix:

- 100 then 250 concurrent users, cold and warm cache;
- several regions, zooms, palettes, layers, and full playback loops;
- manifest, tiles, styles, glyphs, sprites, forecast, search, and alerts;
- load during MRMS/nowcast publication;
- NOAA/NWS delay/404, worker OOM, pod/node loss, CoreDNS disruption;
- Temporal/Postgres restart, object/NAS pause, home-uplink degradation;
- cache-hit ratio, origin RPS, uplink bandwidth, battery, RSS, and publish lag.

Publish exact hardware, dataset, image digests, cache state, first saturated
resource, recovery time, and failed scenarios in
`docs/capacity-acceptance.md`.

**Pass:** the SLO table in the canonical Radar plan holds without degrading
ingest freshness, backups restore, and every injected failure has a tested
rollback or an honestly documented limitation.

### Packet 18 — release and final definition of done

**Status: FUTURE.**

Radar is ready for friends when:

- a new install works with bundled maps and this homelab can select shared
  VersaTiles without code changes;
- users can distinguish live, stale, offline, and unavailable everywhere;
- MRMS and HRRR freshness pages a human and natural actions recover without
  manual triggering;
- each queue has a bounded worker pool and a tested rollback;
- every advertised tile exists, decodes, and belongs to one complete
  publication;
- one serving or worker pod/node loss does not blank last-good maps;
- restore drills for the catalog and Temporal persistence pass;
- public upstream traffic, logs, and telemetry respect privacy and quotas;
- supported devices pass playback, memory, background, and poor-network gates;
- capacity and failure results state what this hardware can honestly support.

The flagship architecture is done when, in addition:

- dynamic tiles/grids live in the dedicated Radar object bucket;
- authoritative metadata lives in the separate Radar catalog;
- API/tile serving is stateless and spread;
- replicated workers publish idempotently with role-scoped epoch fencing;
- Radar runs on the dedicated 32-shard Temporal control plane;
- old tile/grid PVCs and old Temporal persistence are retired only after
  rollback windows and backups;
- the documented 99.5% home-lab target is measured. Do not claim 99.9% until
  NAS/object, WAN/power, and the single Talos control-plane failure domains are
  removed.

## Plan status

- Phase 0, stop bleeding: merged and live; keep the observation window.
- Phase 1, per-role pools: deployed; queue cutover deliberately not done.
- Open-Meteo unified image: merged/live at v1.1.9; natural-sync soak remains.
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

Then execute Packet 0 and only the first unblocked packet. Close the current
Open-Meteo/worker soak, fix/review replay, fix/review alert freshness,
independently review/push render-once, and only then return to the observe-only
image and isolated queue cutover. PR #2183 is already merged; do not try to
merge it again.

## Mink references

- `projects/talos-argocd-proxmox/radar-ng-end-to-end-execution-plan-and-handoff-2026-09-02.md`
- `resources/temporal-postgres-and-radar-hrrr-recovery-completed-2026-09-02.md`
- `resources/temporal-postgres-outage-2026-09-02-the-hp-elite-node-19216810172-stopped-k.md`
- `resources/temporal-backup-completion-time-is-not-the-recovery-point.md`
- `resources/longhorn-wired-ha-contract-for-radar-and-temporal-use-the-opt-in-longhorn-wired.md`
- `resources/radar-open-meteo-unified-image-gitops-rollout-contract.md`
- `resources/radar-render-once-publication-and-durability-contract.md`
- `resources/radar-temporal-replay-safety-implementation-contract.md`
- `resources/radar-mobile-nws-alert-freshness-implementation.md`
- `projects/talos-argocd-proxmox/radar-ng-dedicated-temporal-and-storage-blueprint.md`

## Repository sources for verification

- Talos: `CLAUDE.md`
- Talos: `my-apps/CLAUDE.md`
- Talos: `my-apps/development/radar-ng/RUNBOOK.md`
- Talos: `my-apps/development/temporal/README.md`
- Talos: `docs/domains/storage/storage-tiers.md`
- Talos: `docs/domains/storage/kopiur-backup-architecture.md`
- Talos: `infrastructure/storage/longhorn/storageclass-wired-ha.yaml`
- Radar: `docs/reliability-and-scale-plan.md`
- Radar: `docs/radar-north-star.md`
- Radar: `docs/releasing.md`
- Radar: `temporal/task_queues.py`
- Radar: `temporal/schedules/seed.py`
- Radar: `temporal/worker.py`

The north-star document's COG/Zarr on-demand idea is future research. The
indexed pre-rendered PNG plus RustFS path in this execution plan is the
approved v1 delivery architecture.
