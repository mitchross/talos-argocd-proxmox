# Running several feature agents in parallel

Use when one request becomes several feature branches built at once by Claude Code children.

## Dispatch

- Model choice: Opus for root-cause bugs and the core feature others build on; Sonnet for spelled-out feature branches. If the user asks to switch models mid-run, check each worktree's `git status`. Restarting a child that has edited nothing loses nothing.
- Six parallel Claude Code agents (Opus + Sonnet) hit the Claude 5-hour usage limit in about 1.5 hours. Run at most 4–5 at once, and hold stacked follow-ups until their base is settled. Push each branch as soon as it has commits, so a limit or pod restart loses nothing. A limit-stopped run with an empty JSON output has no session id; relaunch it with a "check git status/log and continue" preamble. Resume details: `claude-code` skill, `references/language-port.md` §6.
- Name shared helpers in each child's prompt and say which branch owns them (Qwen-only model guard, geocoder client, schema migrations). Unprompted, parallel children each write their own copy, which conflicts on merge and leaves duplicate code to consolidate.
- **For a cross-cutting redesign (tabs, header, shared state), run one Opus planning-only child before any builder.** Restrict its tools to read-only commands plus `Write(<scratch>/plan.md)`, and give it Mitch's decisions verbatim. Ask it to produce, for each PR: the files it owns, its additive-only edits, endpoints with their JSON, and its state fields. Also have it fix the shared contracts: empty slot ids that one PR leaves for another, exported functions with signatures, and which Rust helper module owns what. Then paste the plan into each Sonnet builder's prompt. Builders that each redesign the same `index.html`, `app.js` and `state.js` without agreed contracts conflict on every merge.
  - Make each contract work in either merge order. The consumer imports the module as a namespace with a fallback (`import * as find from "./find.js"; (find.applyFindFilters ?? fallback)(nav)`), and inserts the slot itself if the other PR hasn't created it yet. Then each branch links, tests and runs on its own, and an out-of-order merge doesn't break master.
- **Launch a stacked child at the same time as its base, with a launcher that waits.** Have the launcher loop on `until git ls-remote --exit-code origin <base-branch> >/dev/null; do sleep 60; done`, then `git fetch` and `git worktree add -b <new> <path> origin/<base-branch>`, then start `claude` with `gh pr create --base <base-branch>`. That way you don't need to come back in a later turn to start it.
- Look for each child's PR with `gh pr list` as well as its `out-*.json`. The PR often exists while the JSON is still empty, because the child is still writing its final summary.
- Pass on any "behaviour change you didn't ask for" from a child's summary, for example a Qwen-only guard widened to every AI path.
- When a branch adds a Temporal schedule or workflow, check it yourself against `docs/temporal-safe-deployments.md`. Children often skip that doc. A new workflow type plus a schedule that follows the existing digest pattern is safe. Changing an existing workflow's code needs that doc's versioning rules.

## Disk

- Each deal-scout worktree's `target/` grows to 20-25 GB, so a handful of stale worktrees fills the Hermes PVC, and children's `cargo test` then fails on a full disk. After a batch merges, remove the merged worktrees with plain `git worktree remove <path>`, only when `status --porcelain` and `@{u}..HEAD` are both empty. Run it in the background, because `git status` over big `target/` dirs passes the foreground timeout. Check `df -h /opt/data` before you launch a new batch.

## Merge order

- **Enforce merge order with draft status, not words.** When two PRs rewrite the same feature code (the core feature and a follow-up on it), mark the later one draft (`gh pr ready <n> --undo`) until the first merges. Mitch merges whatever is green, often out of the order you gave, and a wrong-order merge turns every open PR `CONFLICTING`.
- Expect out-of-order merges anyway. After every "merged", run `gh pr list --json number,mergeable` and `git log origin/master`, find what actually landed, and fix every PR that now conflicts in that pass, not just the next one in your list.
- `gh pr merge` is hard-denied by Mitch's Hermes config; don't rephrase it. Hand him one paste-ready loop that waits for CI and stops on the first problem:
  ```bash
  for n in <a> <b> <c>; do
    gh pr checks $n -R <owner/repo> --watch --fail-fast || break
    gh pr merge $n -R <owner/repo> --squash || break
    sleep 20
  done
  ```
  Put the base/feature-core PR first, say "tell me the number where it stopped", and give a fresh loop with only the remaining PRs after each stop.
- **While a conflict fix is still gating, don't give the merge command. Say "wait for my *pushed*".** `gh pr checks --watch` reports the old head's green checks, so Mitch's merge fails with "merge commit cannot be cleanly created". After the push, confirm `MERGEABLE` and that the new head's checks have started, then hand over the command.
- **When sibling PRs finish, test them against each other, not just master:** `git merge-tree --write-tree --name-only origin/<a> origin/<b>`. Then name the order and say which one will need a conflict fix after the first merges. For trivial import-line unions, do a trial merge in a detached scratch worktree (`git worktree add --detach`, `merge --no-commit`, resolve, `node --check`, `merge --abort`, `worktree remove`), so you can say "small, already tested".
- Merge first the PR that removes the old UI, so master never ships two copies of the same control (for example a new header bar plus the old in-page box). Tell Mitch to hold the other PR, even when it finished first and is green.
- **When Mitch says "merged", confirm `state` is `MERGED` before you act on it.** His `gh pr checks --watch && gh pr merge` line may still be waiting on CI. If the PR is still `OPEN` with checks pending, poll in the foreground (`until state==MERGED; sleep 10`, under 600 s), then continue. Retargeting or merging master into a stacked branch any earlier works against the wrong base.
- Report parallel feature PRs as one table (PR | what | state).
- If Mitch merges a PR while its fix child is still running, stop the child (kill its background session), move the worktree to a new branch with `git checkout -b <new> origin/master` (uncommitted edits carry over), and resume the same session id with "PR merged; open a NEW PR from this branch". Restarting fresh would lose its context; letting it run would push to a merged branch.

## Release bumps

- Before telling Mitch to merge an auto-opened talos bump PR, check which commit its tag contains (`git log -1 <tag>`, `gh run list --branch master`). Back-to-back merges cancel the earlier master CI run, so that merge never gets its own release and the open bump can carry an older tag that lacks the latest fix. Tell him to merge the newest bump. Close the stale older bumps yourself with `gh pr close <n> -c "Superseded by a newer bump."` (closing isn't blocked, only merging), since merging a stale bump later rolls the app back. When a feature PR is still about to merge, say the open bump will be stale soon and offer two choices: merge it now for the partial release, or wait for the next bump.
- Get any memory-limit or other infra fix merged before the next release bump rolls the pod.

## Resolving conflicts

- After each base PR merges, check every branch with `git merge-tree --write-tree --name-only HEAD origin/master`. It is read-only, so it's safe while a child edits. A conflict fix that started before another PR merged is already behind: run it again when the fix finishes.
- When the conflict is between two features' logic in the same module (not just lists), or spans many files, hand it to a child: resume the PR author's `session_id` if it exists, else a fresh Sonnet child in that worktree with the conflicting file list, "keep BOTH sides' features", the four gates, push without force, one "Update" line in the PR body. Run the per-PR children in parallel.
- Resolve list-shaped conflicts yourself: `pub mod` lines, import lists, route tables, sibling HTML sections, `CREATE TABLE IF NOT EXISTS` blocks in the schema. Union both sides and keep sorted order where the file is sorted. Steps: `git merge --no-commit origin/master`, resolve, `git add`.
- When both sides add a new function at the same spot, the shared closing `}` sits after the `>>>>>>>` marker. Keep-both must close the first function: `ours + "}\n\n" + theirs`. Run `cargo check` right after, before the slow gates.
- When both sides added the same helper under different names (two Qwen-only guards, two geocoder clients), keep master's copy whole (`git checkout --theirs <file>`), then `grep -rn <old_name> crates/` and repoint this branch's callers and tests to master's name. Keeping both leaves two guards that drift apart; `cargo check` right after catches any caller you missed.
- Check the merged logic, not just the markers: a new filter must run through the shared filter function (e.g. `views::matches_shopping`) so the faceted counts include it. Tests that count outbound requests on a fake network break when another branch adds requests during ingest; clear the fake log after setup.
- **Stacked PR after its base was squash-merged:** a squash commit doesn't match the base's commits, so merging master into the stacked branch raises add/add conflicts even in files the stacked PR never touched. Fix it without force-pushing:
  1. Retarget the PR: `gh pr edit <n> --base master`.
  2. Find the old base tip inside the branch: `B=$(git merge-base HEAD <base-branch-head-sha>)`.
  3. Run `git merge --no-commit origin/master`. For each conflicted file, run `git checkout --theirs -- <f>` and `git add <f>`.
  4. Re-apply only this PR's own changes: `git diff $B HEAD -- <conflicted files> > own.patch && git apply --3way own.patch`. Files where `git diff $B HEAD` is empty stay as master's version.
  5. Verify that the merge equals the PR's own diff. `git diff --stat $B HEAD` and `git diff --cached --stat origin/master` must match. The sorted `+`/`-` lines of both diffs must be identical. Then run `cargo check`, then the gates.
- Gate in the background, because full `cargo test` exceeds the foreground cap. For several branches use `scripts/gate-and-push.sh <worktree>...`: it gates each in turn, commits and pushes only the ones that pass, and appends one summary line per branch. Then confirm `gh pr view <n> --json mergeable` reads `MERGEABLE`.
