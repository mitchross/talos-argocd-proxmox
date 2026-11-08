---
name: codex
description: "Delegate coding to OpenAI Codex CLI (features, PRs)."
version: 1.0.1
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Coding-Agent, Codex, OpenAI, Code-Review, Refactoring]
    related_skills: [claude-code, hermes-agent]
---

# Codex CLI

Delegate coding tasks to [Codex](https://github.com/openai/codex) via the Hermes terminal. Codex is OpenAI's autonomous coding agent CLI.

## When to use

- Building features
- Refactoring
- PR reviews
- Batch issue fixing

Requires the codex CLI and a git repository.

## Prerequisites

- Codex installed: `npm install -g @openai/codex`
- OpenAI auth configured: either `OPENAI_API_KEY` or Codex OAuth credentials
  from the Codex CLI login flow
- **Must run inside a git repository** — Codex refuses to run outside one
- Use `pty=true` in terminal calls — Codex is an interactive terminal app

### Two different "Codex" integrations — disambiguate first

"Add Codex to Hermes" means one of two independent things; check the state of
both before answering, and ask which one if the user's wording doesn't say:

| | Codex CLI (delegated coding agent) | `openai-codex` provider (Hermes's own model) |
|-|-|-|
| What it is | `codex exec` run via the terminal tool | ChatGPT-subscription models in the Hermes model picker |
| Login state | `~/.codex/auth.json` (`codex login`, `codex login --device-auth`) | `$HERMES_HOME/auth.json` (`hermes auth add openai-codex`) |
| Check | `codex login status`, or the smoke test below | `hermes auth list` |

The two logins are SEPARATE — a working Codex CLI login does NOT make Codex
models show up in the desktop/TUI model picker; the picker only lists providers
with a Hermes credential. Do not treat a missing `OPENAI_API_KEY` alone as
proof that either auth is missing.

**Smoke-test the CLI before announcing a provider switch or launching a fan-out.** A successful `codex login status` shows configured credentials, not that a request can authenticate. Send one no-tools request from the task's checkout and inspect its exit code and response:
```
terminal(command="codex exec --sandbox workspace-write --color never 'Reply with just: ok. Do not run tools or modify files.'", workdir="/absolute/path/to/task-worktree", background=true, pty=true, notify=true)
```
Read the tracked process result before starting coding workers. On an authentication failure, preserve the checkout and report the blocker; do not copy credentials between the CLI and Hermes or start another login flow unless requested. Treat any alternate execution route as unverified until it returns real output.

**Add the provider on a headless/remote gateway** (pod, server): run the
device-code login in the background with a PTY, read the URL + code from the
log, hand them to the user, then verify:
```
terminal(command="HERMES_HOME=$HERMES_HOME hermes auth add openai-codex --no-browser", background=true, pty=true, notify=true)
process(action="log", session_id="<id>")   # wait a few seconds; shows auth.openai.com/codex/device + code
# after the user approves:
terminal(command="hermes auth list")      # openai-codex should be listed
```
Then tell the user to click **Refresh models** in the picker. If `hermes` is not
on PATH in the terminal tool (container installs), locate it (`find / -maxdepth 4 -name hermes -type f`, often `/opt/hermes/bin/hermes`).

## One-Shot Tasks

```
terminal(command="codex exec --sandbox workspace-write 'Add dark mode toggle to settings'", workdir="~/project", background=true, pty=true, notify=true)
```

For scratch work (Codex needs a git repo):
```
terminal(command="cd $(mktemp -d) && git init && codex exec --sandbox workspace-write 'Build a snake game in Python'", background=true, pty=true, notify=true)
```

## Background Mode (Long Tasks)

```
# Start in background with PTY
terminal(command="codex exec --sandbox workspace-write 'Refactor the auth module'", workdir="~/project", background=true, pty=true)
# Returns session_id

# Monitor progress
process(action="poll", session_id="<id>")
process(action="log", session_id="<id>")

# Send input if Codex asks a question
process(action="submit", session_id="<id>", data="yes")

# Kill if needed
process(action="kill", session_id="<id>")
```

## Key Flags

| Flag | Effect |
|------|--------|
| `exec "prompt"` | One-shot execution, exits when done |
| `--sandbox workspace-write` (`-s`) | Sandboxed but auto-approves file changes in the workspace (the recommended auto-build mode) |
| `--dangerously-bypass-approvals-and-sandbox` | No sandbox, no approvals (fastest, most dangerous; `--yolo` still works as a hidden alias) |
| `--sandbox danger-full-access` | No Codex sandbox; useful when the host service context breaks bubblewrap |

> **Deprecated:** `--full-auto` still works but the live CLI warns to use `--sandbox workspace-write` instead.

## Hermes Gateway Caveat

When invoking the Codex CLI from a Hermes gateway/service context (for example,
Telegram-driven agent sessions), Codex `workspace-write` sandboxing may fail even
when the same command works in the user's interactive shell. A typical symptom is
bubblewrap/user-namespace errors such as `setting up uid map: Permission denied`
or `loopback: Failed RTM_NEWADDR: Operation not permitted`.

In that context, prefer:

```
codex exec --sandbox danger-full-access "<task>"
```

Use process boundaries as the safety layer instead: explicit `workdir`, clean git
status before launch, narrow task prompts, `git diff` review, targeted tests, and
human/agent confirmation before committing broad changes.

## PR Reviews

Clone to a temp directory for safe review:

```
terminal(command="REVIEW=$(mktemp -d) && git clone https://github.com/user/repo.git $REVIEW && cd $REVIEW && gh pr checkout 42 && codex review --base origin/main", background=true, pty=true, notify=true)
```

## Parallel Issue Fixing with Worktrees

```
# Create worktrees
terminal(command="git worktree add -b fix/issue-78 ~/.hermes/cache/scratch/issue-78 main", workdir="~/project")
terminal(command="git worktree add -b fix/issue-99 ~/.hermes/cache/scratch/issue-99 main", workdir="~/project")

# Launch Codex in each
terminal(command="codex --sandbox workspace-write exec 'Fix issue #78: <description>. Commit when done.'", workdir="~/.hermes/cache/scratch/issue-78", background=true, pty=true)
terminal(command="codex --sandbox workspace-write exec 'Fix issue #99: <description>. Commit when done.'", workdir="~/.hermes/cache/scratch/issue-99", background=true, pty=true)

# Monitor
process(action="list")

# After completion, push and create PRs
terminal(command="cd ~/.hermes/cache/scratch/issue-78 && git push -u origin fix/issue-78")
terminal(command="gh pr create --repo user/repo --head fix/issue-78 --title 'fix: ...' --body '...'")

# Cleanup
terminal(command="git worktree remove ~/.hermes/cache/scratch/issue-78", workdir="~/project")
```

## Batch PR Reviews

```
# Fetch all PR refs
terminal(command="git fetch origin '+refs/pull/*/head:refs/remotes/origin/pr/*'", workdir="~/project")

# Review multiple PRs in parallel
terminal(command="codex exec 'Review PR #86. git diff origin/main...origin/pr/86'", workdir="~/project", background=true, pty=true)
terminal(command="codex exec 'Review PR #87. git diff origin/main...origin/pr/87'", workdir="~/project", background=true, pty=true)

# Post results
terminal(command="gh pr comment 86 --body '<review>'", workdir="~/project")
```

## Rules

1. **Pair PTY launches with background tracking** — use `background=true, pty=true` for the recipes above, then read the tracked process result; a foreground PTY call is rejected before Codex starts.
2. **Git repo required** — Codex won't run outside a git directory. Use `mktemp -d && git init` for scratch
3. **Use `exec` for one-shots** — `codex exec "prompt"` runs and exits cleanly
4. **`--sandbox workspace-write` for building** — auto-approves changes within the sandbox (`--full-auto` is deprecated for this)
5. **Background for long tasks** — use `background=true` and monitor with `process` tool
6. **Don't interfere** — monitor with `poll`/`log`, be patient with long-running tasks
7. **Parallel is fine** — run multiple Codex processes at once for batch work
8. **Explain usage in terms of the chat** — when Hermes is hosted (pod/server), the user doesn't run Codex; they ask Hermes in chat and Hermes runs `codex exec` in the gateway's terminal on a branch, reviews the diff, and opens a PR. Say where it runs and what it can't see (files only on the user's desktop).
