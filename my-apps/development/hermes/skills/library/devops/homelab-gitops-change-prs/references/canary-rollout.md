# Running the old and new build side by side

Use this for any risky image swap: a language rewrite, a framework upgrade, a new server. The user expects Kubernetes to run both versions at once. Don't propose a big-bang image swap as the default.

## 0. Pick the shape
| Shape | When | Notes |
|---|---|---|
| **Beta stack** (default for this user) | Rewrites, anything the user wants to click around in first | Own namespace `<app>-beta`, own DB, own worker, own hostname `beta-<app>.vanillax.me`. Prod untouched until the user is happy. |
| Weighted canary in prod | Small upgrades where real-traffic error rates matter | See the Argo weight landmine in §3 before choosing it. |
| Temporal worker only | Worker swap with no UI | No route split. Use worker versioning (Progressive ramp + smoke gate). In-flight PINNED workflows finish on the old build. |

Asked to "run both", the user chose the beta stack with its own DB and hostname over an in-prod canary. Offer the beta stack first and mention the canary as the alternative.

## 1. Beta stack recipe
1. Copy the app dir to `my-apps/<category>/<app>-beta/`. Rewrite every `namespace:` and the kustomization `namespace:`. Keep object names, so in-namespace URLs like `http://<svc>:<port>` resolve to the beta Service.
2. Pin the new images by the release's `tag@digest` (see the image bump pitfall in SKILL.md). Leave the prod dir alone.
3. **Seed the DB from prod's backup instead of starting empty.** Use a kopiur `Restore` in the beta namespace with `source.fromPolicy: {name: <prod-policy>, namespace: <prod-ns>, offset: 0}`. Point the beta PVC's `dataSourceRef` at it, give the beta namespace the `kopiur.home-operations.com/repo: cluster-kopia` label, and keep the `../../common/kopiur-backup` component, which supplies the repository, populator and `onMissingSnapshot: Continue`. Check the prod policy has a recent snapshot first (`kubectl -n <prod-ns> get snapshot`). Config that lives only in the DB (search queries, thresholds) comes along with it. API re-ingest would lose price history, so prefer the restore.
4. Mark the beta PVC with the `backup-exempt: "true"` label and the fully-qualified `storage.vanillax.dev/backup-exempt-reason` annotation, and don't add a SnapshotPolicy. It is a disposable copy.
5. Temporal: give beta its own namespace. Add it to the `for NS in …` loop in `my-apps/development-infra/temporal/scripts/seed-namespaces.sh`, and set `temporalNamespace: <app>-beta` in the WorkerDeployment. Shared schedule IDs in one namespace would fight. The beta worker may restart until the seed job has run.
6. Route: LAN-only HTTPRoute on `gateway-internal-technitium` with the same header filters as prod's internal route. Say that making it public is one more route on `gateway-external`.
7. Reuse prod's 1Password items in new ExternalSecrets in the beta namespace.
8. Before writing the PR, list the duplicated side effects: outbound API quotas (scans run twice), alert or webhook env vars (leave them unset in beta), and desktop runners that only poll prod (beta's jobs for them stay unclaimed).
9. Validate: `kubectl kustomize` both dirs into one file, then run `validate-kopiur-coverage.py <file>` and `validate-vpa-policies.py <file>`. A partial render shows "stale exemption" errors for apps you didn't render; ignore those.
10. Tell the user not to merge the release's automatic prod bump PR until beta checks out.
11. The release workflow's bump PR rewrites only the prod dir. For every later release while beta exists, add a commit to that same bump PR that pins the beta dir to the same `tag@digest`s. Otherwise beta keeps testing the old build, or prod gets a fix that beta never had.

## 2. Weighted canary: check the app is safe to share
- Single writer on an RWO PVC (SQLite): put the new build in a **second container in the same pod**, mounting the same PVC, with a second Service selecting that pod via `targetPort: <named-port>`. A second pod can land on another node and hang in Multi-Attach, or block the old pod's next Recreate. SQLite in WAL mode handles two processes on one host.
- **Response caches** must be keyed on DB content (a version query per request), not invalidated only by the process's own writes.
- **Side effects on write** (alerts, digests, webhooks, warmers): route every write to ONE container, so nothing fires twice.
- **Schema init on start:** both must run the same idempotent migrations, and the new one must not add anything the old one can't read.
- Give the new container a different port (`PORT` env) and a named containerPort, and point its probes at that name.

## 3. Weighted route split (Gateway API, Cilium)
- **Argo landmine:** this repo's argocd-cm `ignoreDifferences` for `HTTPRoute` ignores `.spec.rules[].backendRefs[].weight`. Weight edits can sync "Succeeded" without ever reaching live. Check `infrastructure/controllers/argocd/values.yaml` first. Each ramp step then needs the user's manual server-side apply plus a live `kubectl get httproute -o yaml` check, or the ignore entry has to be narrowed in its own PR.
- Split only GET/HEAD: one rule with weighted `backendRefs` (old 90 / new 10). Weights are core Gateway API, and `weight: 0` sends nothing. Writes go to a catch-all rule with the old backend only.
- Forced-new rule for LAN testing: `method: GET` plus a `headers:` match. Precedence is path, then method, then the number of header matches, so the header rule must carry the method too.
- Copy the existing `RequestHeaderModifier` filters into every new rule, or the gateway-set mode header silently drops.
- `RequestMirror` is Extended conformance. Check Cilium's docs for the running version before you rely on it.

## 4. Ramp (canary) or promote (beta)
- Canary: 10 → 50 → 100 with one PR per step. Between steps, check Loki (`k8s_container_name="<new>"`) for errors and 5xx, plus restarts and memory against the limit. Rollback is setting the new weight to 0.
- Beta: once the user is happy, merge the prod bump PR (or a hand-written one from the same digests), then retire the beta dir in one PR:
  - Shrink the kustomization to `namespace.yaml` only, so the Application stays and everything else prunes.
  - Remove the beta namespace from the Temporal `seed-namespaces.sh` loop.
  - Revert any OOM stopgaps on prod (raised limit, allocator env vars) that the app fix made unnecessary.
  - Expect `static-risk` to BLOCK with `persistent-resource-disappears` on the beta PVC. That is the intended deletion of a disposable copy, so say so in the PR body and call the PR a one-way door for beta's data.
  - Seed jobs never delete, so the beta Temporal namespace and its schedules outlive the PR. Remove them by hand after merge, via the admintools pod: `temporal schedule list -n <ns>`, then `temporal schedule delete -n <ns> -s <id>` for each, then `temporal operator namespace delete -n <ns> --yes` (it prompts without `--yes`). Then open the follow-up PR that deletes the empty folder.
  - Right after the prune, Argo can show the beta app OutOfSync/Progressing on `WorkerDeployment` and `Connection` (`requiresPruning: true`). The worker controller is still deleting the server-side versions and its finalizers. It clears on its own within minutes, so wait before you touch anything, and wait before deleting the Temporal namespace, because the controller needs it for that cleanup. Hermes' RBAC can't read `temporal.io` CRs, so watch progress in the controller logs instead (`kubectl -n temporal-worker-controller logs <manager-pod> --since=15m | grep <ns>`: look for "finalizer removed") and with `temporal worker deployment list -n <ns>`. A later "unable to fetch Connection" error after the finalizer is removed is harmless.
- Either way, check one real run of every scheduled job before you remove the old build.
- **Check memory headroom before promoting.** A rewrite can idle at a very different RSS from the old build, even with the same cache budget. Compare `kubectl top pod --containers` for beta against prod's `limits.memory`, and load-test beta first. Under bursts of large responses, a glibc-based Rust/Tokio server holds freed memory and gets OOMKilled at a limit sized for the old process. As a stopgap, raise the limit (2× the observed peak) in its own PR. `MALLOC_ARENA_MAX=2` barely moves RSS, so don't promise it as a fix. The real fix goes in the app repo: tuned jemalloc plus a blocking-thread cap (see the `claude-code` skill's `references/language-port.md` §3). After it ships, lower the limit back and drop the stopgap env.

## 5. Benchmark old vs new
1. Run it in-cluster, service to service (`http://<svc>.<ns>.svc:<port>`), with `oha` (`gh release download -R hatoo/oha -p oha-linux-amd64`, into `/opt/data/tools/bin`). Use `-z <dur> -c <n> --no-tui --output-format json -H 'Accept-Encoding: gzip'`.
2. Before and after the run, curl `/api/version` on both targets. An auto bump PR the user merges mid-run silently turns "old vs new" into "new vs new". Discard rows taken after a swap.
3. Note each pod's node (`kubectl get pod -o wide`). Different hardware skews the numbers, so say which side it favours.
4. Parse oha's JSON defensively: `latencyPercentiles` values can be `null` (a failed or short run), so a parser that multiplies them crashes and drops that row. Compute rps as successful-count ÷ duration, and check the status-code distribution. oha's `requestsPerSec` can misreport, and 403s from operator-only endpoints look like fast successes (send the mode header the gateway would set).
5. Sample `kubectl top pod --containers` per step and watch `restartCount`/`lastState.terminated.reason` on both. A load test can OOM a live pod, so keep the heaviest endpoints at low concurrency against prod.
