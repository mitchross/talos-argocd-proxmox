# Global rules for coding agents in the Hermes pod

The repo's own `AGENTS.md` and `CLAUDE.md` add to these rules. When they conflict, the stricter rule wins.

## Git

- Work on a feature branch and open a pull request. Never push to the default branch.
- Never merge a pull request. Mitch merges after review.
- Stage only the files your task changed.

## Code comments

- A comment explains a mechanism that the code does not show, or a gotcha that broke something.
- Keep each comment to one line. Use two lines only when the second line adds new facts. Never use three.
- Put no dates, incident history, measurements or procedures in comments. Put them in the commit message, the PR body or `docs/`.
- Do not restate the code. Do not justify the change.
- When you replace a long comment, do not copy its length. Old files carry legacy comment density.

## Changes

- Read neighboring files first. Keep diffs minimal and easy to review.
- Search the web for versions, flags, CRD fields and Helm values. Do not state them from memory.
- Separate observations from hypotheses. Name a root cause only when evidence rules out the alternatives.

## Writing (docs, PR text, replies)

- Lead with the result.
- PR body: the problem, the new behavior, the checks you ran, and known limits. Usually one or two short paragraphs.
- Use active voice and the imperative. One instruction per sentence, 20 words or fewer.
- Use one word for one meaning. Keep code, commands and names exact.
