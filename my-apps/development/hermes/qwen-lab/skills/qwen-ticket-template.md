---
name: qwen-ticket-template
description: Use when splitting work into Kanban cards for the Qwen Lab team.
version: 1.0.0
metadata:
  hermes:
    tags: [Kanban, Planning, Qwen-Lab]
    category: qwen-lab
---

# Split work into small cards

Small cards win. A card a worker can finish in one sitting beats a big card it gets lost in.

## Steps

1. Write the goal in one sentence. If you can't, ask Mitch one question first.
2. List the steps. Each step that changes code, does research or does UI becomes one card.
3. Check each card against the size rule: one repo, a few files, one clear check. Split it if it fails.
4. Create each card with `kanban_create`:
   - `board`: `"qwen-lab"` (always pass it).
   - `assignee`: `qwen-worker` (code), `qwen-researcher` (questions), `qwen-designer` (UI).
   - `workspace_kind`: `"worktree"` for code, with `workspace_path` set to the absolute repo path
     under `/opt/data/workspace/qwen-lab/`. Never `scratch` for code: it is deleted on completion.
   - `parents`: the card ids it depends on, so it waits for them.
   - Never set `triage: true`.
5. Use this body for every card:

```
Goal: <one sentence>
Context: <files, links, earlier card ids; only what the worker needs>
Done when:
- <a check anyone can run, e.g. "cargo test -p foo passes" or "answer cites 2 sources">
Out of scope: <what not to touch>
```

6. Tell Mitch the card ids, one line each.

## Good and bad "done when"

- Good: `pytest tests/test_parse.py passes and includes a test for an empty file`.
- Bad: `parser works`. Nobody can check that.
