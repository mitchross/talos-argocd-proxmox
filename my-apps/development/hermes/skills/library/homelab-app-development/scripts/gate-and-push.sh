#!/bin/bash
# Gate merged-but-uncommitted worktrees one at a time; commit + push only the ones that pass.
# Usage: gate-and-push.sh <worktree> [<worktree>...]   (run with terminal background=true, notify=true)
# Env: ENV_FILE (toolchain env to source), SUMMARY (summary file), MSG (merge commit message prefix).
# Gates are deal-scout's four; edit them for another repo.
ENV_FILE=${ENV_FILE:-/opt/data/tools/deal-scout-rust-env.sh}
SUMMARY=${SUMMARY:-/opt/data/cache/scratch/gate-and-push.txt}
MSG=${MSG:-Merge origin/master}
# shellcheck source=/dev/null
[ -f "$ENV_FILE" ] && source "$ENV_FILE"
for wt in "$@"; do
  cd "$wt" || { echo "$wt: cd failed" >> "$SUMMARY"; continue; }
  if git diff --name-only --diff-filter=U | grep -q .; then echo "$wt: unresolved conflicts" >> "$SUMMARY"; continue; fi
  L="/opt/data/cache/scratch/gates-$(basename "$wt")"; mkdir -p "$L"
  git add -u
  r=ok
  cargo fmt --all --check > "$L/fmt.log" 2>&1 || r=fmt
  [ $r = ok ] && { cargo clippy --workspace --all-targets --locked -- -D warnings > "$L/clippy.log" 2>&1 || r=clippy; }
  [ $r = ok ] && { cargo test --workspace --locked > "$L/test.log" 2>&1 || r=test; }
  [ $r = ok ] && { node --test dashboard/static/*.test.cjs > "$L/node.log" 2>&1 || r=node; }
  t=$(grep -E "^test result" "$L/test.log" 2>/dev/null | awk '{p+=$4;f+=$6} END {print p"/"f}')
  n=$(grep -oE "pass [0-9]+" "$L/node.log" 2>/dev/null | tail -1)
  if [ $r = ok ]; then
    git commit -q -m "$MSG into $(git branch --show-current)" && git push -q origin HEAD || r=push
  fi
  echo "$(basename "$wt"): $r rust(pass/fail)=$t node=$n logs=$L" >> "$SUMMARY"
done
