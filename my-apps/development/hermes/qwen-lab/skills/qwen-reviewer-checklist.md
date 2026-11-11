---
name: qwen-reviewer-checklist
description: Use when reviewing a Kanban card's diff as qwen-reviewer.
version: 2.0.0
metadata:
  hermes:
    tags: [Code-Review, Kanban, Qwen-Lab]
    category: qwen-lab
---

# Review with only the goal and the diff

## Steps

1. Read the card with `kanban_show`. Note the Goal and the Done when lines, and read the spec file
   it names. Skip the worker's explanation of why it is right.
2. In the repo, see the diff: `git diff main...<branch on the card>`.
3. Check each item and write pass or fail with one line of proof:
   1. Does the diff do the Goal? Nothing missing?
   2. Does it stay in scope? No unrelated files or rewrites.
   3. Run every Done when check yourself, once. Paste the result line.
   4. Is there a test for the new behaviour?
   5. Any obvious bug: wrong edge case, unhandled error, secret or key in the diff, debug print left in.
4. Decide:
   - All pass: `kanban_complete`. The summary is the 5 lines above and `VERDICT: READY TO MERGE`.
   - Any fail: `kanban_block` with numbered fixes. Each fix names the file and what to change.

## Rules

- Never write the fix. Describe it.
- The verdict is a short list, not a report: under 20 lines, no tables, no re-telling of the spec.
- Style nits alone are not a reason to block.
- If you can't run the checks (missing tool, broken env), say so and block the card instead of guessing.
