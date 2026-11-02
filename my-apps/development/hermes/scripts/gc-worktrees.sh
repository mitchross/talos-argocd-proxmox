#!/bin/sh
# Prunes rebuildable build output inside agent worktrees. It never deletes a worktree, a checkout
# or a commit: only `target/` and `node_modules/`, which the next build or install recreates.
#
# Why: coding agents keep one worktree per feature under agent-worktrees. Seven parallel Rust
# worktrees wrote 79Gi in one hour and filled the 100Gi volume on 2026-10-31, which broke every
# Hermes write until the volume was expanded.
set -eu

root="${WORKTREE_ROOT:-/opt/data/home/.local/share/agent-worktrees}"
idle_hours="${IDLE_HOURS:-6}"
interval="${INTERVAL_SECONDS:-3600}"
build_dirs="${BUILD_DIRS:-target node_modules}"

prune() {
  [ -d "$root" ] || { echo "[gc] $root is absent; nothing to do"; return 0; }
  idle_min=$((idle_hours * 60))
  free_before=$(df -Pk "$root" | awk 'NR==2 {print $4}')
  for repo in "$root"/*/; do
    [ -d "$repo" ] || continue
    for wt in "$repo"*/; do
      [ -d "$wt" ] || continue
      for name in $build_dirs; do
        dir="$wt$name"
        [ -d "$dir" ] || continue
        # A file touched inside the idle window means the tree may be in use. Keep it.
        if [ -n "$(find "$dir" -mmin "-$idle_min" -print -quit 2>/dev/null || true)" ]; then
          continue
        fi
        rm -rf "$dir" || { echo "[gc] could not remove $dir"; continue; }
        echo "[gc] removed $dir (idle over ${idle_hours}h)"
      done
    done
  done
  free_after=$(df -Pk "$root" | awk 'NR==2 {print $4}')
  echo "[gc] pass done; free KiB $free_before -> $free_after"
}

echo "[gc] watching $root; idle window ${idle_hours}h; dirs: $build_dirs; every ${interval}s"
while :; do
  prune
  sleep "$interval"
done
