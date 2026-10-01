# Agent Instructions

## Always use pull requests

For every repository change, create a branch, commit and push that branch,
and open a pull request. Never push directly to `main` or another default
branch. This applies to fixes, documentation, configuration, and urgent
deployment repairs. A request to fix or deploy something is not permission
to bypass the PR workflow. Merge a PR only when the user explicitly asks to merge that specific PR.
This rule takes precedence over direct-push examples in `CLAUDE.md` files.

## Operating contract

- Discover repository facts, relevant history, and available runtime evidence before asking the user to restate them; ask for unresolved intent or unavailable facts.
- Git describes desired state; live systems describe runtime state; Mink is dated historical context. Verify memories against current manifests, live state, and canonical docs; they do not override the current request or repository safety rules.
- State a root cause only when evidence distinguishes it from plausible alternatives; otherwise label it a hypothesis.
- Preserve the user's requested objective, approach, and scope. Explain any necessary change of approach before substituting a solution.
- An implementation request authorizes scoped investigation, edits, validation, feature-branch commit/push, PR creation, and CI review without repeated approval. Honor narrower requests, including analysis-only work.
- Keep routine work fast: scoped discovery → change → targeted local checks → PR → CI review. Complete required repository checks, let CI run broad suites, and repeat validation only for new changes, failures or unresolved risks. Keep plans and reports brief; scale risk review to the actual impact.
- Start from a refreshed, intended base in an isolated worktree; preserve others' changes and stage only task-owned files.
- Destructive live or storage operations require explicit authorization and verified prerequisites.
- Do not advance a dependent GitOps phase merely because its prerequisite PR merged; verify the required prerequisite state live first.
- After merge, verify the affected runtime when applicable. Documentation/instruction-only changes do not need a cluster health gate.

## Repo rules live in CLAUDE.md

Before changing anything in this repo, read `CLAUDE.md` in the repo root — it
is the law here (GitOps-only workflow, directory = ArgoCD Application, sync
waves, kopiur backups, Gateway API rules). Nested `CLAUDE.md` files in
`infrastructure/`, `my-apps/`, `monitoring/`, etc. carry directory-specific
rules. Before editing a file, read each applicable `CLAUDE.md` along its
path from the repo root to the file, in parent-to-child order. Load these
files yourself; do not wait for the user to mention or attach them.

## Skills and commands (Claude Code and Codex)

Repo procedures live once, in `.claude/commands/*.md`. Claude Code runs them as
`/project:<name>`; Codex finds the same ones through the thin wrappers in
`.agents/skills/<name>/SKILL.md`. Change the procedure in `.claude/commands/`,
never in a wrapper.

| Skill | Use it to |
|---|---|
| `new-app` | add an ArgoCD-discovered app |
| `add-backup` | back up a PVC with kopiur |
| `new-database` | add a plain Postgres database |
| `place-storage` | choose a PVC's storage class and size |

## Mink Knowledge Capture

Keep Mink updated during substantive work. Hooks may track session state automatically, but durable decisions, verified root causes, runbooks, and gotchas require explicit note capture with `mink note` or `/mink:note`.

Use `mink note --project talos-argocd-proxmox --category resources` for durable references and `--category projects` for active decisions or followups. Do not capture routine edits, raw command output, or unverified hypotheses. Mention saved Mink note paths in the final response.
