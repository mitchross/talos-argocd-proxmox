---
name: repo-docs-overhaul
description: "Use when restructuring, rewriting or retiring a repo's docs."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [docs, documentation, readme, onboarding, self-hosting, llms.txt, agents-md, refactor]
    related_skills: [github, hermes-agent-skill-authoring]
---

# Repo docs overhaul

Restructure and rewrite a repository's documentation so someone with no context can clone, run
and fork it. For this user, the target audience is friends who fork or clone and tinker: **simple
terms, batteries included** (Docker Compose for local, ready-to-apply manifests for Kubernetes,
which is how the owner really runs things).

## When to Use

- "Make the docs clear / easy to set up / ready for people to fork"
- Moving or archiving docs, adding a docs index, deduping setup guides
- Refreshing agent-facing text (`AGENTS.md`, `CLAUDE.md`, `llms.txt`, repo skills) after a stack change
- Replacing one component's docs with its successor's ("replace my X docs with Y"), or documenting how
  a self-built image is built and rolled out: see `references/retire-and-replace-component-docs.md`

## Procedure

1. **Plan as issues first** when the user asks for "issues/tasks": load the `github` skill and follow its
   issues reference, section *Planning an initiative* (a tracking issue plus one sub-issue per PR).
   Typical split: structure → local setup works → k8s manifests in-repo → fork-friendliness →
   plain-language rewrite → agent/LLM docs. Structure goes first because every other issue writes
   into it; wording and agent docs go last because they describe the final shape.
2. **Inventory before moving.** `find docs -type f | sort` plus every top-level `*.md`, then classify:
   user guide / developer guide / reference / *dated or historical* (QA passes, audits, task lists,
   migration plans) → `archive/`.
   - Check whether "historical-looking" files are still referenced as contracts (e.g. crate READMEs
     saying "JSON shapes follow spec-api.md"). Those stay live (e.g. `develop/specs/`), never archive.
   - Grep **non-markdown** files for doc paths too (code comments, scripts, `.env.*`, `llms.txt`,
     CI path filters): `grep -rIn -E 'docs/[A-Za-z0-9_./-]+\.md|GETTING_STARTED|ARCHITECTURE' --exclude-dir={node_modules,.git,target} .`
   - Look for external consumers of blob URLs (App Store privacy-policy URL, other repos). If any
     exist, keep a stub or tell the user in the PR.
3. **Default layout** (adapt names to the repo):
   `docs/README.md` ("I want to… → read this" index + layout) · `start/` · `self-host/` · `app/` ·
   `develop/` · `reference/` · `archive/` (with a README saying it is unmaintained and that current
   pages win on conflict). Keep `README.md`, `CONTRIBUTING.md`, `LICENSE`, agent files at the root;
   leave shared asset dirs (`diagrams/`, `screenshots/`) in place.
4. **Move with `scripts/move_docs.py`.** Write the old→new map (files or whole dirs) as JSON, run with
   `--dry` first, then for real. It `git mv`s (history follows), rewrites every relative link and
   `<img src>` by resolving against the file's *old* location, and replaces bare path mentions in
   code/text files and `blob/<branch>/` URLs.
5. **Verify with `scripts/check_links.py`** after `git add -A` (it scans tracked files, so new files
   are skipped until staged). Also check in-page `#anchors` you wrote against the headings' GitHub
   slugs, and that every `llms.txt` URL path exists. A link that was already broken on the base
   branch is noted in the PR, not silently "fixed" by deleting it.
6. **Dedupe in the same PR only where steps were written in several places:** one canonical page per
   path (Compose, Kubernetes). Getting-started becomes a chooser (pick-your-path table + 5-line
   summary per path + link). Move unique details from the duplicate into the canonical page before
   deleting them; don't drop content.
7. **Keep the structural PR reviewable:** moves + links + index + dedupe only. Leave wording rewrites
   for a follow-up PR so reviewers can tell a moved line from a changed one. Confirm code-file edits are
   comment/help-text only by diffing non-comment lines.
8. PR body: tree of the new layout, what moved where, the verification run (counts), and external-link
   risk. CI failures: compare with the base branch before attributing (`github` → `pr-workflow.md`).
9. **K8s manifests, Compose-first-try and fork-friendly identity** follow
   `references/batteries-included-deliverables.md` (validate.sh + kubeconform; prebuilt images with
   an arch check, a shared bootstrap script, `up.sh`, offline `compose config`; one identity module
   with upstream fallbacks and a resolved-config diff proving the owner's build is unchanged).
10. **After the structure PR merges, the independent issues can run in parallel** (one delegated child per
   issue, each in its own clone; recipe and failure recovery live in skill `hermes-agent`, background-systems
   reference, Delegation section). Keep wording/agent-docs issues last.

## Finishing delegated or interrupted work

- **Re-fetch the base and list overlapping open PRs right before committing**
  (`git fetch origin && git log --oneline HEAD..origin/main`; `gh pr list --search "<component>"`).
  The owner runs other agents (Claude Code on the desktop) in parallel, so main may already carry part of
  the change. Take main's version of overlapping files (`git checkout origin/main -- <dir>`), rebase,
  re-point docs at what main now says, and close a narrower open PR as superseded with a comment
  linking the new one.
- When the user asks to "update issues and PRs, what's next": reply with one table (item · status ·
  action taken), then a numbered next-steps list, one step at a time, ending with a single question
  about step 1-or-2. Name anything untested.

- Helper output is often left uncommitted in its clone. Before committing it, review the diff and
  re-run the verification yourself (render/validate, personal-data grep, link check, tests); a
  child's summary is not evidence.
- A test that fails locally: run that single test on a base-commit checkout before fixing or
  blaming the branch. Failures from tools the pod lacks (e.g. `spawnSync ruby ENOENT`) reproduce on
  base and pass in CI; note them in the PR instead of patching around them.
- Ask before merging unless the user granted merge for those specific PRs. "Keep going / go all
  night" means keep opening PRs, not merging them.
- **Unattended runs:** approval prompts time out with nobody there, and a timed-out command must not
  be retried. Keep each command small enough to be auto-approved: write commit messages and PR
  bodies with `write_file` (then `git commit -F` / `gh pr create --body-file`), and run commit, push
  and `gh pr create` as separate calls so a block stops one step, not three. Commands get flagged for
  heredoc scripts, `python3 -c` / `node -e`, `chmod +x` followed by running the file, and recursive
  `rm`. Edit files with `patch`/`write_file`, and run validators as plain commands on files written
  beforehand. Fetch tool binaries in an earlier, attended step.
- If blocked, stop and leave a summary: what's committed/pushed, what's only staged (branch + path),
  and the decisions the user must make.
- End-of-run report for a multi-PR initiative: one table (PR · closes · CI · merge order, noting
  which PRs are stacked), then what's verified, what still needs the owner's machine (with the exact
  commands), and follow-ups that were noticed but not done.

## Before editing during the reorg

- Files you rewrite wholesale after `git mv` (e.g. getting-started) must be read in full first; partial
  views from grep/sed don't count, and the overwrite would drop content you didn't see. Prefer `patch`
  for section swaps (e.g. replacing a docs table in the README).

## Writing rules for the rewrite pass (user preference)

- A no-jargon 3-sentence "what is this" at the top of the README; a glossary for domain terms.
- A **Pick your path** table: path, time, prerequisites, doc link.
- Every setup guide has the same shape: **You need → Steps → How to know it worked → If it didn't.**
  One action per step, copy-pasteable commands, expected output shown.
- Batteries included: Compose defaults to prebuilt images (local build as an opt-in), and there's a
  one-command entrypoint; Kubernetes ships in-repo (Kustomize base + optional components +
  `examples/minimal`), not "copy from my GitOps repo".
- No dead defaults: date-stamped URLs in `.env.example` expire, so resolve them in a script or fail
  with a clear message.
- Verification that needs Docker, a test cluster or heavy builds (e.g. Rust) runs on a real machine
  (the user's desktop test bed), not a small agent pod; say so in the issue/PR. When the user says
  "write an issue, I'll have a box do it", write it for an agent: see
  `references/batteries-included-deliverables.md` → *Live verification on the test bed*.
- **Fact-check every sentence you simplify** against code/config, not just the old doc: pages
  contradict each other (one says "scan with Expo Go", another says native modules make that
  impossible — `package.json` scripts decide). Simplifying is where wrong claims get copied.
- **Run every command you put in a doc** and paste its real output as the expectation. Commands run
  through `kubectl exec … sh -c` get a non-login PATH, so binaries found via a login profile need an
  absolute path there.
- **No numbers you didn't measure** (build times, sizes): write "takes a while" instead of a guess.
  Figures already in the old docs count as unmeasured too: carrying one forward is how a download
  size ends up an order of magnitude wrong. Mark them for the test-bed run to replace.
- **No absolute privacy/feature claims** ("no tracking") when the owner's deployment turns the
  feature on; state the gate ("off unless `VITE_POSTHOG_KEY` is set").
- Before documenting how to host a component, read its real serving config (e.g. `nginx.conf`) and
  the owner's production routing (the GitOps repo, read-only); routing requirements like same-host
  path splits are easy to miss and break forks.
- A new link you add (glossary, guide) needs its target created in the same PR; trimming the README
  means moving its unique sections into the guide first.

## Agent/LLM docs (AGENTS.md, CLAUDE.md, llms.txt, .claude/)

- Split **public** agent rules (build, test, verify, PR rule, cross-platform parity) from the owner's
  **personal** layer (note-taking hooks like Mink, private GitOps release flow). Committed hooks that
  call tools forkers don't have break every session for them; move them to uncommitted local
  settings or make them no-ops when the binary is missing.
- Collect scattered "be careful here" knowledge (toolchain pins, required system packages, the
  pre-push gate, replay/compat tests, concurrency traps, image contracts) into a repo skill that
  `AGENTS.md` tells every agent to load before touching that area. Source every rule from the repo's
  own handoff/README; don't invent rules.
- Regenerate `llms.txt` after any move. Ship the link check as a committed script plus a CI workflow
  on `**/*.md` and `llms.txt`. Match `github.com/<any-owner>/<repo>/blob/<branch>/<path>` URLs so forks
  pass, and skip archive/node_modules/fenced code.
- **Guard owner-only hooks** so forkers get no errors and the owner's behavior doesn't change:
  `command -v mink >/dev/null 2>&1 || exit 0; mink <sub>`. Test it by running the command without the
  binary (exit 0). Check other agent adapters (e.g. `.pi/` extensions) before touching them: they
  may already ignore a missing binary. Git-ignore `CLAUDE.local.md`, `AGENTS.local.md` and
  `.claude/settings.local.json` for the personal layer, and keep owner-only rules in a clearly labeled
  "Upstream maintainer only" section of `AGENTS.md`. Don't move them to a local file: the owner's
  other agents (cluster clones) still need them.
- **Repo skills pattern** (same as the owner's GitOps repo): the procedure goes in
  `.claude/commands/<name>.md` (a `/name` command, `$ARGUMENTS` placeholder), with a thin
  `.agents/skills/<name>/SKILL.md` wrapper (frontmatter `name`, a trigger `description`, and "read
  `.claude/commands/<name>.md` and follow it"). The useful set for a self-hosted app is:
  area guardrail (e.g. `rust-dev`), `setup-compose`, `setup-k8s`, `fork-setup`, `add-layer`/add-feature
  with the parity rule, and `doctor`. Skills must ask the user for contact emails/IDs rather than
  invent them, confirm the kube context, and refuse to apply to GitOps-managed clusters.
- **Removed-language sweep** (e.g. after a Python → Rust port): besides docs, check Renovate
  `enabledManagers`/`packageRules` (drop managers whose files are gone), `.gitignore` and CI path filters.
  History mentions (handoff docs, behavioural specs, "recorded from the old code" fixtures) stay. CLI
  flag names that still carry the old language are a code change: leave them and list a follow-up.
- Before committing a skill or AGENTS.md, check every path, crate, test name, service and section heading
  it cites (`search_files`, `git grep`, heading greps). Agents follow these literally, so a wrong path costs
  every future session.
- `AGENTS.md` should carry a "verify before done" table (area → exact commands), and say that
  anything the agent couldn't run must be reported as untested.

## Scripts

- `scripts/move_docs.py <map.json> [--dry]`: git-mv plus link/mention rewrite.
- `scripts/check_links.py [repo]`: relative-link and `<img src>` checker for tracked `*.md` (skips fenced code).
- `templates/ci-check-links.py`: committable CI version (set `REPO`/`BRANCH`). It also checks `llms.txt`
  GitHub URLs for any owner, so forks pass. Pair it with a `docs-links.yml` workflow on `**/*.md` and `llms.txt`.
