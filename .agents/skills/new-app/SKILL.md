---
name: new-app
description: Create a new ArgoCD-discovered application in this talos-argocd-proxmox repo (directory = Application, kustomization, namespace, Service with named ports, Gateway API HTTPRoute, 1Password ExternalSecret, VPA). Use when asked to add, deploy or scaffold an app.
---

# Create an app

The procedure lives in `.claude/commands/new-app.md` (shared with Claude Code).
Read it and follow it exactly, treating `$ARGUMENTS` as the target path the user
gave (for example `my-apps/media/jellyfin`). Directory rules: `my-apps/CLAUDE.md`.

If the app needs storage, pick the class with the `place-storage` skill first.
