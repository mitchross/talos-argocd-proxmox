---
name: qwen-best-of-n
description: Use after a card failed. Run 3 tries in parallel and keep the one that passes.
version: 2.0.0
metadata:
  hermes:
    tags: [Kanban, Quality, Qwen-Lab]
    category: qwen-lab
---

# Best of N, only after a failure

Three tries cost three times the GPU time and slow every other card. Never plan them up front.

## When

- A worker already failed the card, and
- there is a test that can tell right from wrong. Without one you can't pick a winner.

## Steps

1. Write one shared check first: a test file or command whose pass or fail picks the winner. Put it
   in the card body under Done when.
2. Create 3 cards on board `qwen-lab` with the `qwen-ticket-template` command, all assigned to
   `qwen-worker`, same body, titles ending in `(try 1/3)`, `(try 2/3)`, `(try 3/3)`, each with its
   own `--branch`.
3. Create a 4th card for `qwen-reviewer` with the 3 tries as parents. Body: "Run the check on
   each branch. Pick the one that passes with the smallest diff. Review it with the
   qwen-reviewer-checklist."
4. Point the merge card at that review card.

## Rules

- Never more than 3 tries at once.
- If no try passes, don't retry blindly. Read the failures and rewrite the card.
