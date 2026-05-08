# Renovate Self-Hosted CronJob Diagnosis — 2026-05-08

User report: dashboard issue [#1266](https://github.com/mitchross/talos-argocd-proxmox/issues/1266) checkboxes "do nothing", lots of errors, slow runs.

## 1. Diagnosis

The repo run aborts with `external-host-error` **before the `update` phase ever executes**. The dashboard issue is parsed (`DEBUG: findIssue(Dependency Dashboard)` → `Found issue 1266`, log line 921) but no PRs are created or rebased and the issue body is never re-rendered, so checkmarks the user toggles persist visually but get processed by nothing.

Hard evidence from `kubectl logs -n renovate renovate-29637890-g5wsl`:

- Line 3239: `Repository result: external-host-error, status: onboarded, enabled: true, onboarded: true`
- Line 3248: `"splits": {"init": 11018, "onboarding": 0, "extract": 5517, "lookup": 0, "update": 0}` — `lookup` and `update` both `0 ms`. The lookup phase aborted at the first `AggregateError`, and the `update` phase (which is what acts on the dashboard) never runs.
- 26 occurrences of `TOOMANYREQUESTS` from `index.docker.io` against PAT user `mitchross09` in a single run.
- 30+ unique Docker Hub manifest GETs that returned HTTP 429 (`alpine`, `bitnami/kubectl`, `axllent/mailpit`, `kopia/kopia`, `qdrant/qdrant`, `temporalio/admin-tools`, `temporalio/server`, `temporalio/temporal-worker-controller`, `bitnamicharts/redis`, `library/alpine` digest, `cloudflare/cloudflared`, `copyparty/ac`, `dullage/flatnotes`, `vulnerables/web-dvwa`, `yanwk/comfyui-boot`, ...).

Run took **51 s** (`durationMs: 51739`) which is fast — the slowness the user perceives is the `*/5` cron interval plus the abort: a checkbox click sits unprocessed forever because every subsequent run also aborts in the same place.

The hostRules secret is present and the PAT itself works (verified: `curl -u mitchross09:dckr_pat_… https://auth.docker.io/token?...` returns a 2949-byte token). The auth IS being applied (`Adding password authentication for index.docker.io`, log lines confirming `matchHost: index.docker.io, username: mitchross09`). The `username: ""` / `password: ""` strings in error log dumps are `got`'s redacted option-object printout, not the wire credentials.

## 2. Root Causes

### Primary: Docker Hub authenticated free-tier PAT is still ratelimited under this workload

A free-tier authenticated PAT gets **200 image-pulls / 6 h** (Docker Hub published rate, body of every 429 confirms `pull rate limit as 'mitchross09'`). This repo references ~50 unique images on `index.docker.io` (`alpine`, `bitnami/*`, `bitnamicharts/redis`, `axllent/mailpit`, `qdrant/qdrant`, `kopia/kopia`, `cloudflare/cloudflared`, `temporalio/{server,admin-tools,temporal-worker-controller,temporal-worker-controller-crds}`, `posthog/*`, plus dozens more). Each lookup pulls list-manifest + digest + sometimes config, so a single full run easily makes 150-300 manifest GETs against Docker Hub. With the cron firing every 5 min, the bucket is permanently empty.

Once any AggregateError reaches the lookup pipeline, Renovate aborts the repo with `external-host-error` and **skips the entire `update` phase** — that's the phase that reads the dashboard issue body, detects newly-checked `[x]` boxes, rebases or recreates branches, and rewrites the issue. So every checkbox click is a no-op while this is broken.

### Contributing: cache PVC is `persistRepoData: false`, no docker datasource cache PVC

`my-apps/development/renovate/configmap.yaml:19` sets `"persistRepoData": false` and the CronJob spec uses `emptyDir` for `/tmp` (`cronjob.yaml:93-94`). Every run re-clones the repo and re-fetches every Docker manifest from scratch. A persistent cache would not eliminate the rate-limit problem but would dramatically reduce the per-run hit count after the first warm run.

### Not a cause (already handled correctly)

- The Gitea pagination customDatasource workaround (`renovate.json5:238-258`) is in place and the `enabled: false` mute on the `kubernetes` manager copy is working.
- The GitHub PAT works fine — the dashboard issue IS being read, it's just not being mutated because the run aborts first.
- `prHourlyLimit: 3` is intentional and not blocking checkbox processing.

## 3. Recommended Fix (manifest-only, no scripts)

Apply both, in priority order:

**A. Stop letting Docker Hub 429s abort the whole run.** Add a hostRule entry that tells Renovate to drop 429 errors from Docker Hub instead of bubbling them up. Inject via env so it stays alongside the PAT host_rules:

In `1Password://renovate-dockerhub.host_rules`, change the JSON value from:
```json
[{"matchHost":"index.docker.io","username":"mitchross09","password":"dckr_pat_..."}]
```
to:
```json
[{"matchHost":"index.docker.io","username":"mitchross09","password":"dckr_pat_...","abortOnError":false,"abortIgnoreStatusCodes":[429]}]
```

`abortIgnoreStatusCodes: [429]` is a documented Renovate hostRule field ([docs](https://docs.renovatebot.com/configuration-options/#hostrules)) that converts 429 into a soft failure for that host. Renovate flags affected packages in the dashboard "Package Lookup Failures" section and **continues to the update phase**, which is what processes dashboard checkboxes. Soonest the user clicks `[x]` next to a Helm/argocd/ghcr.io PR that doesn't depend on Docker Hub, the next run rebases it.

**B. Reduce Docker Hub burn rate** by adding to `.github/renovate.json5`:
```json5
{
  description: 'Reduce Docker Hub manifest fetches to live within free-tier 200/6h PAT limit',
  matchDatasources: ['docker'],
  matchPackagePatterns: ['^(library/)?[a-z0-9._-]+/[a-z0-9._-]+$'],
  matchPackagePrefixes: [''],
  // only check tag-list / digest once a day instead of every 5 min run
  schedule: ['after 02:00 and before 06:00 every day'],
}
```
plus consider switching the cron schedule from `*/5 * * * *` to `*/15 * * * *` (`my-apps/development/renovate/cronjob.yaml:11`) — checkbox responsiveness goes from "5-min worst case" to "15-min worst case", with 3x fewer manifest fetches per hour.

**C. Optional, future hardening:** Add a Renovate cache PVC (Longhorn RWO, `backup: "daily"` is overkill — `emptyDir` is fine, the PVC is just for speed) and set `persistRepoData: true`. This is documented in [Renovate self-hosted caching guide](https://docs.renovatebot.com/self-hosted-configuration/#cachedir). Do this after A+B prove the abort is fixed.

After applying A: the user clicks any `[x]` on the dashboard, waits one cron tick (`*/5`, ≤5 min), and Renovate will rebase/recreate the corresponding branch even though Docker Hub is still ratelimited for some packages. The "PR Edited (Blocked)" entries stay until rebase is requested via checkbox; that's correct Renovate behavior, not a bug.

## 4. User Impatience vs Real Bug

| Symptom | Verdict |
|---|---|
| Checkbox click does nothing immediately | **Expected** — Renovate only acts on next scheduled run (≤5 min). |
| Checkbox stays unchecked across 3+ runs | **Real bug** — confirmed today. Run aborts at lookup, never reaches dashboard-action phase. |
| "Slow" — runs taking minutes | **Misperception** — runs are 50 s. Slowness is the *5-min cron* combined with the abort silently dropping the user's input. |
| "Too many errors" | **Real bug** — 26+ TOOMANYREQUESTS / run, but they're a symptom of the rate-limit blowing the lookup phase, not separate bugs. |
| "PR Edited (Blocked)" list is long | **Expected** — those branches were force-pushed by the user/UI; Renovate refuses to overwrite without explicit checkbox consent. Listed correctly. |

## 5. Quick-Test Command

After updating the 1Password `renovate-dockerhub.host_rules` field, force a fresh run and verify the `update` phase actually runs:

```bash
# Force ExternalSecret refresh (1Password is on 1h TTL)
kubectl annotate externalsecret -n renovate renovate-secrets \
  force-sync="$(date +%s)" --overwrite

# Wait for secret to repopulate, then trigger a Job
kubectl create job -n renovate --from=cronjob/renovate renovate-manual-$(date +%s)

# Tail and look for split timings
kubectl logs -n renovate -l app.kubernetes.io/name=renovate -f --tail=-1 | \
  grep -E '"splits"|Repository result|Repository finished'
```

Success looks like `"lookup": <non-zero>, "update": <non-zero>` and `Repository result: done` (instead of `external-host-error`). Then on the dashboard, click one `[x]` (e.g. the simple ghcr.io tubesync v0.17.3 entry that's already checked), wait ≤5 min, and verify either a new comment lands on issue #1266 or the corresponding `renovate/ghcr.io-meeb-tubesync-0.x` branch gets a fresh push.

---

Files cited:
- `/home/vanillax/programming/talos-argocd-proxmox/.github/renovate.json5`
- `/home/vanillax/programming/talos-argocd-proxmox/my-apps/development/renovate/configmap.yaml`
- `/home/vanillax/programming/talos-argocd-proxmox/my-apps/development/renovate/cronjob.yaml`
- `/home/vanillax/programming/talos-argocd-proxmox/my-apps/development/renovate/externalsecret.yaml`
- Renovate run log saved at `/tmp/renovate-g5wsl.log` (8338 lines, captured 2026-05-08 ~20:51 UTC)
