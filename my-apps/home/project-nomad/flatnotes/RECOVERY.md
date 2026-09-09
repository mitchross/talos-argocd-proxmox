# Flatnotes search-index recovery

The September 9, 2026 live failure is the Whoosh TOC EOF error
`ord() expected a character, but string of length 0 found`. Markdown notes remain
the source of truth. Upstream [documents rebuilding `.flatnotes` while the app is
stopped](https://github.com/dullage/flatnotes/wiki#what-is-the-flatnotes-sub-folder-for).

The Recreate Deployment runs the same application image in an init container,
tries opening index schema `5`, and preserves the index only for that exact
observed exception. Unexpected layouts, symlinks, other exceptions and low disk
headroom stop init without moving the index. A healthy or absent index is left
alone. Before rename it exclusively creates
`/data/.flatnotes-recovery-20260909`, writes SHA-256 hashes, and then atomically
moves `.flatnotes` to that directory's `index` child on the same PVC. No original
index byte or Markdown file is deleted. Normal startup rebuilds the index from
notes, using the upstream implementation. The archive remains on the backed-up
PVC until deliberately removed after verification.

Acceptance: startup/readiness succeed; existing notes open and representative
searches find their content; compare note counts and check the retained archive
hashes. The new probes expose startup failure rather than reporting a process as
healthy. A restart after successful recovery opens the healthy rebuilt index and
makes no further archive. An interrupted preservation with an existing archive
and still-corrupt source fails closed; inspect it instead of removing the guard.

Rollback requires stopping Flatnotes, preserving any new index separately and
moving the retained index back to `.flatnotes`. That intentionally reproduces
the old search failure; Markdown notes are unchanged either way.
