# Agent Instructions

## Repo rules live in CLAUDE.md

Before changing anything in this repo, read `CLAUDE.md` in the repo root — it
is the law here (GitOps-only workflow, directory = ArgoCD Application, sync
waves, kopiur backups, Gateway API rules). Nested `CLAUDE.md` files in
`infrastructure/`, `my-apps/`, `monitoring/`, etc. carry directory-specific
rules. Before editing a file, read each applicable `CLAUDE.md` along its
path from the repo root to the file, in parent-to-child order. Load these
files yourself; do not wait for the user to mention or attach them.

## Mink Knowledge Capture

Keep Mink updated during substantive work. Hooks may track session state automatically, but durable decisions, verified root causes, runbooks, and gotchas require explicit note capture with `mink note` or `/mink:note`.

Use `mink note --project talos-argocd-proxmox --category resources` for durable references and `--category projects` for active decisions or followups. Do not capture routine edits, raw command output, or unverified hypotheses. Mention saved Mink note paths in the final response.
