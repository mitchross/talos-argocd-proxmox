You are in a git worktree of <OWNER/REPO> at <WORKTREE>, branch `<BRANCH>` (based on origin/<DEFAULT> @ <SHA>). Read AGENTS.md first, plus any skill it names for the areas you touch.

Fix exactly these audit findings. Read each with `gh issue view <n> -R <OWNER/REPO> --comments` (a "Decision" comment, when present, overrides the audit's suggested fix):
- #<N1> (<ID1>): <one-line problem + intended change>
- #<N2> (<ID2>): ...
Do NOT touch any other finding. Keep the diff minimal.
<If another open PR edits nearby files: "PR #<n> edits <files>; do not touch those files.">
<If another fix run is in flight at the same time: "Another agent is editing <files/dirs> in parallel. Do NOT touch those." and halve the gate workers below (cargo -j 2, --maxWorkers=2).>
<For an audit claim marked unverified that the code can settle: "FIRST verify <claim> in <files> and quote the proving code in the PR body. If you can't prove it, change nothing for that finding, explain why, and write `Part of #<N>`.">
If the repo has more than one client (e.g. web + app parity in AGENTS.md), check whether each bug also exists in the other client. Fix it there too, or say in the PR why that client is unaffected.
For backend fixes, keep output byte-identical and keep Temporal activity inputs and outputs unchanged. If a fix would change them, stop and explain in the PR instead.
For dead-code deletes: before deleting, grep the WHOLE repo for every symbol, key and string it writes or exports, and every way the code can be invoked (Dockerfiles, CI workflows, scripts, compose files, docs, skills). If you find a real reader or caller, stop and explain in the PR. Put the grep commands and results in the PR Evidence.
For dependency additions: don't let `npm install` re-resolve the lockfile. Add the dependency at the version already locked (edit the root `packages[""]` entry by hand if needed), then prove consistency with `npm ci`; `git diff <lockfile>` must touch only that package.
If an issue names a symbol, key or file that doesn't exist as described (audits go stale), fix the real equivalent and say in the PR what differed; don't invent values (e.g. cadences for planned sources).
If you move code that Temporal workflow files import into a shared module, keep that module pure (no `process.env`, no `node:` imports, no I/O) and keep values and order identical, so replay of in-flight runs is unaffected; say so in Merge Danger.
For every new test, check it fails without its fix.

The pod you run in can be restarted by deployments, which kills this run. Save work early:
- First check `git log origin/<DEFAULT>..HEAD` and `git ls-remote origin <BRANCH>`. If commits or fixes already exist, keep them; don't redo them.
- Commit (one short conventional commit per finding) and `git push -u origin <BRANCH>` BEFORE running the slow gates. Push again after every later fix.

Gates (all from AGENTS.md, or .github/workflows/*.yml when there is none; run them one at a time from the worktree root and log each to <SCRATCH>/checks/<name>.log with `<cmd> 2>&1 | tee <log>`, never a hand-written summary). `cd x && cmd` is often blocked, so pass paths as arguments where the tool allows it (e.g. `python -m pytest -q dashboard`):
- <e.g. in rust/: cargo fmt --all -- --check; cargo clippy --workspace --all-targets -- -D warnings; cargo test --workspace>
- <e.g. in frontend/: bun run lint; bunx tsc --noEmit; bun run test -- --maxWorkers=4>
Give Bash a 600000 ms timeout. Cap every parallel test runner at 4 workers (Jest: `-- --maxWorkers=4`; node: `--test-concurrency=4`), because more starves the pod. Fix failures in touched files. If a failure is pre-existing or caused only by the environment, say so and don't chase it.

PR: if `gh pr view <BRANCH> -R <OWNER/REPO>` finds one, don't make another. Otherwise write the body to <SCRATCH>/pr-body.md and run `gh pr create -R <OWNER/REPO> --base <DEFAULT> --head <BRANCH> --title "<title>" --body-file <SCRATCH>/pr-body.md`.
The body is short, plain English, with Summary, Evidence (the REAL commands and result lines, plus toolchain versions) and Merge Danger (door, blast radius, native rebuild if the app changed). It must contain these lines exactly:
Closes #<N1>
Closes #<N2>
Part of #<EPIC>
Don't write "close", "closes", "fix", "fixes" or "resolve" directly before an issue number anywhere else in the body (not even "does not close #N"): GitHub treats any of them as a closing keyword.
Exception: if you fix only part of a finding (e.g. the audit was wrong about one symbol and you kept it), write `Part of #<N>` instead of `Closes #<N>` for that one, say what is left, and the issue stays open.

NEVER merge. NEVER push to <DEFAULT>. Never force-push. Don't edit issues. Finish by printing the PR URL and one line per gate with its result.
