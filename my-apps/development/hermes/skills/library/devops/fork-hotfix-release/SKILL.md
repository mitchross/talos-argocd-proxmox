---
name: fork-hotfix-release
description: Use when a homelab app built from a fork breaks.
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [homelab, gitops, hotfix, ghcr, redlib]
    related_skills: [homelab-ops, github]
---

# Fork hotfix release (homelab apps on user forks)

Applies to apps where the user maintains a fork (e.g. `mitchross/redlib`), CI builds `ghcr.io/mitchross/<app>`, and the deployment lives in `mitchross/talos-argocd-proxmox` pinned as `image: ghcr.io/mitchross/<app>:<ver>@sha256:<digest>`. Goal: diagnose, verify the fix live, ship a hotfix release + digest-pinned GitOps PR.

## When to Use
A deployed app built from a `mitchross/*` fork shows errors in prod (upstream API change, provider block, regression) and the user asks to fix it. Also applies when the repo builds a **third-party** fork at a pinned commit (an in-repo `Dockerfile` + `VERSION` + init-container tag): fork it to `mitchross/<app>`, port fixes onto a branch there, then pin the new commit and bump `VERSION` and the image tag together.

## Preferences
- **Fix forward**, never propose rollback unless forward is impossible. Hotfix routine for these forks: version bump folded into the fix PR → merge when CI green → tag → infra PR. The infra repo is PR-only; do not merge it unless asked.
- **Fix, don't file.** When the user asks to fix a broken app, dig to the root cause and ship the fix PR. Do not offer "open an issue" as the next step.
- **Don't react too soon.** After a restart or rollout, wait out startup churn (Frigate/go2rtc takes ~25–30 min to settle) and re-check before proposing a change. The user prefers a second look over a premature PR.
- **Write PRs, READMEs and commit messages in plain, short English.** Shape: *What was wrong* (the failure loop as 3–5 numbered steps), *What this changes* (a few bullets, credit upstream authors), *After merging* (checkbox list of what to verify), *To undo*. Leave out evidence dumps, log excerpts, test transcripts and stacked qualifiers; one number that proves the point beats five. Run the `humanizer` skill's patterns over the text before posting.

## Procedure

1. **Read the live failure first.** Rule out external causes with one cheap check each before blaming code: provider-side metrics (e.g. Google Cloud console → API → Metrics → *Traffic by response code*; no 429s means not quota) and a one-variable A/B change (e.g. one camera CPU vs GPU encode). Count *per-device* operations from logs (new sessions vs renewals) to find which unit is looping.
    `kubectl get deploy,pod -A -o wide | grep -i <app>` then `kubectl logs -n <ns> deploy/<app> --tail=400 | grep -v '<noisy line>' | sort | uniq -c | sort -rn`. Get the upstream status code / body type (e.g. HTML 403 vs JSON), not just the rendered error page.
    For history beyond the current container (previous pod, before/after a change, node kernel logs), query Loki in-cluster: `curl -sG -H 'X-Scope-OrgID: 1' http://loki-read.loki-stack.svc:3100/loki/api/v1/query --data-urlencode 'query=sum by (cam) (count_over_time({k8s_namespace_name="<ns>",k8s_container_name="<c>"} |= "<msg>" | regexp "<re>(?P<cam>[a-z-]+)" [5m]))' --data-urlencode time=<unix>`. Labels are `k8s_namespace_name`, `k8s_container_name`, `k8s_pod_name`, `host_name` (node kernel/Talos logs); without the tenant header Loki answers `no org id`. Bucket counts per 5 min to tell startup churn from a steady loop.
2. **Reproduce in-cluster** against the Service (`curl http://<svc>.<ns>.svc.cluster.local:<port><path>`) across several routes to see which class of route fails (listings vs threads, etc.).
3. **Survey upstream before writing code.** `gh api repos/<upstream>/compare/main...<fork>:main` (ahead/behind), recent upstream commits on `src/`, and **open issues + open PRs sorted by updated** (`gh search issues --repo <upstream> <keywords> --sort updated`, `gh search prs --repo <upstream> <keyword>`), plus a web search for the symptom. Read the latest issue comments: a merged upstream fix may already be reported as broken, and the working fix may be an open PR, often one of several competing PRs for the same bug. Then grep the pinned revision's source for which of those fixes it already contains, so you port only what is missing. *Why:* the user's bug is rarely unique, and tested community patches beat new recovery logic.
4. **Verify the candidate fix live from the cluster egress IP before shipping.** Replay the app's exact auth flow + headers against the real upstream service and confirm the new request path returns 200 with real data, and the old one fails. Use `curl_cffi` with `impersonate="chrome"` in a scratch venv — plain curl/requests get TLS-fingerprint-blocked and give false negatives. See `references/redlib-reddit-api.md` for the Reddit probe recipe and `references/frigate-nest-go2rtc.md` for the Frigate + Nest go2rtc build, failure loop and checks. *Why:* a fix that matches upstream's commit can already be dead on the provider side; skipping this costs a full release + deploy cycle.
5. **Port onto a branch of the fork.** `git remote add upstream …; git fetch upstream pull/<n>/head:prN` then cherry-pick to keep authorship. Expect divergence: fork-specific templates and types (e.g. fork's `CLIENT` is `ArcSwap` → `CLIENT.load().post(...)`). Resolve conflicts keeping the fork's behaviour.
   - **Choose the base deliberately.** For a pinned *third-party* fork whose own added logic is implicated in the failure, base the new `mitchross/<app>` branch on upstream `master` and stack the open upstream PRs, instead of patching the fork. Show the result with `gh api repos/<upstream>/compare/master...mitchross:<app>:<sha>` (ahead/behind, commit authors) in the PR.
   - **Build and test locally when you can.** If the pod lacks the toolchain, download the official one into `$TMPDIR` (Go: go.dev/dl tarball matching the Dockerfile's version, with `GOPATH`/`GOCACHE` under `$TMPDIR`), run the patched packages' tests and a build that prints `-version`. Otherwise CI is the compiler — say so.
   - A `-race` failure in a package you touched may be pre-existing upstream code exposed by a new test. Check whether the racing lines are in your diff before blocking; report it either way.
6. **Bump version in the same PR** (`Cargo.toml` + the package entry in `Cargo.lock`). Push, `gh pr create`, then `gh pr checks <n> --watch` (run in background if >10 min).
7. **Merge on green → tag.** Check first whether the user already merged (`gh pr view --json state,mergedBy`). Annotated tag on the merge commit: `git tag -a vX.Y.Z <merge_sha> -m …; git push origin vX.Y.Z`.
8. **Wait for the tag image build** (`gh run list --branch vX.Y.Z --workflow 'Build and Push to GHCR'`, `gh run watch --exit-status`), then get the multi-arch index digest anonymously:
   ```
   TOKEN=$(curl -s "https://ghcr.io/token?scope=repository:mitchross/<app>:pull" | jq -r .token)
   curl -sI -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.oci.image.index.v1+json" https://ghcr.io/v2/mitchross/<app>/manifests/X.Y.Z | grep -i docker-content-digest
   ```
9. **Infra PR:** fresh branch from `origin/main` in a shallow clone, `sed` the `image:` line to `:X.Y.Z@sha256:<digest>`, commit, `git push -u`, then `gh pr create --head <branch>` (pass `--head`; a quiet push can leave gh thinking the branch is unpushed).
10. **After the user merges:** confirm the running pod's `imageID` equals the new digest and re-run step 2 against the Service. Report "deployed + verified" only after that; otherwise state what is unverified.
    - Judge health from the app's own per-unit stats (e.g. Frigate `/api/stats` → `camera_fps`, `reconnects_last_hour`, `connection_quality`), not from counting a log line. *Why:* a new build can change which message a failure logs, so a grep-based count drops to zero while a unit is still down.
    - For media proxies, inspect per-track bytes (go2rtc `/api/streams`: each receiver's `bytes` and `childs`) twice ~15 s apart. *Why:* a frozen video track hides behind a still-growing audio track and total `bytes_recv`.
    - If the pod was replaced unexpectedly, check the node before blaming the app: Ready `lastTransitionTime`, `FailedMount ... driver not found` / `TaintManagerEviction` events, and a `Linux version` boot line for that `host_name` in Loki. *Why:* a node reboot recreates the pod and looks like an app crash.
    - If a follow-up fix is needed, ship it as a new small PR on a fresh branch from `origin/main`.
    - Re-check hours later, not just at +30 min, and compare units against each other. *Why:* one pipeline can hold several independent failures (session loop, frozen track, adaptive resolution, timestamp bursts); fixing one exposes the next, often on only one unit and only under daytime load. Probe each unit's source directly (see the Frigate reference) instead of assuming the last fix regressed.

## Pitfalls
- Before restarting or replacing a background coding agent, check its worktree (`git status`, `git diff`) and any fork branch it pushed. *Why:* a pod restart kills the agent silently (empty output file) but leaves partial work you can finish instead of redoing.
- A required CI check can fail for reasons outside your PR (e.g. a Renovate chart bump already on main). Confirm the failing path is outside your diff and that main has the same change, then report it separately instead of "fixing" it in your PR.
- Don't declare a fix done because CI passed — CI proves it compiles, not that the provider accepts the request.
- Don't assume upstream's newest commit is the working fix; check issues updated after it.
- Report briefly: what broke (one line of mechanism), what shipped (PR/tag/digest), what the user must merge, what is still unverified.
