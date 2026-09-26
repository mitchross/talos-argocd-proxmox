---
name: new-database
description: Create a database for an app in this talos-argocd-proxmox repo using the only supported pattern, a plain Postgres Deployment inside the app directory backed up by kopiur. Use when an app needs Postgres. Never CNPG.
---

# Create a database

The procedure lives in `.claude/commands/new-database.md` (shared with Claude Code).
Read it and follow it exactly, treating `$ARGUMENTS` as the app name the user gave.
Reference implementation: `my-apps/development/gitea/postgres/`.

Databases always go on Longhorn (`longhorn` or `longhorn-wired-ha`), never NFS.
