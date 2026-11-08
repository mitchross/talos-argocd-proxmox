---
name: hermes-agent
description: "Use, configure, theme, extend, and orchestrate Hermes Agent."
version: 3.2.0
author: Hermes Agent + Teknium
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [hermes, setup, configuration, multi-agent, spawning, cli, gateway, bots, bot-mode, features, themes, skins, desktop-plugins, tui-widgets, petdex, development]
    homepage: https://github.com/NousResearch/hermes-agent
    related_skills: [claude-code, codex, opencode]
---

# Hermes Agent

Hermes Agent is an open-source AI agent framework by Nous Research that runs in your terminal, a native desktop app, messaging platforms, and IDEs. It's in the same category as Claude Code (Anthropic), Codex (OpenAI), and OpenClaw — autonomous coding and task-execution agents that use tool calling to interact with your system. Hermes works with any LLM provider (OpenRouter, Anthropic, OpenAI, Google, DeepSeek, xAI, local models, and 20+ others) and runs on Linux, macOS, Windows, and WSL.

What makes Hermes different:

- **Self-improving through skills** — Hermes learns from experience by saving reusable procedures as skills that load into future sessions.
- **Persistent memory across sessions** — remembers who you are, your preferences, environment details, and lessons learned. Pluggable memory backends.
- **Multi-platform gateway** — the same agent runs on Telegram, Discord, Slack, WhatsApp, iMessage, Signal, Matrix, Teams, Email, and a dozen more platforms with full tool access, not just chat.
- **Many surfaces** — the same agent core drives the CLI, the Ink TUI, a native Electron desktop app, a web dashboard, and an ACP server for IDEs (VS Code / Zed / JetBrains).
- **Provider-agnostic** — swap models and providers mid-workflow; credential pools rotate across multiple API keys automatically.
- **Profiles** — run multiple independent Hermes instances with isolated configs, sessions, skills, and memory.
- **Extensible & themeable** — plugins, MCP servers, custom tools, webhook triggers, cron scheduling, skins that theme every surface, desktop UI plugins, TUI widgets, and pet mascots.

**This skill is a hub.** The body covers identity, quick start, spawning/orchestration, and hard invariants. Everything else lives in reference files — **load the matching reference (below) before answering**; do not answer detail questions from the body alone.

**Docs:** https://hermes-agent.nousresearch.com/docs/

## Scope & Verification

This skill is a concise operating guide, not the complete source of truth for every Hermes feature. If a Hermes feature, command, or setting is not mentioned here or in a reference, do not treat that absence as evidence that it does not exist. Check the live repository and official docs before giving a negative answer.

Good verification targets, cheapest first:

- **Every shipped feature, one line each: https://hermes-agent.nousresearch.com/docs/llms.txt.** Start here for any "can Hermes do X?" or "how do I do X?" — it indexes the entire documentation set with a link to the page that answers. It is generated from the docs tree on every build, so it is never behind the product. Fetch it with `web_extract`, or `curl -s https://hermes-agent.nousresearch.com/docs/llms.txt` when web tools are off. The whole documentation set in one file is at `/docs/llms-full.txt` (~6 MB): when `web_extract` can't read a docs page, `curl -s .../llms-full.txt -o $TMPDIR/full.txt` and pull the section with `awk '/^### Hindsight/{f=1} f{print; n++} n>110{exit}'` or `grep -n` plus `sed -n a,bp`.
- CLI commands: `hermes --help`, `hermes <command> --help`, and `hermes_cli/main.py`
- Source tree: https://github.com/NousResearch/hermes-agent

Never answer "Hermes can't do that" from memory. Hermes ships far more than this skill body describes, and the index exists so a negative answer is always checkable.

- **Desktop-app UI behaviour (shortcuts, menus, window quirks) is often undocumented.** Grep the Electron main process instead of guessing. Sparse-clone into the scratch dir: `git clone -q --depth 1 --filter=blob:none --sparse https://github.com/NousResearch/hermes-agent ha && cd ha && git sparse-checkout set apps/desktop/electron`, then `grep -rn <term> apps/desktop/electron`. Known desktop fixes (DevTools shortcut, Linux window translucency) are in `references/troubleshooting.md`.
- **When the user pastes a bare GitHub issue URL, read the whole thread** with `gh issue view <n> -R NousResearch/hermes-agent --comments`, because the attached snippet is truncated. Check the linked PRs' state (`gh pr view <n> --json state,mergedAt`), then answer for the user's OS: a short workaround if it isn't fixed yet, or "update to X" if it is.

## Setup and skill-library recommendations

- Audit Mitch's actual workflows before recommending more skills. Keep mobile/Expo, React Native/React and browser-use capabilities available even when recent load counts are low; episodic development needs are not obsolete capabilities.
- Prefer native Hermes Kanban, delegation, learning and memory over custom orchestration. Recommend a new skill only for a concrete gap after comparing it with Ponytail, pstack and existing review/design workflows; leaderboard popularity is discovery evidence, not quality or compatibility evidence.
- Explain skill pruning as reversible discoverability cleanup, not a guaranteed intelligence improvement. A disabled skill cannot be selected or loaded normally until re-enabled; low historical usage alone does not prove disabling it is harmless.
- Follow `references/setup-audit.md` for evidence, token-cost estimates and a reversible pruning procedure.

## Restart safety and design interviews

- Recall the existing design from Hindsight before opening an architecture interview, then verify it against the owning repository and live deployment. Inspect startup seeding, external skill pins, the authored-skill library, drift checks, cron definitions and plugin installation. Present only the verified gap; do not ask Mitch to choose a replacement for machinery already in place.
- Preserve previously answered decisions across interview turns. Treat live install → persistence PR → backup coverage until merge → nightly drift check as the agreed maintenance flow unless Mitch changes it; verify which pieces are implemented rather than calling the whole flow deployed.
- Before proposing restart-safety changes, establish whether Mitch wants fewer restarts, control over restart timing, or recoverable work after any restart. Ask one genuine decision at a time with a recommended answer; inspect code for facts instead of asking Mitch to supply them. If they want to provide more context or send an issue log, pause the interview and implementation until they finish. Do not resend a cancelled question automatically or infer a desktop rendering bug from a cancellation result alone.
- Read every supplied architecture link and relevant issue/PR comment before presenting choices. Summarize what each source actually contributes, and separate a documented deployment recipe from evidence that it solves hot updates, empty-volume bootstrap or interrupted-work recovery.
- Treat preservation of running work across restarts as the acceptance goal, not merely faster startup or avoiding skill-triggered rollouts. Separate saved files, committed conversation history, in-flight turns and child-process execution; persistent storage alone does not preserve running agents.
- Trace the actual update path before recommending a sidecar or manual sync: inspect skill discovery and refresh behavior, startup seeding, generated ConfigMap hashes and pod-template references. Distinguish what Hermes can reload from what GitOps currently forces to restart; a cache-invalidation function alone does not prove every active session refreshes its skill inventory.
- Evaluate reload behavior separately for skills, config, cron jobs, plugins and MCP servers; hot skill discovery does not establish that the other components can safely reload. Do not recommend rerunning the full startup seed against a busy home directory: it can overwrite runtime state and repeat installs. First identify the minimal changed artifact, its supported apply mechanism and concurrent-writer safety.
- Compare change detection separately from applying changes. If periodic checks are considered, make unchanged revisions a cheap no-op rather than repeated cloning, copying or installation; if event-driven delivery is considered, verify the actual event source and projected-volume semantics before claiming it works. Mitch wants low-churn delivery, not a frequent reseed loop, and no delivery design is selected merely because it appeared as a recommended option.
- Separate prevention from recovery. Hot skill delivery can avoid some rollouts, manual sync can defer planned rollouts, and graceful draining can help planned stops; none by itself proves recovery after crashes or node loss. Require an exercised interruption-and-resume check before promising that running work survives.

## Diagnostic and cleanup gates

- Treat `hermes doctor` as a diagnostic inventory, not proof that every warned capability is broken. Verify warnings for configured capabilities with a small read-only call through the active runtime; CLI and gateway environments can differ. Report completed checks and unresolved warnings separately.
- Reconcile skill counts using full canonical identifiers and runtime eligibility before declaring names mismatched. Truncated tables and platform filtering can change displayed totals; do not explain a discrepancy until the exact set difference supports it.
- Before approved cache cleanup, verify the exact paths contain regenerable artifacts and are not in active use. Measure filesystem space before and after, preserve source and worktrees, and report measured space reclaimed rather than adding rounded directory sizes.

## Release reviews and upgrades

1. Read the requested release notes and verify the running version separately from the Dockerfile base pin and deployment digest; these can differ.
2. Compare the notes with the installed version before calling a feature new. Separate changes already delivered in patch releases from newly introduced behavior, breaking changes and documentation roll-ups.
3. For a custom GitOps image, load `homelab-gitops-change-prs` and inspect the image publisher's workflow before promising a deployment. Keep upstream release, tested custom image, published deployment tag and running pod as distinct verification gates.
4. Update the public setup guide and workflow guide alongside the runtime or skill-library change. Check examples, install paths, enabled-skill recommendations and breaking-change advice against the target release; Mitch expects the guides to stay usable without a separate reminder. Keep historical usage snapshots labeled as historical, and distinguish proposed changes from deployed behavior.
5. Verify commands such as rewind, rollback and curator locking against official docs or source before adding them to a guide; similarly named commands can change conversation history, files or skill mutability in different ways. Build the docs after editing, and verify the exact remote PR files before reporting them updated.
6. Report completed gates and the next merge dependency briefly. Do not claim a restart duration without measured evidence, and do not occupy a worker polling a human merge gate. Do not promise that merging two PRs quickly produces one restart: GitOps can reconcile either commit independently. If one rollout matters, combine compatible changes before review or describe the separate rollout risk.

## Quick Start

```bash
# Install (shell installer — bootstraps PM, Python, dependencies, and the launcher)
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash

# Interactive chat (default surface; set display.interface: tui to launch the Ink TUI instead)
hermes

# Single query
hermes chat -q "What is the capital of France?"

# Setup wizard  /  pick model+provider  /  health check
hermes setup
hermes model
hermes doctor

# Other surfaces
hermes desktop                 # launch the native desktop app (alias: hermes gui)
hermes dashboard               # web admin panel + embedded chat
hermes proxy                   # OpenAI-compatible local proxy backed by your OAuth provider
```

## Key Paths

```
~/.hermes/config.yaml       Main configuration (settings — never secrets)
~/.hermes/.env              API keys and secrets ONLY (under $HERMES_HOME if set)
$HERMES_HOME/skills/        Installed skills
~/.hermes/skins/            Custom themes (see references/themes.md)
~/.hermes/desktop-plugins/  Desktop app UI plugins (see references/desktop-plugins.md)
~/.hermes/tui-widgets/      TUI widget apps (see references/tui-widgets.md)
~/.hermes/pets/             Installed pet mascots (see references/petdex.md)
~/.hermes/state.db          Canonical session store (SQLite + FTS5)
~/.hermes/sessions/         Gateway routing index, request dumps, *.jsonl transcripts
~/.hermes/logs/             Gateway and error logs
~/.hermes/auth.json         OAuth tokens and credential pools
~/.hermes/hermes-agent/     Source code (if git-installed)
```

Profiles use `~/.hermes/profiles/<name>/` with the same layout. When a profile is active, resolve the real home from `$HERMES_HOME` — never hardcode `~/.hermes`.

## Routing Table — load the reference for the task

| User wants... | Load |
|---|---|
| **Anything not listed below — "can Hermes do X?", "how do I set up X?"** | **https://hermes-agent.nousresearch.com/docs/llms.txt** |
| Bots that chat, run routines, or message each other; the Bots tab | docs: `/user-guide/bot-mode` |
| CLI commands, subcommands, flags, "how do I run X" | `references/cli-reference.md` |
| In-session slash commands | `references/slash-commands.md` |
| Provider setup, API keys, OAuth; a provider/model missing from the model picker; "add Codex/ChatGPT" (also see the `codex` skill) | `references/providers-and-models.md` |
| config.yaml sections, toolsets, voice/STT/TTS | `references/configuration.md` |
| AGENTS.md / .hermes.md / CLAUDE.md project rules | `references/project-context-files.md` |
| Secret redaction, PII, approval modes, "reset permissions" | `references/security-privacy.md` |
| Delegation, cron, curator, kanban, kanban swarms (parallel workers → verifier → synthesizer) | `references/background-systems.md` + `templates/kanban-swarm.py` |
| Which model runs what: per-subagent model/profile routes (`advanced-delegation` plugin), auxiliary helper models, fallback when a plan rate-limits, "use my Codex/Claude/local models", "stop running out of Claude" | `references/model-routing.md` |
| MCP servers (add, catalog, `hermes mcp`) | `references/native-mcp.md` |
| Installing a published skill pack (Matt Pocock, P-Stack, skills.sh), name clashes, blocked scans, where skills live per repo and desktop | `references/skill-packs.md` |
| Webhook routes and event-driven runs | `references/webhooks.md` |
| A custom theme/skin ("synthwave theme", "change the gold ●") | `references/themes.md` + `templates/skin.yaml` |
| A desktop app UI element (pane, widget, ⌘K command, page) | `references/desktop-plugins.md` + `templates/plugin.js` |
| A live TUI panel or modal widget (ticker, clock, dashboard) | `references/tui-widgets.md` + `templates/clock.mjs` |
| Pet mascots — install, select, scale, diagnose | `references/petdex.md` |
| Windows-specific issues (keybinds, WinError 10106, BOM) | `references/windows-quirks.md` |
| Debugging: voice, tools missing, gateway, aux models, Hindsight stalls, web_extract backend, a failed cron run, where cron output shows in Desktop, desktop DevTools, Linux desktop window transparent | `references/troubleshooting.md` |
| "How would a friend set up Hermes like mine", a starter kit, OpenRouter + Hindsight with no cluster (own-PC installer, optional Hindsight compose, skills and building focus) | `references/portable-setup.md` |
| "Audit my Hermes", is my setup optimal, clean up sessions/memory, usage/cost stats, coaching; "how will I know about upgrades" (daily upstream watch) | `references/setup-audit.md` + `templates/upstream-watch.py` |
| Contributing code: adding tools, slash commands, tests | `references/contributor-guide.md` |
| delegate_task "capped at N" reports | `references/delegate-task-concurrency-diagnosis.md` |
| "Can app X use my Nous Portal subscription/OAuth?" | `references/portal-auth-for-third-party-apps.md` |
| Connecting a messaging platform (Telegram, Discord, Slack, WhatsApp, …) | docs: `/user-guide/messaging` |
| "Look at my desktop/PC", where the agent actually runs, reaching files on other machines (Gateways registry, `hermes peer`, SSH backend) | `references/multi-machine.md` |

The reference list above is not the feature list — it is the set of topics that
need more than their docs page. For everything else Hermes ships, fetch
`llms.txt` and it maps the question to the page that answers it.

Two theming rules that hold even without loading the reference: **you apply skins yourself** (`hermes config set display.skin <name>` — every surface repaints live within ~a second; don't tell the user to run `/skin`), and **to tweak one color, edit the ACTIVE skin** (`hermes skin set <key> <hex>`) — never fork `default`, which drops the palette and resets the background.

## Spawning Additional Hermes Instances

Run additional Hermes processes as fully independent subprocesses — separate sessions, tools, and environments.

### When to Use This vs delegate_task

| | `delegate_task` | Spawning `hermes` process |
|-|-----------------|--------------------------|
| Isolation | Separate conversation, shared process | Fully independent process |
| Duration | Minutes (bounded by parent loop) | Hours/days |
| Tool access | Subset of parent's tools | Full tool access |
| Interactive | No | Yes (PTY mode) |
| Use case | Quick parallel subtasks | Long autonomous missions |

### One-Shot Mode

```
terminal(command="hermes chat -q 'Research GRPO papers and write summary to ~/research/grpo.md'", timeout=300)

# Background for long tasks:
terminal(command="hermes chat -q 'Set up CI/CD for ~/myapp'", background=true)
```

### Interactive PTY Mode (via tmux)

Hermes uses prompt_toolkit, which requires a real terminal. Use tmux for interactive spawning:

```
# Start
terminal(command="tmux new-session -d -s agent1 -x 120 -y 40 'hermes'", timeout=10)

# Wait for startup, then send a message
terminal(command="sleep 8 && tmux send-keys -t agent1 'Build a FastAPI auth service' Enter", timeout=15)

# Read output
terminal(command="sleep 20 && tmux capture-pane -t agent1 -p", timeout=5)

# Send follow-up
terminal(command="tmux send-keys -t agent1 'Add rate limiting middleware' Enter", timeout=5)

# Exit
terminal(command="tmux send-keys -t agent1 '/exit' Enter && sleep 2 && tmux kill-session -t agent1", timeout=10)
```

### Multi-Agent Coordination

```
# Agent A: backend
terminal(command="tmux new-session -d -s backend -x 120 -y 40 'hermes -w'", timeout=10)
terminal(command="sleep 8 && tmux send-keys -t backend 'Build REST API for user management' Enter", timeout=15)

# Agent B: frontend
terminal(command="tmux new-session -d -s frontend -x 120 -y 40 'hermes -w'", timeout=10)
terminal(command="sleep 8 && tmux send-keys -t frontend 'Build React dashboard for user management' Enter", timeout=15)

# Check progress, relay context between them
terminal(command="tmux capture-pane -t backend -p | tail -30", timeout=5)
terminal(command="tmux send-keys -t frontend 'Here is the API schema from the backend agent: ...' Enter", timeout=5)
```

### Session Resume

```
# Resume most recent session
terminal(command="tmux new-session -d -s resumed 'hermes --continue'", timeout=10)

# Resume specific session
terminal(command="tmux new-session -d -s resumed 'hermes --resume 20260225_143052_a1b2c3'", timeout=10)
```

### Tips

- **Prefer `delegate_task` for quick subtasks** — less overhead than spawning a full process
- **Use `-w` (worktree mode)** when spawning agents that edit code — prevents git conflicts
- **Set timeouts** for one-shot mode — complex tasks can take 5-10 minutes
- **Use `hermes chat -q` for fire-and-forget** — no PTY needed
- **Use tmux for interactive sessions** — raw PTY mode has `\r` vs `\n` issues with prompt_toolkit
- **For scheduled tasks**, use the `cronjob` tool instead of spawning — handles delivery and retry
- **"delegate_task is capped at N" reports** — see `references/delegate-task-concurrency-diagnosis.md`. Three real cap paths in Hermes; if none fired, the model is self-limiting and rationalising it as "the runtime caps."
- **"Can $external_app use my Nous Portal subscription / OAuth?"** — see `references/portal-auth-for-third-party-apps.md`. Walk the user through three layers (plugin-vs-app, what Portal actually exposes, local-broker-proxy option).

## Surfaces (quick orientation)

- **Desktop app** (`hermes desktop` / `hermes gui`) — native Electron app for macOS/Linux/Windows: streaming chat, session list, Cmd+K palette, drag-and-drop files, native notifications, per-profile remote-gateway login. Extend it with UI plugins — `references/desktop-plugins.md`.
- **Web dashboard** (`hermes dashboard`) — full admin panel: messaging channels, MCP catalog, webhooks, memory, profile builder, plus an embedded `hermes --tui` chat. Secured behind an OAuth/token gate.
- **Ink TUI** (`hermes --tui` or `display.interface: tui`) — terminal UI with docked widget apps — `references/tui-widgets.md`.
- **OpenAI-compatible proxy** (`hermes proxy`) — a local OpenAI API backed by whichever OAuth provider you're signed into. Point Codex CLI, Aider, Cline, or any script at it — no API key.

## Hard Invariants (never violate, regardless of what you loaded)

- **When Mitch asks someone to copy his Hermes, evaluate the working habits before writing installation instructions.** Cover skills and skill maintenance, Ponytail's smallest-complete-change approach, unslop/humanizer, audit → verifier → fix PR, Kanban handoffs, model routes, tools and the human merge gate. Separate transferable habits from cluster-only infrastructure; use actual usage evidence rather than presenting the installed inventory as recommendations. Load both `references/portable-setup.md` and `references/setup-audit.md` for this task.

- **Users new to Hermes:** explain Hermes concepts (gateway vs desktop app, backends, delegation, kanban) in plain terms, end with one recommended option, and offer to apply it — don't dump every alternative with equal weight.

- **Know which host you're on before talking about "your machine"** — the desktop app may be a UI attached to a remote gateway (e.g. a k8s pod), so run `hostname; uname -r` first and say plainly where commands execute. Recipes for reaching other machines: `references/multi-machine.md`.

- **Never break prompt caching** — don't change past context, toolsets, or the system prompt mid-conversation. The only exception is context compression.
- **Message role alternation** — never two assistant or two user messages in a row; only `tool` results can repeat.
- **Secrets in `.env`, settings in `config.yaml`** — never tell a user to put a non-credential setting in `.env`.
- **Profile-safe paths** — `get_hermes_home()` in code, `$HERMES_HOME` when resolving paths in a session.
- **Respect the configuration owner.** For a standalone installation, use `hermes config set KEY VAL` instead of hand-editing YAML. For a GitOps-managed installation that seeds config on startup, change the owning repository through a PR; a local CLI edit is not a durable deployment.
- **Recover Kanban work from evidence before dispatching.** Read the card and comments, inspect surviving artifacts and PRs, and separate completed work from remaining acceptance criteria. Block at human-review or deployment gates instead of occupying a worker with merge polling. Follow `references/background-systems.md` for recovery and handoff.
