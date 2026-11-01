# Batteries-included deliverables: in-repo k8s manifests and fork-friendly identity

Recipes for the two code-heavy issues of a docs overhaul. Both must leave the owner's own
deployment and builds byte-for-byte unchanged while making a fork work with zero edits to code.

## In-repo Kubernetes manifests (from the owner's GitOps repo)

1. Source from the live GitOps manifests (read-only clone, `git pull` first). Keep the runtime
   contract exactly: image digests the cluster runs, probe paths/ports, UIDs/fsGroup, mount paths,
   sidecar layout (a sync sidecar lets RWO volumes work).
2. Shape: `deploy/kubernetes/base/` (plain Deployments, Services, PVCs **without**
   `storageClassName`, env files with a clearly marked placeholder for any required contact/UA) +
   `components/` as Kustomize `kind: Component` (dev datastore, ingress, gateway-api, monitoring,
   operator CRs, autoscaling) + `examples/minimal` (base + dev datastore, one `kubectl apply -k`) and
   `examples/production`.
3. Strip: personal hosts (use `example.com`), ExternalSecrets/secret-manager refs, PriorityClass,
   storage-class names, owner namespaces, LAN IPs. Then grep for them to prove it:
   `grep -rn -i -E '<owner-domain>|externalsecret|priorityClass|longhorn|nfs|192\.168' deploy/kubernetes`.
4. Ship `validate.sh`: `kubectl kustomize` every example and every component-on-base, pipe to
   `kubeconform -strict -summary` with the default schemas plus the datree CRD catalog
   (`-schema-location default -schema-location 'https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json'`).
   kubeconform is a single static binary: download the release tarball to a scratch `bin/`, verify
   its sha256. Add a CI workflow running it on `deploy/kubernetes/**`, pinning actions the same way
   the repo's other workflows do.
5. PR body: file tree, kept-vs-stripped list, object counts per render, and an explicit "not run on
   a live cluster" line with the smoke test for the owner's machine
   (`kind create cluster && kubectl apply -k deploy/kubernetes/examples/minimal`).
6. Update every doc that said "manifests live elsewhere" (self-host page, getting-started path,
   deploy README, docs index); the GitOps repo becomes "the owner's production example".

## Compose that works on the first try

1. **Prebuilt images by default**, pinned by tag@digest with an env override per image
   (`${RADAR_API_IMAGE:-ghcr.io/…:vX@sha256:…}`). Local builds go in a `docker-compose.build.yml`
   override (`build:` + `pull_policy: build`). Use the same pins as the in-repo k8s base and note that
   both get bumped together on release.
2. **Check the published architectures** before promising prebuilt images. Fetch the manifest from GHCR
   (an anonymous token from `https://ghcr.io/token?scope=repository:<owner>/<img>:pull`, Accept the
   OCI index and manifest types). If it is a single manifest, read `.config` to get os/arch. If it's
   amd64-only, the entrypoint must refuse arm64 and point to `--build`, and the docs must say so.
3. Confirm the per-role images share an ENTRYPOINT and differ only in `CMD` (read the Dockerfile
   targets) before swapping one local image for several published ones; Compose's `command:` then
   drives the role.
4. **Reuse one bootstrap script** for Compose and the k8s init container (e.g. the newest-basemap
   resolver). Mount it read-only into a digest-pinned alpine and run it with `sh <script>` so the
   executable bit doesn't matter. Add an optional pin override (`PMTILES_URL`) and include it in the
   skip-marker key. Keep the old one-shot service names as safe no-ops so older instructions still work.
5. **One entrypoint** (`deploy/up.sh [--build]`). Order: check docker/compose/curl → refuse arm64
   without `--build` → create `.env` → refuse a placeholder contact → bootstrap (idempotent) →
   `up -d` → poll `/livez`, then `/health` with timeouts → print app URLs per client. Each failure
   names the troubleshooting section.
6. **Validate offline:** the standalone Compose v2 binary runs `config -q` without a daemon. Run it for
   every combination of base, build override and each profile; check `config --images` and an
   image-override env. Pass `--env-file .env.example` instead of copying it to `.env` and deleting it
   afterwards: the copy/delete pair gets the command flagged for approval. Run shellcheck on the
   scripts. A live `up` still runs on the owner's machine.
7. **Run the bootstrap script for real** in the pod with a tiny bbox (a city, ~5 MB) and `OUT` in
   scratch. If the pod lacks busybox `wget`, put a small curl-backed `wget` stand-in (handles `-q`,
   `-O`, `--spider`, `-T`) first on `PATH` for the test only. Exercise four paths: fresh (finds
   today's build, checksum passes, marker written), re-run (marker skip), pinned URL (used, recorded
   in the marker) and an expired pin (fails with a 404 and leaves the existing file intact). Put the
   results in the PR.
8. **Shell heredoc pitfall:** inside an unquoted `<<EOF` heredoc, an apostrophe in a
   `${var:-default}` default (`${ip:-<this-computer's-IP>}`) is parsed as an unterminated quote and
   breaks the script. Set the fallback in a plain assignment before the heredoc, using a placeholder
   with no quotes. shellcheck catches this, so run it before committing any entrypoint script.

## Live verification on the test bed (issue for the owner's desktop agent)

1. Issue body for an agent, not a human: which branch (or `master` once merged), preflight tool
   versions and free disk, the repo skills to load, "never commit `.env` or edited settings files".
2. One numbered section per path (prebuilt Compose, `--build` Compose, kind/k3d), each a checkbox list
   with the exact commands and what to **record**: basemap/bootstrap size and duration, time from
   "API up" to first frame, local build time and peak RAM, re-run idempotence, `doctor` summary,
   cleanup (delete the test cluster, confirm kubectl points back at the real context).
3. Report section: pass/fail table with timings, every error with command + log lines + fix, fixes
   in a PR that `Refs` the issue, and **replace every size/timing claim in the docs with the measured
   number**. Link the issue under the tracking epic; close the epic only after its fixes merge.
4. Reviewing the returned PR: re-check each new claim against the code (e.g. a zoom cap is safe only
   if the bundled styles' source `maxzoom` matches), note side effects such as a changed skip-marker
   key forcing one re-download on every existing install, and open a separate issue (with the likely
   cause) for anything the run left unexplained rather than holding the PR.

## Fork-friendly identity (app bundle IDs, team IDs, default URLs, image owner)

1. One module (e.g. `frontend/identity.js`) holds every personal value; each reads an env var and
   falls back to the upstream value. The app config, widget/extension configs and build/QA scripts
   read it (`node -p "require('./identity').bundleId"` in shell scripts).
2. Native code that can't read env (Swift/Kotlin constants): a sync script rewrites them from the
   module, with a `--check` mode wired into the test suite so drift fails tests. Upstream the sync
   must be a no-op.
3. CI image owner: `ghcr.io/${GITHUB_REPOSITORY_OWNER,,}/…` (lowercase is required by GHCR) keeps
   upstream names unchanged.
4. **Prove the owner's build is unchanged**: resolve the config on the base commit and on the branch
   with env unset and diff. For Expo: clone base into a scratch dir, symlink the branch's
   `node_modules`, run `npx expo config --type public --json` in both, compare with
   `python3 -m json.tool --sort-keys`. Repeat for every build variant flag (e.g. `RADAR_CARPLAY=1`).
   Zero diff lines is the gate; put the result in the PR.
5. When moving a value out of `app.json` into the config function, tests that call the config
   function with a minimal hand-built config now see the injected value; update their expectations
   to import it from the identity module rather than hard-coding.
6. Grep the repo (excluding archive/node_modules/build dirs) for remaining owner identifiers and
   account for every file in a PR table: configured, synced copy, test fixture, simulator-only, or
   prose. Simulator-only test-host IDs and fixtures asserting upstream defaults can stay.
7. `FORKING.md` at the root, simple language: identity env table (with upstream values) → server
   URL → run native sync → server-side contact → images automatic → **native rebuild required**
   (a JS reload isn't enough), plus a "before you fork" paraphrase of the repo's third-party-terms
   doc. Link it from the README and docs index.
8. Native builds (Xcode/Gradle) can't run in the agent pod; say the native build on the owner's Mac
   is the remaining check before a release.
