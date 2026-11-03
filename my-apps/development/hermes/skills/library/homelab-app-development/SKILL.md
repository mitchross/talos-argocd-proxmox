---
name: homelab-app-development
description: "Use when building features in Mitch's own apps."
version: 1.0.0
metadata:
  hermes:
    tags: [deal-scout, radar-ng, news-reader, features, llm, ui]
    related_skills: [claude-code, homelab-gitops-change-prs, diagnosing-bugs]
---

# Building features in Mitch's own apps

Applies to Mitch's self-hosted apps (deal-scout, radar-ng, news-reader and similar): features, UI bugs, LLM features. Coding goes to Claude Code via the `claude-code` hand-off recipe; this skill holds the product rules to put in the child's prompt.

## Procedure

1. Read the repo's AGENTS.md, README and dev docs, then the code you touch. Map the request onto existing endpoints and helpers first.
1b. **Place every feature as a first-time visitor would meet it, before building.** Write a one-line answer per feature to "which tab, which panel, visible to public or operator only?" and check that the tabs still make sense to someone who isn't Mitch. Features bolted onto one operator-only tab read as "I don't see anything" and later force an IA redesign. Mitch wants each app to work as a product for strangers, and in deal-scout an in-stock listing matters whether it's new today or a week old. When an AI or personal feature could be public, ask the access decision up front with options (public with per-visitor quota vs operator-only; user data in the browser vs on the server).
2. For a UI bug from a screenshot, trace each number on screen to the API field it comes from before you guess. Mismatched numbers usually mean two widgets read different endpoints or different rules.
3. Write the prompt with: verified cause or design, "reuse the existing pipeline, no second filter engine", the exact CI gates from docs, PR title, short plain PR body, never merge.
4. Dispatch in a worktree, report the PR link and gate results.
5. When Mitch asks to "add them all" from an idea list, group the features into a few PRs by code area (pricing, alerts, scraper, vision/UI), one child each, not one PR per idea and not one giant PR. Grouping by area keeps merge conflicts and review load down. Features that extend an unmerged feature go in a stacked PR on that branch.
6. For LLM features, run a live test on real data before you report. Mocked-Outbound tests don't prove the real model's JSON, its latency, or the real results. Recipe (deal-scout):
   - Build the PR's binary (`cargo build -p deal-scout-dashboard`; first build exceeds the 600 s foreground cap, so run it in the background).
   - Start it in scratch: `DATA_DIR=<scratch> INGEST_TOKEN=dev-token DEAL_SCOUT_DEFAULT_MODE=operator PORT=38200 DIGEST_LLM_URL=http://vllm-service.vllm.svc.cluster.local:8080/v1/chat/completions LITELLM_API_KEY=none target/debug/deal-scout-dashboard`. The direct vLLM endpoint needs no key; `/v1/models` lists the live id. Production traffic still goes through LiteLLM.
   - Load real rows with a read-only GET (`https://deals.vanillax.me/api/listings?since_days=30&limit=2000`) and POST them to the local `/api/ingest` with the dev token. Never write to the live API.
   - Fire the user's own example questions several times. Record `curl -w '%{time_total}'` for each, and read the results, not only the shape. Cross-check one filter against `/api/listings?view=table&...` to tell a parse bug from a data bug. Expect Ask to return fewer rows than Find for the same filters (Ask keeps only STEAL/BUY/MAYBE; Find also counts Skip/Unknown), so compare zero vs non-zero, not exact totals.
   - Kill the local server by its PID when done. One day of ingested data can't show trends, so say that the trend line is untested.
7. **When a live test sends a PR back for fixes, mark it draft first** (`gh pr ready <n> --undo`) and say "don't merge yet". Mitch merges green PRs fast, and a merge before the fixes land ships the slow or buggy version and strands the fix child on a merged branch.
8. **After Mitch says "merged", verify live before reporting.** Check which PR merged (`gh pr view <n> --json state,mergedAt`), then the app's `/api/version`, pod images, and restart counts with `lastState.terminated.reason`. Argo can take ~5 min to pick up a talos bump, so wait one reconcile cycle before calling it stuck. A new release can OOM at startup: check it, and size the limit with `homelab-gitops-change-prs` `references/restart-and-job-triage.md` §5.
9. **With every deploy report, say where each feature lives in the UI.** Give one table: feature | tab or panel | what to type or click, and mark the operator-only ones. Mitch looks for new features right after a deploy, and "it's live" alone gets "I don't see anything". When he says he can't see them, go through this in order:
   - Is the release live? Check `/api/version` against the newest bump PR.
   - Is he in operator mode? Read `applyMode()` in `app.js` for which tabs and blocks public mode hides. When the public bar lacks the operator tabs, he's in public mode. If he's off-LAN, or browser Secure DNS skips Technitium, he's on the public route through Cloudflare.
   - Is his browser serving a stale page? Have him hard-refresh.
   - Grep `index.html` for the feature's element id to point at the exact label.
   Name pieces releases don't update, such as the desktop `fb-agent` runner, and give the rebuild command (`git pull && docker compose build fb-agent && docker compose up -d fb-agent`).
10. **Test public vs operator mode through the external gateway explicitly.** From the Hermes pod, the app's public hostname reaches the internal (operator) route, so a plain `curl https://<app>.vanillax.me` looks like an operator-only leak when it isn't. Pin each gateway with `curl --resolve <host>:443:$(kubectl -n gateway get svc cilium-gateway-gateway-external -o jsonpath='{.spec.clusterIP}') -k ...`, then the same with `gateway-internal-technitium`. Expect 404/403 or empty operator lists on external, and data on internal.

## LLM features (standing rules)

- Use only the local Qwen on vLLM through LiteLLM (model id currently `qwen3.8-27b`; check `talos-argocd-proxmox/my-apps/ai/README.md` for the live id). No DeepSeek, no `auto` router, no cloud model — Mitch wants it free and local.
- Enforce it in code: a config var with the Qwen default and a guard that refuses non-`qwen` model ids, falling back to the non-AI path. A config typo should never silently route to a paid model.
- Reuse the app's existing LLM client and env (`DIGEST_LLM_URL`, `LITELLM_API_KEY` in deal-scout) so no cluster change is needed.
- Split the work: LLM parses the question into strict JSON filters, validated against known catalogs; code runs the query and computes trends; LLM only narrates the given facts. Drop narrated sentences citing numbers not in the facts.
- Always ship a deterministic fallback (keyword parse, plain facts summary) so the feature works when vLLM is down or busy.
- Rate-limit every GPU-costly endpoint so public visitors cannot swamp the GPU. The default is operator-only. Mitch may choose public access with a per-visitor daily quota (deal-scout: about 20 AI calls/day through `ratelimit.rs`). In that case, show the remaining quota in the UI and switch to the deterministic fallback when the quota runs out or vLLM is busy.
- Keep the call fast (cap tokens, disable thinking only via the mechanism the repo already uses — deal-scout's assist.rs sends `chat_template_kwargs: {enable_thinking: false}`; don't guess request fields). The app must never feel slow or janky.
- Give the parse schema every filter dimension the app's own search UI has (deal-scout: track, fit, tiers, price, RAM, capacity, source), and drop parsed keywords that equal a track or fit id/label. A missing dimension makes the model put the word into a title keyword ("etcd"), which matches nothing while the Find tab shows matches.
- Widen a parsed filter that empties the results, and say so. When the parse narrows to one tier ("steals" → STEAL only) or adds a title keyword for a property another filter already covers ("plp" with fit=etcd), and that gives 0 rows, rerun without it and label the answer ("no steals right now; here are the best buys"). A narrow parse that returns nothing looks to the user like the AI is broken, while Find shows matches.
- Never block results on an LLM call. vLLM is shared, so one call ranges from seconds to over a minute. Put a hard ~5 s timeout on the parse step (fall back to the keyword parse) and return the rows and trend at once. Make narration a second request the UI calls after rendering, with a ~20 s timeout and the plain-facts fallback. Put this split in the first prompt, not a fix round.

## Explaining an app's AI to Mitch

When he asks how a feature's AI works, he means the stack, not the product flow. Answer in stack terms: language and framework (or "none, no LangChain, no Python"), HTTP path (client → LiteLLM → vLLM → model), where the prompts live and how they're built, structured-output method, sampling settings, timeouts, fallbacks, and what isn't used (RAG, embeddings, tools, agent loop). Read the client code (`assist.rs`, the prompt builders) first, and don't describe it from memory. Lead with a boxes-and-arrows HTML diagram (`::preview`): AI calls get an accent border, plain code a normal border, fallbacks a dashed border on a side branch. A numbered prose walkthrough got "no i mean in ai terms" and then "boxes and arrows please".

## deal-scout specifics

- Facebook scraping runs on Mitch's desktop runner with his own login. Never let public visitors trigger FB scrapes (account ban risk); visitor location features use stored data and the in-cluster geocoder (`geocoder-api.geocoder.svc:8000`).
- FB Marketplace `deliveryMethod` is `local_pick_up` or `shipping` (omit for both). Search-result payloads can omit SHIPPING, so trust the filtered URL.
- vLLM `qwen3.8-27b` accepts one image per prompt, so photo-reading features are possible. Run them in a background queue, never on the request path.
- The first Ask after a deploy can hit the ~5 s parse timeout while vLLM warms up, and it falls back to keywords. Re-run it once before you call the parse broken.
- When several feature branches run in parallel, tell each child which shared files (route table, index.html, today.js, find.js, the `state` object in state.js) others are editing and to keep its edits there additive. Parallel branches that each add a field to the one-line `state` literal conflict on every merge; the fix is to keep both fields.
- When a deal-scout PR makes a POST endpoint public, also add it to the `deal-scout-public` HTTPRoute allowlist in talos (`my-apps/personal-projects/deal-scout/httproute.yaml`); the external gateway only passes listed POST paths, so the feature works on LAN and 404s for everyone else. Test step 10 catches it.
- Let title negations override feed specs. Retailer feeds (e.g. lowcostminipcs) report RAM/storage for barebones units whose titles say "NO RAM NO STORAGE", so spec filters match listings with no RAM. Normalize this in one place in the classifier, with a test that uses the real title.

## In-app diagnostics (radar-ng and similar)

- Keep per-frame UI-thread code (Reanimated `'worklet'`, Skia frame callbacks) self-contained inside `frontend/`: no call into a shared web module, even one marked `'worklet'`, and no per-call array or closure allocation. Keep app and web in step with a Jest parity test over the same inputs. A cross-module worklet call passes every JS gate and the bundle export, then aborts the app on device (SIGABRT, `throwPendingError` in `worklets::WorkletRuntime`) when that layer turns on.

- Keep diagnostics counters in one module and change them only through functions that bump a version and notify subscribers. Read them in the UI with `useSyncExternalStore`, whose snapshot is that version. A direct `stats.x++` from another file never repaints Settings, so the line shows stale zeros while the feature works.
- Make the snapshot current on mount, so a Settings screen opened after the work shows real counts. Derive "currently held" counts (frames on disk) from the real index, not from increments, so eviction lowers them. Reset them when the feature is switched off.
- Add tests that fail on a direct mutation: a hook re-renders after an engine write, a late mount shows current counts, and clearing resets.

## Redesigns: plan with Opus, build with Sonnet

For a whole-area UX rethink, load `references/plan-then-parallel-build.md` with `skill_view`: decisions via one `clarify` call, one Opus planning run with shared contracts and file ownership, parallel Sonnet builders, stacked-PR repair after a squash merge, live check, and the "how the AI works" doc.

## Running several feature agents

Full recipe (dispatch, merge order, release bumps, conflict resolution): `references/parallel-feature-agents.md`. Always-on rules:

- Max 4–5 children at once; push each branch as soon as it has commits.
- Mark dependent PRs draft until their base merges; expect out-of-order merges anyway and re-check every open PR after each "merged".
- `gh pr merge` is denied for you; give Mitch the paste-ready merge loop from the reference.
- Check a bump PR's tag contains the latest merge before telling him to merge it; close stale bumps.
- On "merged", confirm `gh pr view --json state` is `MERGED` before you act, because his merge command may still be waiting on CI. Rebase a stacked PR onto master after its base squash-merges with the take-theirs-then-reapply-own-diff recipe in the reference.

- Name shared helpers (model guard, geocoder client, schema migrations) and their owning branch in every child's prompt, or each child writes its own copy.

## Filter and count UI

- Counts on filter chips must be faceted: each facet's count applies every active filter except its own dimension. Compute them in the same server pass that returns the filtered rows, not from a global dashboard summary — otherwise a pill says "1" and opens "0 listings".
- Count every chip row with the same inclusion rules (e.g. hidden/skip rows excluded in both), or the rows disagree with each other.
- Show a 0 count when facets are loaded, so an empty filter is visibly empty.
