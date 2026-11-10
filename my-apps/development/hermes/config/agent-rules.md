# Global rules for coding agents in the Hermes pod

The repo's own `AGENTS.md` and `CLAUDE.md` add to these rules. When they conflict, the stricter rule wins.

## Hard rules

- Work on a feature branch and open a pull request. Never push to the default branch.
- Never merge a pull request. Mitch merges after review.
- Never force-push, `git reset --hard`, `git clean` or delete a branch unless Mitch asks.
- Stage only the files your task changed.
- Never commit secrets. Secrets live in 1Password and reach pods through ExternalSecrets.
- Change config only through Git. Day-to-day fixes (restart, scale, Argo sync) are fine.
- Never install a tool onto the `/opt/data` volume. Add it to the `hermes-dev` Dockerfile in `homelab-images` through a pull request.

## Code: the smallest complete change

Full rules: `/opt/data/skills/software-development/ponytail/SKILL.md`.

- Read the code you touch and its callers first. Fix the root cause once, in the shared code.
- Take the first option that fully works: skip it, reuse what the repo has, use the standard library, use an installed dependency, then write new code.
- Add no abstraction, option, config, dependency or "for later" code nobody asked for. Deletion beats addition.
- Finish the whole change: callers, tests and fixtures your change breaks.
- New non-trivial logic gets one small test or self-check.
- Search the web for versions, flags, CRD fields and Helm values. Never state them from memory.
- Separate observations from hypotheses. Name a root cause only when evidence rules out the alternatives.

## Code comments

- A comment explains a mechanism the code does not show, or a gotcha that broke something.
- Keep each comment to one line. Use two only when the second adds new facts. Never three.
- Put no dates, incident history, measurements or procedures in comments. Put them in the commit, the PR body or `docs/`.
- Do not restate the code or justify the change. Old files carry legacy comment density; do not match it.

## Writing (docs, commits, PR text, replies)

Full rules: `/opt/data/skills/pstack/unslop/SKILL.md`.

- Lead with the result. Use plain words a junior engineer follows.
- Use active voice and the imperative. One idea per sentence, 20 words or fewer.
- Use one word for one meaning. Keep code, commands and names exact.
- Cut filler, hedging, chatbot phrases, em dashes, emojis and AI vocabulary (crucial, robust, leverage, delve).
- PR body: what changed, what you tested, what you could not test, and how to roll back. One or two short paragraphs, a small table at most. No evidence dumps, no "Generated with" footers.
- Reviews: group findings as Must fix, Should fix and Nice to have. Give each the smallest fix and its file and line. No "consider", no style taste.
- End your report with one line on what you skipped or did not check.
