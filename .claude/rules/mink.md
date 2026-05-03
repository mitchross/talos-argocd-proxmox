---
description: Mink context management and durable note capture
---

This project uses **Mink** (`@drewpayment/mink`) for cross-session context and a portable wiki.

## How it works

- Mink hooks may track session lifecycle, read/write intelligence, learned rules, bug memory, and token usage under `~/.mink/`.
- All Mink state lives outside this repository. Do not create in-repo `.mink/`, `.wolf/`, or similar agent-state directories.
- Hooks do not replace explicit knowledge capture. Durable decisions, verified root causes, runbooks, and gotchas still need `mink note` or `/mink:note`.

## Required capture behavior

During substantive work, proactively capture durable lessons in Mink without waiting for a separate request.

Capture when:

- a decision changes architecture, operations, deployment flow, or long-term workflow
- a bug/root cause is discovered and verified
- a live-system, framework, infrastructure, or integration gotcha is learned
- a reusable pattern is introduced or validated
- future agents/operators would benefit from knowing why something exists

Do not capture routine edits, raw command output, transient debugging noise, or unverified hypotheses.

Use this project slug unless project-specific instructions say otherwise:

```bash
mink note --project talos-argocd-proxmox --category resources --tags "gotcha,workflow" --title "..." --body "..."
```

Use `--category resources` for durable runbooks, gotchas, and reference patterns. Use `--category projects` for active project decisions, milestones, and followups.

Mention saved Mink note paths in the final response. If capture fails, provide the exact note content to save later.
