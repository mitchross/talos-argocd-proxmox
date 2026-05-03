# Agent Instructions

## Mink Knowledge Capture

Keep Mink updated during substantive work. Hooks may track session state automatically, but durable decisions, verified root causes, runbooks, and gotchas require explicit note capture with `mink note` or `/mink:note`.

Use `mink note --project talos-argocd-proxmox --category resources` for durable references and `--category projects` for active decisions or followups. Do not capture routine edits, raw command output, or unverified hypotheses. Mention saved Mink note paths in the final response.
