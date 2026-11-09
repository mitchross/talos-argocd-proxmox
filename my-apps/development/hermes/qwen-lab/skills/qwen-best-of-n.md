---
name: qwen-best-of-n
description: Use for a hard card. Run 3 attempts in parallel and keep the one that passes.
version: 1.0.0
metadata:
  hermes:
    tags: [Kanban, Quality, Qwen-Lab]
    category: qwen-lab
---

# Best of N for hard cards

The GPUs run 16 requests at once. On a hard card, spend 3 of them on separate tries and keep the
best. Only for hard cards: the apps need the other slots.

## When

- A worker already failed the card once, or
- The card is tricky logic (parsers, math, concurrency) with a test that can tell right from wrong.

Skip it when there is no automatic check. Without one you can't pick a winner.

## Steps

1. Write one shared check first: a test file or command whose pass or fail picks the winner. Put it
   in the card body under Done when.
2. Create 3 cards on board `qwen-lab`, all assigned to `qwen-worker`, same body, titles ending in
   `(try 1/3)`, `(try 2/3)`, `(try 3/3)`. Each gets its own worktree (`workspace_kind: "worktree"`).
   Add to each body: "Do not request review. Run the check and kanban_complete with its output."
3. Create a 4th card for `qwen-reviewer` with the 3 tries as `parents`. Body: "Compare tries
   <ids>. Run the check in each worktree. Pick the one that passes with the smallest diff. Review it
   with the qwen-reviewer-checklist."
4. Report the winner's card id and worktree to Mitch.

## Rules

- Never more than 3 tries at once.
- If no try passes, don't retry blindly. Read the failures and rewrite the card.
