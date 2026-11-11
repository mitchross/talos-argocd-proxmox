---
name: qwen-ticket-template
description: Use when splitting work into Kanban cards for the Qwen Lab team.
version: 2.0.0
metadata:
  hermes:
    tags: [Kanban, Planning, Qwen-Lab]
    category: qwen-lab
---

# Split work into a few cards

The whole team shares one model, so every extra card, long spec and long report costs minutes.
Plan lean: one page of spec, at most 5 cards, the last one a merge.

## Steps

1. Write the goal in one sentence. If you can't, ask Mitch one question first.
2. Make the repo under `/opt/data/workspace/qwen-lab/<name>` (`git init -b main`, one first commit).
3. Write the spec to `docs/SPEC.md` in the repo and commit it on `main`. One page: what to build,
   the file layout, the rules, and the test command. Cards name this file; never paste it into a card.
4. Plan the cards. The usual shape:

   | Card | Assignee | Parents |
   |---|---|---|
   | build: code and tests | `qwen-worker` | none |
   | ui: pages (only if there is UI) | `qwen-designer` | build |
   | review: the whole diff, once | `qwen-reviewer` | the last build or ui card |
   | merge: into `main`, run tests | `qwen-lab` | review |

   Add a research card (`qwen-researcher`, no parents) only for facts the spec really lacks.
   Split build in two only when the parts share no files. More cards is slower, not safer.
5. Create the cards parents first, so each child can name its parents. Write each body to a file
   outside the repo with write_file, then run one command per card:

   ```
   hermes kanban --board qwen-lab create "<job>-build: <what>" --assignee qwen-worker \
     --workspace worktree:/opt/data/workspace/qwen-lab/<name> --branch wt/<job>-build \
     --body-file /opt/data/workspace/qwen-lab/<name>-cards/build.md --created-by qwen-lab --json
   ```

   - Add `--parent <id>` once per parent. A card without its parents starts too early.
   - Review and merge cards use `--workspace dir:/opt/data/workspace/qwen-lab/<name>` and no `--branch`.
   - Never pass `--triage`. Always pass `--board qwen-lab`.
   - Don't use heredocs or `node -e`/`python -c` in commands: they stop and wait for approval.
6. Use this body for every card:

   ```
   Goal: <one sentence>
   Spec: docs/SPEC.md (read it first)
   Start from: <"main", or "git merge wt/<parent-branch> first">
   Done when:
   - <a check anyone can run, e.g. "node --test passes" or "answer cites 2 sources">
   Out of scope: <what not to touch>
   ```

   The merge card's body: "Merge `wt/<last-branch>` into `main`, run `<test command>` on `main`,
   complete with the output."
7. Check the plan with `hermes kanban --board qwen-lab list`: every child shows its parents and the
   merge card is last. Then tell Mitch the card ids, one line each, and stop. The board runs the cards.

## If a card fails

- A reviewer blocked it with fixes: create one fix card for the worker (same branch name with
  `-fix`, "Start from: git merge wt/<branch> first"), then a new review card and a new merge card
  behind it. Archive the old review and merge cards: `hermes kanban --board qwen-lab archive <id>`.
- A worker failed the same card twice: load `qwen-best-of-n`.

## Good and bad "done when"

- Good: `pytest tests/test_parse.py passes and includes a test for an empty file`.
- Bad: `parser works`. Nobody can check that.
