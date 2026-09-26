#!/bin/sh
# One-time top-up copy: old Longhorn `library` (/old) -> NAS `library-nas` (/new).
# The kopiur restore already filled /new from the last backup; this copies only files added since then.
set -eu

MARKER=/new/.migrated-from-longhorn

if [ -f "$MARKER" ]; then
  echo "[migrate] $MARKER exists, copy already done: $(cat "$MARKER")"
  exit 0
fi

apk add --no-cache rsync >/dev/null

# -rlt keeps folders, links and timestamps; ownership is irrelevant because the NAS maps every client to root.
# --ignore-existing never overwrites a restored file, so the copy is safe to re-run.
rsync -rlt --ignore-existing --exclude=/lost+found --info=stats1 /old/ /new/

date -u +%Y-%m-%dT%H:%M:%SZ > "$MARKER"
echo "[migrate] copy finished"
