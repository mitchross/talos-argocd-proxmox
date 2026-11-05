# How I use Hermes: what to copy

**Purpose:** show how this Hermes is actually used day to day, so you can copy the parts that work.
**Status:** review of real usage, 19 October to 5 November 2026. The numbers come from Hermes's own session database.
**Setup first:** [Run Hermes on your PC](hermes-one-computer.md). This page assumes Hermes already runs.

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

Two things stand out. Hermes does the work in a terminal, not in chat.
And most installed skills were never used.

## The loop

Almost every task follows the same loop:

1. Say what you want in one short line. Typos are fine. "fix posthog?" works.
2. Hermes reads files, Git history, live state and docs before it asks anything.
3. Hermes opens a pull request with a short body. It never merges.
4. You review and merge. Then you type "merged".
5. Hermes checks that the change actually works live, and reports what it measured.
6. When something went wrong on the way, Hermes saves the lesson into a skill.

"merged" appears in 169 messages. "keep going" and "you make the call" hand the next decision to Hermes.

**Copy this.** The PR is the safety gate. Hermes can do almost anything, because nothing lands until you merge it.

## SOUL.md: the rules that matter

[`SOUL.md`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/development/hermes/config/SOUL.md)
loads in every chat. These lines change the most:

| Rule | Why it works |
|---|---|
| Lead with the result. Keep replies under 150 words. | You read the answer, not a report. |
| Look it up before you ask. | Fewer questions back to you. |
| Search the web for versions and flags. Never state them from memory. | Stops made-up config keys. |
| Separate observations from hypotheses. | Stops "the root cause is X" guesses. |
| Never merge a pull request. | Keeps you in control. |
| Wait for an explicit yes before anything destructive. | Deletes and wipes need a human. |

**Copy this.** Take the "How to talk" and "How to work" blocks as they are. Replace the homelab rules with your own.

## Skills that earned their place

These are the skills Hermes loaded most. Your own skills beat installed packs.

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

The skills Hermes wrote itself get loaded the most.
They start small and grow each time Hermes makes a mistake and you correct it.

**Copy this.** After any task that took a few tries, say "save that as a skill".
When Hermes repeats a mistake, say "update the skill so it does X".

## Flows worth copying

### Ponytail: less code

[Ponytail](https://github.com/DietrichGebert/ponytail) is "lazy senior dev" mode.
It picks the smallest change that fully solves the task, and it ends every reply with what it skipped or did not check.
It was mentioned in 88 messages here.

| Skill | Use it to |
|---|---|
| `ponytail` | write or fix code with the smallest complete change |
| `ponytail-review` | review a change for logic, risk and bloat |
| `ponytail-audit` | audit a whole repo, read-only |
| `ponytail-debt` | list every `shortcut:` comment left in the code |

### Audit swarm to one fix PR

`ponytail-audit-to-pr` turns a repo audit into fixes. It ran on three apps here (radar-ng, news-reader, deal-scout):

1. Kanban starts parallel auditors, one per area (backend, frontend, contracts, debt).
2. A verifier card re-checks every finding with `ponytail-review`. Unproven findings are dropped.
3. A writer card produces one report.
4. `to-tickets` turns the report into GitHub issues.
5. One coding agent fixes the "must" items in one PR, with real test output.

Design questions stay as issues for you. Nothing merges by itself.

### Unslop: docs that read like a person wrote them

Run `unslop` on any doc, PR body or README before you publish it.
It removes "delve", "crucial", forced lists of three and similar AI tells.
`humanizer` does the same with more voice.
`repo-docs-overhaul` applies both across a whole repo's docs.

### Kanban for long work

Chat turns can die when Hermes restarts. Kanban cards survive restarts and retry.
Put anything that takes longer than a coffee on the board:

```bash
hermes kanban create "Audit the backend" --body-file brief.md --max-retries 2
hermes kanban list
```

Write the brief as a file: the goal, the constraints, what "done" looks like, and "open a PR, never merge".

### Subagent routes

Subagents ran 131 tasks here. Most used `balanced` or the default route. `deep` and `codex` were used for hard bugs and second opinions.
Setup: [Route subagents](hermes-one-computer.md#route-subagents-to-cheap-and-strong-models).

### Cron

Three jobs run on a schedule:

| Job | What it does |
|---|---|
| `homelab-digest` | Loads `homelab-ops`, checks cluster health, writes a short digest |
| `upstream-watch` | A plain script with no model. Every day it reports new upstream Hermes releases and fixes. |
| `strata-v31-watch` | A plain script with no model. Every 6 hours it checks for a new Strata release. |

**Copy this.** Put a script with no model behind a cron job whenever no thinking is needed. It costs nothing to run.

## What not to copy

| Problem | What happened | Do this instead |
|---|---|---|
| Too many skills | 177 installed, 38 ever loaded. Of the 55 pstack skills, 4 were used. Of the Matt Pocock skills, about 6. | Install 10–20. Add a skill when you need it, not before. |
| Every skill costs tokens | The skill list adds about 3,800 tokens to every message. Hermes ignores `disable-model-invocation`, which 72 of these skills set. | Run `hermes skills config` and turn off what you do not use. |
| A strong model for everything | The main chat ran on Claude Opus. At API prices, 17 days came to about $950. A subscription covered it here. | On OpenRouter, use a mid-tier main model. Send hard work to the `deep` route. |
| A rule nobody follows | `SOUL.md` says to send subagents to Codex by default. Only 10 of 131 subagent tasks went there. | Check with real usage that a rule works. Delete rules that do not. |
| Two skills with one name | A local `claude-code` skill shadows the one that ships with Hermes, so both show in the list. | Give your copy a new `name:`, or delete it. |

## Start with this kit

1. Install Hermes and OpenRouter: [Run Hermes on your PC](hermes-one-computer.md).
2. Copy the "How to talk" and "How to work" blocks of `SOUL.md`.
3. Install `ponytail`, `ponytail-review`, `unslop`, `pr`, `to-tickets` and `diagnosing-bugs`.
4. Work in the loop: ask, let it open a PR, merge, say "merged".
5. Say "save that as a skill" after any hard task.
6. After two weeks, ask Hermes which skills it loaded. Turn off the rest.
