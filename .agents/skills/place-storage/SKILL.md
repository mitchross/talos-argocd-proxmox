---
name: place-storage
description: Decide where a PVC's data should live in this homelab (longhorn, longhorn-flash, longhorn-wired-ha, truenas-nfs, or an existing NAS share) and how big to make it, so consumer SSDs don't wear out and backup clones don't run out of room. Use before writing or resizing any PVC, or when asked where data is stored.
---

# Place storage

The procedure lives in `.claude/commands/place-storage.md` (shared with Claude Code).
Read it and follow it, treating `$ARGUMENTS` as the app or PVC the user named.
The current disk layout is `docs/domains/storage/disk-map.md`.
