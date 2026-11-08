#!/bin/sh
# Prunes rebuildable build output inside agent worktrees and workspace checkouts. It never deletes
# a worktree, a checkout or a commit: only `target/` and `node_modules/`, which the next build or
# install recreates.
#
# Why: coding agents keep one worktree per feature under agent-worktrees and full repo checkouts
# under workspace, including nested monorepo crates and apps (e.g. `rust/target`, `web/node_modules`).
# Seven parallel Rust worktrees wrote 79Gi in one hour and filled the 100Gi volume on 2026-10-31,
# which broke every Hermes write until the volume was expanded.
set -eu

roots="${WORKTREE_ROOTS:-${WORKTREE_ROOT:-/opt/data/home/.local/share/agent-worktrees} /opt/data/workspace}"
idle_hours="${IDLE_HOURS:-6}"
interval="${INTERVAL_SECONDS:-3600}"
max_depth="${MAX_DEPTH:-4}"

prune() {
  idle_min=$((idle_hours * 60))
  free_before=""
  for r in $roots; do
    if [ -d "$r" ]; then
      free_before=$(df -Pk "$r" | awk 'NR==2 {print $4}')
      break
    fi
  done
  [ -n "$free_before" ] || { echo "[gc] no watched roots exist ($roots); nothing to do"; return 0; }

  for r in $roots; do
    [ -d "$r" ] || continue
    find "$r" -maxdepth "$max_depth" -name .git -prune -o \( -name target -o -name node_modules \) -type d -prune -print 2>/dev/null | while IFS= read -r dir; do
      [ -d "$dir" ] || continue
      parent=$(dirname "$dir")
      base=$(basename "$dir")
      if [ "$base" = "target" ] && [ ! -f "$parent/Cargo.toml" ]; then
        continue
      fi
      if [ "$base" = "node_modules" ] && [ ! -f "$parent/package.json" ] && [ "$(basename "$parent")" != ".next" ]; then
        continue
      fi
      # A file touched inside the idle window means the tree may be in use. Keep it.
      if [ -n "$(find "$dir" -mmin "-$idle_min" -print -quit 2>/dev/null || true)" ]; then
        continue
      fi
      rm -rf "$dir" || { echo "[gc] could not remove $dir"; continue; }
      echo "[gc] removed $dir (idle over ${idle_hours}h)"
    done
  done

  for r in $roots; do
    if [ -d "$r" ]; then
      free_after=$(df -Pk "$r" | awk 'NR==2 {print $4}')
      echo "[gc] pass done; free KiB $free_before -> $free_after"
      break
    fi
  done
}

echo "[gc] watching $roots; idle window ${idle_hours}h; maxdepth $max_depth; every ${interval}s"
while :; do
  prune
  sleep "$interval"
done
