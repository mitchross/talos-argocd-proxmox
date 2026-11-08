---
name: github
description: "GitHub via gh CLI: PRs, issues, reviews, repos, auth."
version: 2.0.0
author: Ben Barclay (benbarclay), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [github, gh, git, pull-requests, issues, code-review, repos, auth, ci]
    category: software-development
    related_skills: [codebase-inspection, requesting-code-review]
---

# GitHub

Work GitHub end to end with the `gh` CLI (REST fallback where noted): auth,
issues, the PR lifecycle, issue-to-PR delivery, code review, and repo
management. This skill consolidates six former skills; each workflow lives
complete in its reference file — ALWAYS read the matching reference before
starting that workflow, the body below only routes.

## Routing

| Task | Read first |
|---|---|
| Auth broken / new machine / token or SSH setup / gh login | `references/auth.md` |
| Create, triage, label, assign, close issues | `references/issues.md` |
| Branch, commit, open PR, watch CI, merge | `references/pr-workflow.md` |
| Carry an ISSUE to a verified PR (full delivery loop) | `references/issue-to-pr.md` |
| Review someone's PR: diffs, inline comments, verdict | `references/code-review.md` |
| Clone/create/fork repos, remotes, releases | `references/repo-management.md` |
| Self-hosted app from user's fork broke; port an upstream fix | `references/repo-management.md` § Porting One Upstream Fix |
| Break an initiative into a tracking issue + sub-issues | `references/issues.md` § Planning an initiative |
| "Which open issues are resolved?" audit across repos (GitHub + Gitea) | `references/issues.md` § Open-issue status audit |
| Reorganize/rewrite a repo's docs (moves, link rewrite) | skill `repo-docs-overhaul` |

Supporting assets: `scripts/gh-env.sh` + `scripts/git-credential-token.py`
(auth helpers), `templates/` (PR bodies, bug report, feature request),
`references/ci-troubleshooting.md`, `references/conventional-commits.md`,
`references/github-api-cheatsheet.md`, `references/review-output-template.md`.

## Core discipline (applies to every workflow)

- Preflight once per session: `gh auth status` — if it fails, go to
  `references/auth.md` before anything else.
- Prefer `gh` over raw REST; drop to `gh api` only for endpoints the
  porcelain lacks (the cheatsheet lists them).
- Never report CI green without checking `gh pr checks` yourself; never
  claim merged without verifying `state,mergedAt`.
- Read full context before writing: `gh issue view --comments` /
  `gh pr view --comments` — decisions live in threads, not titles.
  `--comments` prints ONLY the comments, not the body; fetch the body
  separately with `--json body -q .body` (task lists live there).
- Sweep for duplicates before creating anything:
  `gh pr list --search` / `gh issue list --search`. Also list the newest
  items regardless of keywords (`gh issue list --state all --limit 10`,
  `gh pr list --state all --limit 10`). Other chat sessions and agents file
  issues and PRs in parallel under different wording, and a keyword search
  misses them. If one already covers the work, comment on it or link it
  instead of opening a second item.
- Before cloning or offering to clone, establish WHICH machine you run on
  (`hostname; uname -r`) and where the user's working copy lives. Hermes and
  its Paseo agents may run as pods on the user's cluster, not on the desktop
  where they actually code; a clone there is a separate copy, not their local
  folder. Ask whether the local copy is ahead of GitHub before working on a
  remote-side clone.
- GitOps/infra repos: read the repo's `AGENTS.md`/`CLAUDE.md` and any
  sizing/placement procedure before editing manifests, and verify live
  capacity/state (e.g. `kubectl`) to justify the change in the PR body.
  Never merge unless the user names that PR for merge.
- Stacked PRs (B based on A's branch): before merging A, `gh pr edit B --base master`;
  merge with plain `gh pr merge --merge` and delete branches only after the whole stack
  lands. `gh pr merge --delete-branch` on A deletes B's base and GitHub CLOSES B instead
  of retargeting it (recover: re-push the base branch, `gh pr reopen`, then retarget).
- Finding a repo from a loose spoken name (spaces, missing dash): list and
  fuzzy-grep instead of guessing the slug —
  `gh repo list --limit 200 --json name,url,description | grep -i <word>`.
  Not every repo is on GitHub: this user also hosts repos on Gitea
  (`https://gitea.vanillax.me/vanillax/<repo>`). If GitHub has no match, or
  the match has issues disabled, check Gitea before reporting "no issues".

## Verification

- The workflow's own reference file defines done for that task.
- Cross-cutting: every claim about remote state (CI, merge, release,
  issue state) is backed by a fresh `gh` read, never memory.
