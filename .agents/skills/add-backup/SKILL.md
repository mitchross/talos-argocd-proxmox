---
name: add-backup
description: Add kopiur backup to one or more PVCs in this talos-argocd-proxmox repo (SnapshotPolicy + SnapshotSchedule + Restore stub, the kopiur-backup component, restore-before-bind dataSourceRef). Use when asked to back up an app's PVC or add a PVC that needs backups.
---

# Add a backup

The procedure lives in `.claude/commands/add-backup.md` (shared with Claude Code).
Read it and follow it exactly, treating `$ARGUMENTS` as the app path the user gave
(for example `my-apps/home/paperless-ngx`).

Before writing the PVC, pick its storage class with the `place-storage` skill.
NAS (`truenas-nfs`) volumes use `copyMethod: Direct`; see `my-apps/media/immich/kustomization.yaml`.
