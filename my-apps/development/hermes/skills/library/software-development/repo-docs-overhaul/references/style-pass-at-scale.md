# Style pass at scale (unslop / plain-English rewrite of a whole repo)

Use when the user asks to run `unslop` (or "plain English", "clean up the docs") over a repo's
docs rather than one file. Load the `unslop` skill for the rules; this file is the procedure.

## 1. Scope before editing

- Scan first with `python3 <skill>/scripts/scan_prose_tells.py <worktree>`: it applies the default
  exclusions below and prints words, em dashes, AI vocabulary, emojis and `**Label:**` bullets per
  file outside fenced code as JSON. The numbers size the job and pick the worst files; quote them
  in the first reply.
- Also skip forks of upstream projects (their docs belong upstream), exported design bundles
  (`designs/`), and long implementation specs that code or READMEs cite as contracts
  (`develop/specs/`). Rewording a contract can change what it promises; offer it as a separate
  opt-in pass instead of silently including or dropping it.
- Exclude by default, and say so in the reply and the PR:
  agent instruction files (`CLAUDE.md`, `AGENTS.md`, `SKILL.md`, `.claude/`, `.agents/`, skill
  libraries, agent persona files such as `SOUL.md`), dated records (audits, inventories, dated
  plans/specs, `RECOVERY-<date>` notes, benchmark `results.md`), and `_archive/` apps.
  Agent files are instructions, not reader prose; dated records are history and must not be reworded.
- Read the repo's own docs standard (e.g. `docs/documentation-standard.md`, glossary) and fold it
  into the brief; it overrides generic rules where they differ.
- Split into PRs by audience: PR 1 = root README + the docs site; PR 2 = per-app/component READMEs.
  Each in its own worktree from fresh `origin/main`. Start PR 2's batch right after PR 1 is open,
  without asking.
- Several repos ("all my repos"): one worktree, branch and PR per repo; pick the repos from recent
  PR activity (`gh search prs --author @me --created '>=<date>' --json repository`) plus the Gitea
  checkouts in the workspace, and open Gitea PRs through its API. Create each worktree in its own
  small command (`git -C <repo> worktree add <path> -b docs/unslop origin/<default>`), not one loop
  over all repos: a chained loop can be held for approval, time out, and then may not be retried,
  which stalls every repo at once. Check each repo's default branch (`master` vs `main`) first.

## 2. Fan out

- Copy `templates/unslop-docs-brief.md` (or `templates/unslop-comments-brief.md`) to `$TMPDIR`,
  fill in the placeholders and any repo extra-care notes, and pass only its path plus the file list
  to each child.  The brief tells children to load `unslop` themselves, so it never goes stale. Children share one worktree safely because their file sets are disjoint and none runs git.
- Bin-pack files by prose word count into ~10k-word groups (8 children for ~75k words), `balanced`
  model. Give extra-care notes for the front page, glossary (keep every definition's meaning) and DR
  runbooks (never change step order, commands or warnings).
- Constraints that matter: never change commands, numbers, paths, versions, warnings; never touch
  fences, inline code, link URLs, front matter, admonition syntax; headings may change case only
  (mkdocs slugs are lowercased, so case is free) and any reworded heading needs a repo-wide grep for
  its `#slug`; result same length or shorter; keep the author's terse voice.
- Give each child its own scratch dir (`$TMPDIR/unslop-<n>/`) for helper scripts. Children that
  all write `$TMPDIR/ed.py` overwrite and move each other's helpers mid-run.
- Children report suspected stale facts instead of fixing them. Collect those into the PR body as
  "to check, not changed here".

## 3. Verify yourself (child summaries are not evidence)

1. `python3 <skill>/scripts/check_prose_invariants.py --base HEAD <worktree>`: flags changed fences,
   links, inline code, lost numbers, and em dashes left in prose.
2. Read each flagged spot with `git diff --word-diff=plain -U0 <file> | grep -E '\[-[^]]*[0-9]'`.
   Arrow-to-words edits are fine. Watch for meaning drift in superlatives ("the #1 rule" rewritten
   as "the first rule" changes the claim; use "the most important rule").
3. Remaining em dashes are fine only inside table placeholders, literal UI strings or code comments.
4. Run the docs build exactly as CI does, e.g. `python3 -m venv $TMPDIR/mkvenv &&
   $TMPDIR/mkvenv/bin/pip install -r requirements.txt && $TMPDIR/mkvenv/bin/mkdocs build --strict -d $TMPDIR/site`.
5. Commit only the scoped paths (`git add -A docs README.md`), push, open the PR, check CI.
   GitHub: `gh pr create --base <default> --title ... --body ...`, then after 60-90 s
   `gh pr checks <n> -R <owner>/<repo>`. Gitea (no `tea` CLI): POST
   `{title, head, base, body}` (build it with `jq -n`) to
   `https://gitea.vanillax.me/api/v1/repos/vanillax/<repo>/pulls` with header
   `Authorization: token $GITEA_TOKEN`; CI state is
   `GET .../repos/vanillax/<repo>/commits/<head sha>/status` (`statuses` empty = the repo has no CI).
6. Follow-up passes after the owner merges: check `gh pr view <n> --json state`, then branch a new
   worktree from the fresh default branch. Never push to the merged branch.

## 4. Extra-care files

- Published legal text (app privacy policy, data-source licence summaries): mechanical fixes only
  (em dashes, emojis, bold, curly quotes, heading case). Never reword a promise, retention figure,
  licence term or attribution; a style edit there can change what the owner commits to.
- Stale facts the children flag ("says six, lists seven"): check the source of truth in the repo
  (CSS grid, config, code) and fix them in a separate small commit when it settles the question.
  The user wants them fixed, not just listed; list only the ones the repo cannot settle.

## 5. Code-comment pass ("unslop the code too")

- Separate branch and PR from the docs pass. Bin by comment lines per crate/folder
  (`git grep -h -E '^\s*(//|/\*|\*)' -- <dir> | wc -l`), ~1.3-2k lines per child.
- Brief constraints: comment text only; never touch code, strings, attributes, lint directives
  (`eslint-disable`, `@ts-expect-error`, `#[allow]`), the meaning of `SAFETY:`/`TODO` notes, or
  fenced doctest blocks in doc comments; keep the file's line width and `///` summary-line shape;
  delete a comment only when it restates the next line; no new comments.
- After a language port (e.g. Python to Rust): delete pure provenance pointers to deleted files
  ("port of backend/x.py:120"). Keep the reason when output stays identical on purpose, rewritten
  in present tense ("so tiles match the golden fixtures"). Keep the old language's name where it
  names something that still exists (a compat module, CLI flags, fixture generators).
- Proof: `python3 <skill>/scripts/check_comments_only.py <worktree>` strips comments with a
  string-aware lexer and compares code with HEAD; it must say "code changed in 0". Before
  dispatching, prove the checker on the target repo once: edit a word in a comment (expect 0),
  add a space in code (expect 0, whitespace is collapsed), rename an identifier (expect 1), then
  `git checkout -- <file>`. Add
  `cargo fmt --all -- --check` for Rust. No build or tests are needed when the check passes.
- When the docs PR moves a path that comments cite, tell comment children to leave those lines
  alone, so the two PRs don't conflict on the same line.

## PR body

Short: what kinds of tells changed, what stayed identical and how that was checked (script +
strict build), what was left out on purpose, stale facts to check, rollback = revert.
