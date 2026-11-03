# Plan with Opus, build in parallel with Sonnet

Use when Mitch asks to rethink a whole app area ("step back and think about this as a user who isn't me", a tab/IA redesign, "AI on every page"). Proven on the deal-scout redesign v2: Home + Find, Ask everywhere, Lab analysis (PRs #162, #161, #163).

## 1. Decide before dispatching

- Read the existing UI modules, route table, mode handling (operator vs public) and any old `docs/redesign-proposal.md` first. Half the request may already exist (deal-scout already had inventory import, suggestions and a ratelimiter).
- Propose the redesign in a short numbered list, then ask only the decisions that change scope, with `clarify` in ONE call: public access to GPU features (rate limit vs operator-only), where other users' data lives (browser-only vs server), and how to ship (N PRs vs one vs issue first).
- Save the decisions with `hindsight_retain` before launching anything.

## 2. One Opus planning run (no code)

- Launcher runs `claude -p` with `--model opus --effort high`. It may only Read/Grep and Write one file: `/opt/data/cache/scratch/<app>-plan.md`.
- Prompt carries the user's words verbatim, the decisions, the product rules, and asks for: tab order per mode, per-PR goal / OWNED files / additive-only files / endpoints / state fields / tests, shared contracts, and merge order. Cap it near 250 lines.
- Shared contracts that made three parallel branches merge cleanly:
  - a DOM slot one PR creates and another fills (`<div id="askslot">`), with a fallback that inserts it if missing;
  - a function one PR exports and another calls through a namespace import with a fallback (`find.applyFindFilters ?? hash write`);
  - a backend helper one PR owns that a stacked PR uses (`ai_quota`).
- Takes about 15 minutes. Read the plan's branch names and section headings before writing builder prompts.

## 3. Sonnet builders

- One worktree per PR under `~/.local/share/agent-worktrees/<repo>/<task>/`, made by the parent before launch.
- All builders share one prompt template: "Build only PR X (section N) of <plan path>; follow section 2 contracts exactly; two other agents are building the rest now", the product rules, the four gates, push early, `gh pr create --base <base>`, never merge.
- A PR that depends on another starts from a launcher that waits for the base branch: `until git ls-remote --exit-code origin <base-branch>; do sleep 60; done`, then `git worktree add -b <branch> <path> origin/<base-branch>` and `--base <base-branch>`.
- Check `df -h /opt/data` first; three Rust worktrees plus old ones filled the disk mid-run.

## 4. Merge order and conflicts

- Even with contracts, two PRs editing the same import line in `app.js` conflict. Before handing out merge commands, test-merge the open branches in a throwaway worktree (`git worktree add --detach <scratch> origin/<b>`; `git merge --no-commit origin/<a>`), then `git merge --abort` and `git worktree remove`.
- Tell Mitch which PR merges first and why (e.g. B before A shows two Ask boxes on Home). After each "merged", re-merge master into the next branch, gate in the background, and say "pushed" only after `gh pr view --json mergeable` reads MERGEABLE.
- **Stacked PR after a squash merge.** When the base PR squash-merges, the stacked branch still holds the base's original commits, so merging master conflicts on files the stacked PR barely touched (add/add on new files). Fix without force-push:
  1. `gh pr edit <n> --base master`.
  2. Find the old base tip: `B=$(git merge-base HEAD <last-pushed-commit-of-base>)`.
  3. `git merge --no-commit origin/master`; for each conflicted file `git checkout --theirs -- <f>` and `git add <f>`.
  4. `git diff $B HEAD -- <conflicted files> > own.patch`; `git apply --3way own.patch`.
  5. Prove nothing was lost: `git diff --stat $B HEAD` must equal `git diff --cached --stat origin/master`, and the sorted `+/-` lines of both diffs must match. Then `cargo check`, full gates, commit, push.

## 5. Ship and explain

- Each merge cuts a release and opens a talos bump. Close stale bumps yourself with `gh pr close <n> -c "Superseded by a newer deal-scout bump."` when Mitch says "close the bad PRs"; merging stays his.
- Verify live as a public visitor through the external gateway: tab labels from `/`, `GET /api/ai/quota`, `/api/version`, pod images and restarts.
- Give a test query you have already run live, and name the ones that returned 0 and why.
- When he asks how the AI works, answer in AI-stack terms (framework or not, language, HTTP client, prompts, structured output, RAG or not), show the exact JSON the model sees, then offer boxes and arrows as an HTML `::preview` widget and a `docs/ai.md` PR with a Mermaid flowchart that GitHub renders. Verify every function name and env var in the doc against master before opening the PR.

## Pitfalls

- "merged" can arrive while his `gh pr checks --watch` is still waiting. Poll `gh pr view --json state` in a loop before acting; don't report it as failed.
- A child's summary can say "tests passed" when it only ran one crate because the disk was full. Read the PR body's gate lines.
- `gh pr merge` is denied for you even when he says "merge it yea"; give the command.
