---
name: mink
description: Mink context management is active in this project. Read this to understand how Mink memory, write enforcement, and note capture work under Pi.
---

# Mink — context management for this project

This project uses **Mink** (`@drewpayment/mink`) for cross-session context management.

## How it works
- Mink runs automatically through a Pi extension at `.pi/extensions/mink.ts` that hooks session start/stop and every read/edit/write tool call, plus Bash/Grep/Glob/MCP results.
- Large tool outputs may be transparently replaced with a compact, reversible summary; if you need the full original, fetch it with `mink retrieve <token>` (the token appears in the summary).
- All state lives in `~/.mink/` on the user's machine — **not** in this repository. Do not create or write to any in-repo state directory (no `.wolf/`, `.mink/`, etc.).
- Read intelligence, write enforcement, bug memory, and the token ledger are handled by the extension. You do not need to manually read or update any state files.
- Mink shares one `~/.mink/` state across every assistant wired to this project, so history is unified whether the user runs Pi or another assistant.

## When to act on Mink
- If the user asks to "save a note", "remember this", "log this to my wiki", or similar, use the `mink-note` skill (`/skill:mink-note`) — it captures into the user's `~/.mink/` vault.
- If the extension surfaces a learning, past bug, or repeat-read warning in context, treat that as authoritative project memory and follow it.
- The `mink dashboard` and `mink agent` commands are user tools — do not invoke them on the user's behalf.
