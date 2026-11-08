#!/bin/sh
# Prunes rebuildable build output in agent worktrees and workspace checkouts, one or two levels down
# (`<wt>/target`, `<wt>/rust/target`, `<wt>/web/node_modules`). It never deletes a worktree, a checkout
# or a commit, and keeps anything touched within the idle window.
#
# Why: coding agents keep one worktree per feature under agent-worktrees. Seven parallel Rust
# worktrees wrote 79Gi in one hour and filled the 100Gi volume on 2026-10-31, which broke every
# Hermes write until the volume was expanded.
set -eu

root="${WORKTREE_ROOT:-/opt/data/home/.local/share/agent-worktrees}"
workspace="${WORKSPACE_ROOT:-/opt/data/workspace}"
cargo_build="${CARGO_BUILD_ROOT:-/opt/scratch/cargo-build}"
idle_hours="${IDLE_HOURS:-6}"
scratch_idle_hours="${SCRATCH_IDLE_HOURS:-72}"
interval="${INTERVAL_SECONDS:-3600}"
build_dirs="${BUILD_DIRS:-target node_modules .next}"

# Removes $1 unless a file inside changed in the last $2 minutes.
prune_idle() {
  if [ -n "$(find "$1" -mmin "-$2" -print -quit 2>/dev/null || true)" ]; then
    return 0
  fi
  rm -rf "$1" || { echo "[gc] could not remove $1"; return 0; }
  echo "[gc] removed $1"
}

prune() {
  idle_min=$((idle_hours * 60))
  free_before=$(df -Pk /opt/data | awk 'NR==2 {print $4}')
  for wt in "$root"/*/*/ "$workspace"/*/; do
    [ -d "$wt" ] || continue
    for name in $build_dirs; do
      for dir in "$wt$name" "$wt"*/"$name"; do
        { [ -d "$dir" ] && [ ! -L "$dir" ]; } || continue
        # Skip nested hits such as node_modules/<pkg>/target.
        case "${dir#"$wt"}" in node_modules/* | target/*) continue ;; esac
        # Cargo marks its own target dirs with CACHEDIR.TAG; a source folder named target has none.
        if [ "$name" = target ] && [ ! -f "$dir/CACHEDIR.TAG" ]; then continue; fi
        prune_idle "$dir" "$idle_min"
      done
    done
  done
  # CARGO_BUILD_BUILD_DIR keeps one dir per workspace path; drop the ones no build used for days.
  for dir in "$cargo_build"/*/*/; do
    [ -d "$dir" ] && prune_idle "${dir%/}" $((scratch_idle_hours * 60))
  done
  free_after=$(df -Pk /opt/data | awk 'NR==2 {print $4}')
  echo "[gc] pass done; /opt/data free KiB $free_before -> $free_after"
}

echo "[gc] watching $root and $workspace; idle ${idle_hours}h; dirs: $build_dirs; cargo build dirs idle ${scratch_idle_hours}h"
while :; do
  prune
  sleep "$interval"
done
