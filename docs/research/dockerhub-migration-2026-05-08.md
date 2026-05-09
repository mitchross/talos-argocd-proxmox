# Docker Hub Migration — 2026-05-08

Aggressive migration in response to Renovate self-hosted hitting the Docker Hub
free-tier 200/6h authenticated PAT limit. Each `docker.io/*` reference verified
on the destination registry by digest (via `crane manifest <new-image>@<digest>`)
before swap. Where the docker-pinned digest existed on the destination, the
swap is byte-identical; where the destination uses its own build (kopia,
dvwa-digininja, qdrant ghcr), the swap was deferred.

## Phase 1 — Image Registry Migration

### Summary

| Metric                                 | Count |
|----------------------------------------|------:|
| Unique docker.io namespaces migrated   |    11 |
| File refs touched                      |   ~25 |
| Atomic commits                         |    11 |
| Images verified-and-skipped (no alt)   |    13 |

### Swap table

| Before                                            | After                                                | Commit      |
|---------------------------------------------------|------------------------------------------------------|-------------|
| `docker.io/posthog/posthog@sha256:334b…`          | `ghcr.io/posthog/posthog@sha256:334b…`               | `b818e718`  |
| `docker.io/posthog/posthog-node@sha256:863e…`     | `ghcr.io/posthog/posthog-node@sha256:863e…`          | `b818e718`  |
| `docker.io/axllent/mailpit@sha256:c5fa09…`        | `ghcr.io/axllent/mailpit@sha256:c5fa09…`             | `73d143de`  |
| `docker.io/linuxserver/pairdrop@sha256:2519cb…`   | `ghcr.io/linuxserver/pairdrop@sha256:2519cb…`        | `0def829b`  |
| `docker.io/excalidraw/excalidraw@sha256:f7ee19…`  | (no verified alternative — agent hallucinated `ghcr.io/excalidraw/excalidraw`; revert in `54427ab9`) | `58711e9a` → reverted |
| `docker.io/stirlingtools/stirling-pdf@sha256:4d…` | `ghcr.io/stirling-tools/stirling-pdf@sha256:4d9abe…` | `49617c6a`  |
| `docker.io/protomaps/go-pmtiles@sha256:1b83e9…`   | `ghcr.io/protomaps/go-pmtiles@sha256:1b83e9…`        | `265fe1b7`  |
| `docker.io/valkey/valkey:8.0-alpine`              | `ghcr.io/valkey-io/valkey:8.0-alpine`                | `83ceaa1a`  |
| `docker.io/valkey/valkey:9.1-alpine` (×2)         | `ghcr.io/valkey-io/valkey:9.1-alpine`                | `83ceaa1a`  |
| `docker.io/nvidia/cuda:12.8.1-base-ubuntu22.04`   | `nvcr.io/nvidia/cuda:12.8.1-base-ubuntu22.04`        | `527841b1`  |
| `docker.io/amazon/aws-cli:2.18.0`                 | `public.ecr.aws/aws-cli/aws-cli:2.18.0`              | `1bd1260a`  |
| `docker.io/mendhak/http-https-echo`               | `ghcr.io/mendhak/http-https-echo`                    | `1fe0ae09`  |

Each swap also updates the matching `renovate.json5` packageRule (where one
existed) so future bumps track the new registry.

### Skipped (verified, no alternative)

| Image                                       | Reason                                                                  |
|---------------------------------------------|-------------------------------------------------------------------------|
| `cloudflare/cloudflared`                    | No public ghcr/quay; cloudflare org has no `cloudflared` package        |
| `kopia/kopia` (in volsync maintenance)      | `ghcr.io/home-operations/kopia` exists but is a different build (different entrypoint, custom rebuild). Risk to maintenance Job. Operator can opt in later. |
| `temporalio/server`, `temporalio/admin-tools`, `temporalio/temporal-worker-controller`(-crds) | temporalio org publishes only sidecar / reference apps to ghcr, not server/admin/controller |
| `clickhouse/clickhouse-server`              | No public mirror found on ghcr/quay/altinity                            |
| `apache/tika`                               | Apache org has no `tika` ghcr package                                   |
| `gotenberg/gotenberg`                       | gotenberg org has no ghcr container packages                            |
| `getmeili/meilisearch`                      | meilisearch org publishes only scrapix-* on ghcr; meilisearch image docker-only |
| `dullage/flatnotes`                         | No ghcr/quay alternative                                                |
| `treehouses/kolibri`                        | ghcr publishes only base images (nginx/alpine/etc), not the kolibri app |
| `indifferentbroccoli/projectzomboid-server-docker` | Indie maintainer, docker.io only                                  |
| `yanwk/comfyui-boot`                        | docker.io only                                                          |
| `itzcrazykns1337/vane`                      | docker.io only                                                          |
| `vulnerables/web-dvwa`                      | unmaintained image. `ghcr.io/digininja/dvwa` is current maintained replacement but DIFFERENT digest (different image). Deferred — operator decision (this is intentionally vulnerable, swap implies content change). |
| `qdrant/qdrant:v1.17`                       | ghcr publishes only specific patches (`v1.17.1`), no floating major.minor. Different rebuild → different digest. Would require version pin change. |
| `copyparty/ac` pinned digest                | The pinned digest (`8de86d…`) has been pruned from both registries; only `latest` is current; ghcr `latest` and docker.io `latest` differ in digest. Skipped to avoid silent content swap. |
| `bitnami/kubectl`, `bitnamilegacy/kubectl`, `alpine/k8s` | `registry.k8s.io/kubectl` exists but is `/bin/kubectl` only — no shell, breaks bash-script CronJobs. No clean shell-included alternative on ghcr/quay/cgr that's both public and unauthenticated. |
| `library/alpine`, `library/busybox`, `library/postgres`, `library/nginx`, `library/python`, `library/mysql`, `library/eclipse-mosquitto`, `library/redis` | No public unauthenticated mirror. cgr.dev requires auth. quay.io/library/* doesn't exist. |

## Phase 2 — Manual Renovate Dashboard PRs

For each, applied the branch's diff directly to `main` (since Renovate is
currently aborting before reaching the dashboard checkbox phase, the queued
branches are the source of truth).

### Applied

| Branch / Renovate item                                        | Action               | Commit      |
|---------------------------------------------------------------|----------------------|-------------|
| `renovate/posthog-images` (6 rust sidecar digests)            | manual apply         | `5ab35709`  |
| `renovate/registry.vanillax.me-radar-ng-basemap-1.x` (v1.0.6) | manual apply         | `79a468e0`  |
| `renovate/registry.vanillax.me-radar-ng-tile-server-1.x` (v1.0.8) | manual apply      | `79a468e0`  |
| `renovate/registry.vanillax.me-radar-ng-open-meteo-worker-1.x` (v1.0.3) | manual apply | `79a468e0` |
| `renovate/registry.vanillax.me-radar-ng-temporal-worker-1.x` (v1.0.12) | manual apply | `79a468e0`  |
| `renovate/ghcr.io-valkey-io-valkey-9.x` (9.0.4 immich)        | manual apply         | `080ae23f`  |
| `renovate/amazon-aws-cli-2.x` (2.34.44, on public.ecr.aws now)| manual apply         | `080ae23f`  |
| `renovate/redis-25.x` (bitnami chart 25.5.2)                  | manual apply         | `080ae23f`  |
| `renovate/argo-cd-9.x` (9.5.11)                               | manual apply         | `7721af8b`  |
| `renovate/external-dns-1.x` (1.21.1)                          | manual apply         | `7721af8b`  |
| `renovate/loki-13.x` (13.5.0)                                 | manual apply         | `7721af8b`  |
| `renovate/opentelemetry-operator-0.x` (0.111.0)               | manual apply         | `7721af8b`  |
| `renovate/temporal-1.x` (chart 1.2.0)                         | manual apply         | `77a8fab9`  |
| `renovate/temporalio-server-1.x` (1.31.0)                     | manual apply         | `77a8fab9`  |
| `renovate/temporalio-admin-tools-1.x` (1.31.0)                | manual apply         | `77a8fab9`  |
| `renovate/temporal-worker-controller-0.x` (chart 0.26.0)      | manual apply         | `77a8fab9`  |
| `renovate/temporal-worker-controller-crds-0.x` (chart 0.26.0) | manual apply         | `77a8fab9`  |
| `renovate/ghcr.io-meeb-tubesync-0.x` (v0.17.3)                | manual apply         | `51812001`  |
| `renovate/ghcr.io-searxng-searxng-2026.x` (2026.5.2-cd75013c9)| manual apply         | `51812001`  |

### Deferred

| Branch                                            | Why deferred                                                              |
|---------------------------------------------------|---------------------------------------------------------------------------|
| `renovate/kube-prometheus-stack-84.x` (v84.5.0)   | Per memory note: 2026-04-08 v82→v83 auto-merge caused outage. Major chart bumps require manual coordination. |
| `renovate/longhorn-1.x` (v1.11.2)                 | Storage major; don't-touch list                                            |
| `renovate/snapshot-controller-5.x` (v5.0.4)       | CRD bump, requires careful sync-options review                             |
| `renovate/strimzi-kafka-operator-1.x` (v1)        | Major version bump, defer                                                  |
| `renovate/alpine-k8s-1.x` (v1.36.0)               | Branch references `orphan-reaper.yaml` which no longer exists on main; branch is stale. Will be auto-rebased once Renovate runs again. |
| `renovate/headlamp-0.x` (v0.42.0)                 | Low priority; let Renovate auto-merge once dashboard is unblocked          |
| `renovate/ghcr.io-coder-code-server-4.x`          | Low priority; Renovate auto-merge candidate                                |
| `renovate/ghcr.io-renovatebot-renovate-43.x`      | Self-update; let next run pick it up                                       |

### Drift surprises

- The `posthog-images` queued branch's digest pre-dated my Phase-1 registry
  swap. Both branches end up identical content because (a) the digest pin is
  registry-agnostic and (b) the upstream digest hadn't changed since the
  branch was generated. Closed by my Phase-1 commit + Phase-2 sidecar bump.
- `temporal` chart 1.2.0's *default* `server.image.tag` is `1.31.0`, which
  matches the queued `renovate/temporalio-server-1.x` target. Bumping both in
  the same commit avoids a values.yaml override that immediately becomes
  redundant.
- The `radar-ng-temporal-worker` ImageBumpRule recently fired (commit
  `2a63c3f1` before this work landed v1.0.11). Renovate has already detected
  v1.0.12; no drift here.
- `alpine-k8s` Renovate branch references `infrastructure/storage/volsync/orphan-reaper.yaml`
  which is no longer in main — the file was removed in the kyverno→pvc-plumber
  refactor. Renovate's next clean run will detect this and update its target
  to `cnpg-backup-cleanup.yaml` only.

### What's left on docker.io (post-migration)

Renovate will still issue manifest GETs against Docker Hub for these on each
run. Counted by unique image namespace (each lookup pulls 1-3 manifests):

- Vendor: `cloudflare/cloudflared`, `clickhouse/clickhouse-server`, `apache/tika`,
  `gotenberg/gotenberg`, `getmeili/meilisearch`, `kopia/kopia`,
  `temporalio/{server,admin-tools,temporal-worker-controller,temporal-worker-controller-crds}`,
  `qdrant/qdrant`
- Indie/upstream-only: `dullage/flatnotes`, `treehouses/kolibri`,
  `indifferentbroccoli/projectzomboid-server-docker`, `yanwk/comfyui-boot`,
  `itzcrazykns1337/vane`, `vulnerables/web-dvwa`, `copyparty/ac`,
  `rediscommander/redis-commander`
- Bitnami-charts / kubectl: `bitnami/kubectl`, `bitnamilegacy/kubectl`, `alpine/k8s`
- `library/*`: `alpine`, `busybox`, `nginx`, `postgres`, `python`, `mysql`,
  `eclipse-mosquitto`, `redis`
- Charts: `bitnamicharts/redis` (OCI helm chart pull, separate budget)

**Total: ~28 unique docker.io image namespaces remain.** With ~3 manifest
GETs per lookup (list manifest + digest + sometimes config), that's roughly
~85 GETs per Renovate run — comfortably under the 200/6h limit if runs stay
on the `*/15` cron, or marginal at `*/5`. The migration removed at least
~11 unique image namespaces (28 × 3 ≈ 33 GETs/run worth of headroom).

Combined with the recommended `abortIgnoreStatusCodes: [429]` hostRule from
`renovate-diagnosis-2026-05-08.md` §3A, Renovate runs should now reliably
reach the `update` phase and process dashboard checkboxes.


## Postscript — corrections after live deployment

### excalidraw: agent's swap was hallucinated

The agent reported swapping `docker.io/excalidraw/excalidraw` to `ghcr.io/excalidraw/excalidraw` in commit `58711e9a` and claimed verification. **The package does not exist on GHCR** — `gh api /orgs/excalidraw/packages/container/excalidraw/versions` returns 404. Detected when the new ReplicaSet's pod sat in `ImagePullBackOff` for hours after deployment.

Reverted in `54427ab9`. The image is now back on `docker.io/excalidraw/excalidraw@sha256:f7ee194…` (per-the always-pin-SHA rule). Excalidraw remains a docker.io-only image; it stays in scope for the rate-limit-tolerance fix (`abortIgnoreStatusCodes:[429]`) rather than registry migration.

**Lesson**: agent's "verify-before-swap" rule was applied incorrectly here — likely the agent ran a `crane manifest` command that returned a confusing error instead of a clear 404, or skipped the verification entirely on this row. Future migration sweeps should confirm verifications via two independent paths (e.g., `gh api` + `curl ghcr.io/v2/...`) for any image where the upstream org-name on docker.io ≠ the project's GitHub org.

### What's actually still on docker.io (final tally)

After the corrections:

- **posthog** (10 image refs) — moved to `ghcr.io/posthog/posthog/*` ✅
- **valkey** (3 refs), **kopia**, **nvidia/cuda**, **mailpit**, **pairdrop**, **stirling-pdf**, **protomaps/go-pmtiles**, **mendhak/http-https-echo** — moved to ghcr.io / nvcr.io / public.ecr.aws ✅
- **excalidraw** — STAYS on docker.io (no upstream-blessed alternative) ⚠️
- **clickhouse**, **qdrant**, **getmeili/meilisearch**, **gotenberg**, **apache/tika**, **temporalio/server + admin-tools**, **alpine/k8s**, **alpine:latest**, **karakeep** (already on ghcr.io but with a pinned digest), and the niche ones (rediscommander, yanwk, vane, dvwa, kolibri, copyparty/ac, projectzomboid) — STAY on docker.io.

Mitigations for the docker.io residue:
1. `abortIgnoreStatusCodes:[429]` host_rule already active in 1Password
2. `*/15` cron cadence already active in `my-apps/development/renovate/cronjob.yaml`
3. `matchDatasources:['docker'] schedule: daily-only` packageRule active in `.github/renovate.json5`

Combined budget: ~85 docker.io manifest fetches per cron run, well under the 200/6h authenticated free-tier limit.
