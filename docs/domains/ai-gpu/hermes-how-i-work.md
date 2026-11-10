# How I use Hermes and what to copy

This page shows how the owner of this homelab uses Hermes day to day, so you can copy the parts that work.
It assumes that Hermes already runs. If it does not, start with [Run Hermes on your PC](hermes-one-computer.md).
The numbers come from Hermes's own session database and cover 19 October to 5 November 2026.

## The numbers

| What | Count |
|---|---|
| Chats from the desktop app | 83 |
| Subagent runs | 70 |
| Kanban worker runs | 36 |
| Cron runs | 18 |
| Terminal commands Hermes ran | 6,950 |
| Times Hermes loaded a skill | 252 |
| Times Hermes created or fixed a skill | 73 |
| Skills installed / skills ever loaded | 177 / 38 |

Two results matter most.
Hermes does the work in a terminal, not in chat.
Most installed skills were never used.

## The loop

Almost every task follows the same loop:

1. Say what you want in one short line. Typos are fine. "fix posthog?" works.
2. Hermes reads files, Git history, live state and docs before it asks anything.
3. Hermes opens a pull request with a short body. It never merges.
4. You review and merge. Then you type "merged".
5. Hermes checks that the change works live, and reports what it measured.
6. When something went wrong on the way, Hermes saves the lesson into a skill.

"merged" appears in 169 messages. "keep going" and "you make the call" hand the next decision to Hermes.

Copy this loop. The pull request is the safety gate.
Hermes can do almost anything, because nothing lands until you merge it.

## SOUL.md rules that matter

`SOUL.md` is the file that sets how Hermes talks and works. Hermes loads it in every chat.
These rules from [this cluster's `SOUL.md`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/development/hermes/config/SOUL.md) change its behaviour the most:

| Rule | Why it works |
|---|---|
| Lead with the result. Keep replies under 150 words. | You read the answer, not a report. |
| Look it up before you ask. | Hermes asks you fewer questions. |
| Search the web for versions and flags. Never state them from memory. | Stops made-up config keys. |
| Separate observations from hypotheses. | Stops "the root cause is X" guesses. |
| Never merge a pull request. | Keeps you in control. |
| Wait for an explicit yes before anything destructive. | Deletes and wipes need a human. |

Copy the "How to talk" and "How to work" blocks as they are. Replace the homelab rules with your own.

## Skills that earned their place

A skill is a Markdown how-to file that Hermes loads when a task matches.
These are the skills Hermes loaded most.

| Skill | Loads | Where it came from | What it does |
|---|---|---|---|
| `homelab-gitops-change-prs` | 42 | Written by Hermes | How to change this repo through a PR, with every past mistake as a pitfall |
| `hermes-agent` | 31 | Ships with Hermes | How to configure Hermes itself |
| `unslop` | 21 | [pstack](https://github.com/backnotprop/pstack) | Cuts AI tells from writing |
| `homelab-ops` | 19 | Written by Hermes | Daily health checks |
| `github` | 18 | Ships with Hermes | `gh` for PRs, issues and reviews |
| `homelab-app-development` | 17 | Written by Hermes | How to build features in this user's apps |
| `ponytail-audit-to-pr` | 13 | Written by Hermes | Audit a repo with a swarm, then ship one fix PR |
| `pr` | 10 | [Matt Pocock](https://github.com/mattpocock/skills) | Short, human PR bodies |
| `ponytail-audit` | 10 | [Ponytail](https://github.com/DietrichGebert/ponytail) | Read-only quality audit of a repo |

Hermes loads the skills it wrote itself more than the installed packs.
Those skills start small and grow each time Hermes makes a mistake and you correct it.

To copy this, say "save that as a skill" after any task that took a few tries.
When Hermes repeats a mistake, say "update the skill so it does X".
[Skills in the PC guide](hermes-one-computer.md#4-skills) explains how to install, write and lock skills.

## Flows worth copying

### Ponytail for less code

[Ponytail](https://github.com/DietrichGebert/ponytail) is a "lazy senior dev" mode.
It picks the smallest change that fully solves the task.
It ends every reply with what it skipped or did not check.
88 messages here mention it.

| Skill | Use it to |
|---|---|
| `ponytail` | write or fix code with the smallest complete change |
| `ponytail-review` | review a change for logic, risk and bloat |
| `ponytail-audit` | audit a whole repo, read-only |
| `ponytail-debt` | list every `shortcut:` comment left in the code |

### Audit swarm to one fix PR

`ponytail-audit-to-pr` turns a repo audit into fixes. It ran on three apps here (radar-ng, news-reader, deal-scout):

1. Kanban starts parallel auditors, one per area (backend, frontend, contracts, debt).
2. A verifier card checks every finding again with `ponytail-review`. It drops unproven findings.
3. A writer card produces one report.
4. `to-tickets` turns the report into GitHub issues.
5. One coding agent fixes the "must" items in one PR, with real test output.

Design questions stay as issues for you. Nothing merges by itself.

### Unslop for docs that read like a person wrote them

Run `unslop` on any doc, PR body or README before you publish it.
It removes "delve", "crucial", forced lists of three and similar AI tells.
`humanizer` does the same with more voice.
`repo-docs-overhaul` applies both across a whole repo's docs.

### Kanban for long work

A chat turn can die when Hermes restarts. A Kanban card survives a restart and retries.
Put any task that takes more than a few minutes on the board:

```bash
hermes kanban create "Audit the backend" --body-file brief.md --max-retries 2
hermes kanban list
```

Write the brief as a file. Include the goal, the constraints, what "done" looks like, and "open a PR, never merge".

### Subagent routes

A subagent route is a named model that Hermes can hand part of a task to.
Subagents ran 131 tasks here. Most used `balanced` or the default route.
`deep` and `codex` were used for hard bugs and second opinions.
[Route subagents](hermes-one-computer.md#route-subagents-to-cheap-and-strong-models) in the PC guide shows the setup.

### Cron

Three jobs run on a schedule:

| Job | What it does |
|---|---|
| `homelab-digest` | Loads `homelab-ops`, checks cluster health, writes a short digest |
| `upstream-watch` | A plain script with no model. Every day it reports new upstream Hermes releases and fixes. |
| `strata-v31-watch` | A plain script with no model. Every 6 hours it checks for a new Strata release. |

Copy this pattern. Put a script with no model behind a cron job when the job needs no reasoning. Such a job has no model cost.

## What not to copy

| Problem | What the data showed | Do this instead |
|---|---|---|
| Too many skills | 177 installed, 38 ever loaded. Of the 55 pstack skills, 4 were used. Of the Matt Pocock skills, about 6. | Install 10–20. Add a skill when you need it, not before. |
| Every skill costs tokens | The skill list adds about 3,800 tokens to every message. Hermes ignores `disable-model-invocation`, which 72 of these skills set. | Run `hermes skills config` and turn off what you do not use. |
| A strong model for everything | The main chat ran on Claude Opus. At API prices, 17 days came to about $950. A subscription covered it here. | On OpenRouter, use a mid-tier main model. Send hard work to the `deep` route. |
| A rule nobody follows | `SOUL.md` said to send subagents to Codex by default. Only 10 of 131 subagent tasks went there. | Check with real usage that a rule works. Enforce it in config, not prose. |
| Two skills with one name | A local `claude-code` skill shadows the one that ships with Hermes, so both show in the list. | Give your copy a new `name:`, or delete it. |

### How this cluster applies these lessons

The cluster's [`config.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/development/hermes/config/config.yaml) enforces the first and fourth lessons:

- `skills.disabled` turns off the 111 skills that were never loaded. They stay on disk. Delete a name from the list to turn that skill back on.
- The `delegation` settings send untagged subagent tasks to the `codex` route.
- `compression.threshold_tokens` compacts long Opus chats at 200k tokens.

The skill trim saves about 2% of input tokens, because the skill list is cached on most calls.
The larger benefit is a shorter list, so Hermes picks the right skill more often.

## Skills worth adding

From the [Skill Leaderboard](https://www.skillleaderboard.com/), only two filled a real gap here:

| Skill | Why |
|---|---|
| [`pbakaus/impeccable`](https://github.com/pbakaus/impeccable) | Designs, critiques and polishes web and native app UI. Ships a Hermes copy. |
| [`cloudflare/security-audit-skill`](https://github.com/cloudflare/security-audit-skill) | Security review of code, APIs and services. |

Big packs such as `obra/superpowers`, the Karpathy skills and `caveman` overlap Ponytail and pstack.
Skip a pack that overlaps skills you already have, unless it replaces one of them.

## Habits

- Start a new chat per topic. A long chat resends its whole history on every call.
  The longest chats here ran 300–450 messages.
- Use `/rewind` (v0.23.0) to go back to an earlier message, then edit it or fork from it. This is faster than arguing a chat back on track.
- Lock skills you curate by hand with `hermes curator lock <skill>` (v0.23.0).
  Hermes cannot rewrite a locked skill, so lessons go through a PR instead.

## Start with this kit

1. Install Hermes and connect OpenRouter with [Run Hermes on your PC](hermes-one-computer.md).
2. Copy the "How to talk" and "How to work" blocks of `SOUL.md`.
3. Install `ponytail`, `ponytail-review`, `unslop`, `pr`, `to-tickets` and `diagnosing-bugs`. Add `impeccable` if you build UIs.
4. Work in the loop: ask, let Hermes open a PR, merge, say "merged".
5. Say "save that as a skill" after any hard task.
6. After two weeks, ask Hermes which skills it loaded. Turn off the rest.
