# Durable & Background Systems

Four systems run alongside the main conversation loop. Quick reference
here; full developer notes live in `AGENTS.md`, user-facing docs under
`website/docs/user-guide/features/`.

### Delegation (`delegate_task`)

Spawn a subagent with an isolated context + terminal session.

- **Single:** `delegate_task(goal, context)`.
- **Batch:** `delegate_task(tasks=[{goal, ...}, ...])` runs children in
  parallel, capped by `delegation.max_concurrent_children` (default 3).
- **Background:** `delegate_task(background=true)` returns a handle
  immediately and keeps the parent loop going; the child's result
  re-enters the conversation as a new turn when it finishes.
- **Roles:** `leaf` (default; cannot re-delegate) vs `orchestrator`
  (can spawn its own workers, bounded by `delegation.max_spawn_depth`).
- **Not durable.** A backgrounded child is still process-local — if the
  parent process exits, the child is lost. For work that must outlive
  the process, use `cronjob` or
  `terminal(background=True, notify_on_complete=True)`.
- **Parallel children on one repo (e.g. one issue → one PR each):** give each
  child its own clone (`git clone <local-repo> <repo>-<issue>` then
  `git remote set-url origin <github-url>`) or set `worktree_isolation`, so
  their branches and working trees can't collide. Put everything in `context`:
  issue number to read with `gh issue view --comments`, the clone path,
  what the host can and cannot verify (no Docker daemon, no toolchain), the
  repo's merge/push rules, and "never merge". Tell each child to commit and
  push a WIP branch early, because a child killed with its parent loses only
  unpushed work.
- **Batch reports "owner exited… outcome unknown":** don't re-dispatch blind.
  Inspect evidence first — `gh pr list --state open` for PRs the children may
  have opened, and `git -C <clone> status -sb` / `git log` in each child's
  clone for committed or uncommitted work — then resume from that state
  (yourself or with a new child pointed at the existing clone) and tell the
  user what survived.
- **If children die a second time** (the app/backend restarts, or the user
  sends a new message while they run), finish the work in the parent
  instead of re-dispatching: the remaining steps are usually review,
  verify, commit, PR, which are short and need the parent's judgement anyway.
- **Long verification in the parent** (test suites, builds > ~2 min): run
  with `terminal(background=true, notify=true)` writing to a log file in
  scratch (`cmd > log 2>&1; echo EXIT=$? >> log`), then
  `process_manage(action="wait")` (waits clamp at ~180 s; call again) and
  read the log. A backend restart mid-turn loses a foreground command's
  output but not the log file.

Config: `delegation.*` in `config.yaml`. Read the live values with
`hermes config get delegation` before advising; set with `hermes config set`.
Changes take effect in new sessions only.

| Key | Meaning | Advice for a typical single-user setup |
|---|---|---|
| `model` / `provider` | Empty = children inherit the parent's model (often the most expensive one) | Pin a cheaper capable model for children; leaf tasks are narrow |
| `max_concurrent_children` | Parallel children per batch (default 3, no ceiling) | 3–4; high values multiply token spend and disk/CPU on small pods |
| `max_spawn_depth` / `orchestrator_enabled` | 1 = flat tree (children can't delegate) | Keep 1 unless running orchestrator workflows |
| `child_timeout_seconds` | 0 = no inactivity cap (floor 30) | ~1800 so a stuck child gets reaped |
| `worktree_isolation` | Each child gets its own git worktree (local backend + git repos) | `true` when children edit the same repo in parallel |
| `max_iterations` | Step budget per child | Default fine |
| `oneshot_max_children` | Total children for `hermes chat -q` runs only | Leave |
| `independent_completions` | Results land per child instead of one message per call | Optional |
| `surface_child_process_notifications` | Show children's background-process notices in the parent | Leave off |

When a user new to Hermes asks about delegation, present this as a
current-vs-recommended table with one plain sentence per knob, then offer to
apply the changes via `hermes config set`.

### Cron (scheduled jobs)

Durable scheduler — `cron/jobs.py` + `cron/scheduler.py`. Drive it via
the `cronjob` tool, the `hermes cron` CLI (`list`, `add`, `edit`,
`pause`, `resume`, `run`, `remove`), or the `/cron` slash command.

- **Schedules:** duration (`"30m"`, `"2h"`), "every" phrase
  (`"every monday 9am"`), 5-field cron (`"0 9 * * *"`), or ISO timestamp.
- **Per-job knobs:** `skills`, `model`/`provider` override, `script`
  (pre-run data collection; `no_agent=True` makes the script the whole
  job), `context_from` (chain job A's output into job B), `workdir`
  (run in a specific dir with its `AGENTS.md` / `CLAUDE.md` loaded),
  multi-platform delivery.
- **Invariants:** 3-minute hard interrupt per run, `.tick.lock` file
  prevents duplicate ticks across processes, cron sessions pass
  `skip_memory=True` by default, and cron deliveries are framed with a
  header/footer instead of being mirrored into the target gateway
  session (keeps role alternation intact).

User docs: https://hermes-agent.nousresearch.com/docs/user-guide/features/cron

### Curator (skill lifecycle)

Background maintenance for agent-created skills. Tracks usage, marks
idle skills stale, archives stale ones, keeps a pre-run tar.gz backup
so nothing is lost.

- **CLI:** `hermes curator <verb>` — `status`, `usage`, `run`, `pause`,
  `resume`, `pin`, `unpin`, `archive`, `restore`, `list-archived`, `prune`,
  `backup`, `rollback`.
- **Slash:** `/curator <subcommand>` mirrors the CLI.
- **Scope:** only touches skills with `created_by: "agent"` provenance.
  Bundled + hub-installed skills are off-limits. **Never deletes** —
  max destructive action is archive. Pinned skills are exempt from
  every auto-transition and every LLM review pass.
- **Cost:** the deterministic inactivity/prune sweep runs for free. The
  aux-model "consolidate overlapping skills into umbrellas" pass is
  **off by default** — opt in with `curator.consolidate: true` or
  `hermes curator run --consolidate`. Routine background curation costs
  zero tokens.
- **Telemetry:** sidecar at `~/.hermes/skills/.usage.json` holds
  per-skill `use_count`, `view_count`, `patch_count`,
  `last_activity_at`, `state`, `pinned`.

Config: `curator.*` (`enabled`, `interval_hours`, `min_idle_hours`,
`stale_after_days`, `archive_after_days`, `backup.*`).
User docs: https://hermes-agent.nousresearch.com/docs/user-guide/features/curator

### Kanban (multi-agent work queue)

Durable SQLite board for multi-profile / multi-worker collaboration.
Users drive it via `hermes kanban <verb>`; dispatcher-spawned workers
see a focused `kanban_*` toolset gated by `HERMES_KANBAN_TASK`, and
orchestrator profiles can opt into the broader `kanban` toolset. Normal
sessions still have zero `kanban_*` schema footprint unless configured.

- **CLI verbs (common):** `init`, `create`, `list` (alias `ls`),
  `show`, `assign`, `link`, `unlink`, `comment`, `complete`, `block`,
  `unblock`, `archive`, `tail`. Less common: `watch`, `stats`, `runs`,
  `log`, `dispatch`, `daemon`, `gc`.
- **Worker/orchestrator toolset:** `kanban_show`, `kanban_complete`,
  `kanban_block`, `kanban_heartbeat`, `kanban_comment`, `kanban_create`,
  `kanban_link`; profiles that explicitly enable the `kanban` toolset
  outside a dispatcher-spawned task also get `kanban_list` and
  `kanban_unblock` for board routing.
- **Dispatcher** runs inside the gateway by default
  (`kanban.dispatch_in_gateway: true`) — reclaims stale claims,
  promotes ready tasks, atomically claims, spawns assigned profiles.
  Auto-blocks a task after `failure_limit` consecutive spawn failures
  (default 2; configurable via `kanban.failure_limit` or per-task
  `max_retries`).
- **Isolation:** board is the hard boundary (workers get
  `HERMES_KANBAN_BOARD` pinned in env); tenant is a soft namespace
  within a board for workspace-path + memory-key isolation.

User docs: https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban

#### Recovering and handing off interrupted work

1. Read `hermes kanban show <id>`, including comments and run diagnostics, before reclaiming or replacing a card. Inspect its existing branch, PRs and output files; a restart can kill a worker after useful work has already persisted.
2. Validate artifact completeness against the original acceptance criteria. A results file or chart can predate the current run; compare timestamps, logs, expected cases and repeat counts. Rerun an interrupted benchmark as a coherent arm rather than silently combining partial runs.
3. Inspect startup recovery rules before unblocking. If startup deliberately blocks a matching stale card, reclaiming it alone can repeat the same cycle; make an explicit, evidence-backed handoff instead.
4. Preserve approvals, scope, completed artifacts, remaining checks and rollback requirements in the handoff. Pin coding cards explicitly to `--model gpt-6.1-sol --provider openai-codex` after checking the installed CLI flags; assigning the default profile alone does not prove model selection.
5. Use `hermes kanban complete <id> --summary "<verified work and remaining-work handoff>"` when closing work that truly meets its scope. Completion requires evidence. Do not mark unmet acceptance criteria done merely to release a dependent card; keep the original blocked, or explicitly record an agreed scope split and link the remaining work.
6. Block cards that require a human merge or prerequisite deployment. Include the exact PR URL and required live check in the block reason. Do not instruct workers to poll for a merge for hours; that consumes a worker slot without advancing the task.
7. Read back each changed card with `hermes kanban show <id>`. Confirm its status, dependency links, model/provider and dispatch state before reporting it running or complete. A successful create command does not establish that its prerequisites are satisfied.

#### Swarms (parallel workers → verifier → synthesizer)

`hermes kanban swarm` builds: a root card (completed at once; it is the
shared blackboard) → parallel worker cards → one verifier → one synthesizer.

1. **Find the CLI first.** In the Hermes pod it may not be on `PATH`:
   `export PATH=/opt/hermes/bin:$PATH`. Python for the internals is
   `/opt/hermes/.venv/bin/python` (system python lacks the deps).
2. **Prep the repo yourself** (fetch, `merge --ff-only`, `git status -s`)
   before creating cards, so every worker reads the same commit. Put the SHA
   in each body.
3. **Use the Python API, not `--worker`, for anything real.** The CLI's
   `--worker PROFILE:TITLE[:SKILLS]` sets the body to the title (no room for
   scope or rules, and colons split the field). It also can't set
   workspace, verifier/synth titles or bodies. Copy
   `templates/kanban-swarm.py`: it calls `kanban_swarm.create_swarm(...)`
   with full bodies, `workspace_kind="dir"` + `workspace_path=<repo>`, so
   workers run in the repo and load its AGENTS.md. Use an `idempotency_key`
   so a re-run returns the same graph instead of a duplicate.
4. **Override the verifier and synthesizer defaults.** `create_swarm`
   hard-codes verifier skill `requesting-code-review` (it auto-fixes code)
   and synthesizer skill `humanizer`, with generic bodies. For read-only
   work, swap the verifier skill (for example `ponytail-review`) and write
   real bodies. Update the `tasks` row (`body`, `skills` as JSON) in the same
   connection, then commit. Tell the user about the swap.
5. **Repeat the hard rules in every card body** (read-only? output path,
   finding-ID prefix per worker, evidence format with file:line). Workers
   see only their own card plus the swarm context suffix.
6. **Confirm dispatch:** `hermes kanban ls` after ~70 s (dispatch interval
   is 60 s). Workers should show `running`. Check `hermes kanban diag` if
   they don't. All swarms share one board and a capped worker pool, so some
   cards wait in `ready` while another swarm runs. That is queueing, not a
   duplicate graph; the `idempotency_key` already prevents duplicates.
7. **"Ping me when done" from the desktop app:** `notify-subscribe` needs a
   messaging `--platform/--chat-id`, and desktop sessions have neither. Run
   a bounded background poll with `terminal(background=true, notify=true)`
   instead. It loops `hermes kanban ls`, exits when the synthesizer card is
   `done` (or any card is `blocked`), and caps at a few hours. On messaging
   platforms, use `notify-subscribe` on the synthesizer card.
8. **Pod restart orphans running cards.** The card stays `running` with a
   claim lock naming the dead pod (`hermes kanban show <id>` → `claimed
   {'lock': '<pod>:<pid>'}`), and heartbeats stop. Confirm the pod is gone
   (`kubectl get pods -n hermes`), then `hermes kanban reclaim <id> --reason
   ...`. The next dispatcher pass (~60 s) reruns it. Restart the watcher
   pollers too, because they died with the old pod.
9. After it finishes, run `git status -s` in the repo to prove read-only
   workers changed nothing. Then read the report before telling the user
   it's done.

### Which one for a "leave a TODO, I'll come back later" request?
- `todo_list` tool: session-scoped step tracker; gone when the chat ends. Not a reminder.
- Kanban: a work queue for agents; cards assigned to a profile get claimed and run by the dispatcher. Wrong for a human-paced reminder.
- A GitHub issue (checklist body) in the repo the work touches: durable and visible to the user. Default choice; also `hindsight_retain` a one-line pointer to it so a later session can resume.
