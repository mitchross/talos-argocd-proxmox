# Brief: unslop code comments (comments only)

Worktree and file scope: given in your task. Edit only files in your scope; other agents edit other files.
Do NOT run any git command that writes. `git diff` is fine. Read the repo's AGENTS.md first.
Read the rules with `skill_view(name="unslop")` and apply them to comment text only.

## Goal
Comments say WHY or state a non-obvious fact. Delete a comment only when it restates the next line word for word.

## After a language port (fill in or delete)
<old language> code was removed on <date>.
- Delete pure provenance pointers to deleted files ("Port of backend/x.py:120-180").
- Rewrite "the old code did X, so we do X" as a present-tense reason ("so tiles match the golden fixtures").
- Keep the old language's name where it names something that still exists (compat module, CLI flags, fixture generators).
- Leave lines containing <paths another open PR moves> unchanged.

## Hard constraints
- Change ONLY comment text. Never change code, strings, identifiers, attributes (`#[allow]`, `#[cfg]`), lint
  directives (`eslint-disable`, `@ts-expect-error`, `biome-ignore`, `prettier-ignore`), the meaning of `SAFETY:`,
  `TODO`, `FIXME`, license headers, or fenced ``` blocks inside doc comments (doctests).
- Keep the file's line width (Rust: 100) and `///` shape (summary line, blank `///`, detail).
- Keep every number, unit, invariant, issue reference and warning. No new comments. Same length or shorter.
- Don't churn: leave plain comments alone.

## Proof (required before you report)
`python3 /opt/data/skills/software-development/repo-docs-overhaul/scripts/check_comments_only.py <worktree>`
must report "code changed in 0". For Rust also run `cargo fmt --all -- --check` where Cargo.toml lives.

## Scratch files
Put helper scripts in $TMPDIR/<repo>-<scope-name>/. Never move or delete files you did not create.

## Report back
Per folder: comments edited and deleted, provenance pointers removed, 2-3 before/after examples, what you
left alone and why, and the checker's final line.
