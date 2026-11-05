# Unslop brief: <repo> docs

Worktree: <absolute worktree path>. Every path is relative to it.
Edit ONLY the files assigned to you. Other agents edit other files in the same worktree at the same time.
Do NOT run any git command that writes (no add/commit/stash/checkout/reset/push). `git diff -- <file>` is fine.

## Goal
Apply the unslop rules to each assigned markdown file. Read them first with `skill_view(name="unslop")`.
Read the repo's AGENTS.md / CLAUDE.md and any docs standard or glossary (e.g. docs/documentation-standard.md,
docs/glossary.md) and follow them. Default style: imperative, one instruction per sentence, <=20 words per
instruction, <=25 per descriptive sentence, active voice, simplify words not facts.

## Hard constraints (accuracy beats style)
- Never change facts: commands, numbers, versions, paths, resource names, flags, dates, warnings, gotchas, limits.
  If unsure what a sentence means, leave it.
- Never touch fenced code, inline `code`, front matter, HTML/SVG, mermaid, link URLs, image paths, table structure.
- Headings: case changes only. A reworded heading changes its #slug: grep the whole repo for the old slug and fix links.
- Keep admonition syntax and list/indent structure valid.
- Em dashes become a period, comma, or colon-before-list. No parentheses or en dashes as substitutes.
  Em dashes inside code, literal UI strings or table placeholders stay.
- Remove decorative emojis. Keep warnings bold; drop bold on routine nouns. "**Label:** restates" bullets become prose.
- Same length or shorter. No new sections. Keep the author's terse voice.
- Report suspected stale facts; do not fix them.

## Done check per file
Re-read the file once after editing. `grep -c '—' <file>` should be 0 outside code.

## Scratch files
Put helper scripts in $TMPDIR/<repo>-<first-file-basename>/. Never move or delete files you did not create.

## Report back
Per file: one line of what changed. List what you left alone and why, renamed headings plus links fixed,
and suspected stale facts.
