#!/usr/bin/env bash
# Squash-merge every open PR that GitHub reports as ready. Usage: merge-open-prs.sh [--dry-run] [--force]
# --force skips the CI state filter and attempts every open PR; conflicted PRs still fail.
set -euo pipefail

dry_run=false
force=false
for arg in "$@"; do
  case "$arg" in
    --dry-run) dry_run=true ;;
    --force) force=true ;;
    *) echo "Usage: $0 [--dry-run] [--force]" >&2; exit 2 ;;
  esac
done

repo=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
prs=$(gh pr list --repo "$repo" --state open --limit 200 \
  --json number,mergeStateStatus,title \
  --jq '.[] | [.number, .mergeStateStatus, .title] | @tsv')

if [[ -z "$prs" ]]; then
  echo "No open PRs in $repo."
  exit 0
fi

merged=0 skipped=0 failed=0
while IFS=$'\t' read -r number state title; do
  # The state is read at run start: non-required checks never block, a real conflict fails below.
  # --force attempts every PR and annotates the bypassed state; --dry-run never merges.
  case "$state" in
    CLEAN | HAS_HOOKS) note="" ;;
    *)
      if "$force"; then
        # Bypass a non-clean state; the merge below still fails on a real conflict.
        note=" [$state]"
      else
        echo "SKIP   #$number [$state] $title"
        skipped=$((skipped + 1))
        continue
      fi
      ;;
  esac

  if "$dry_run"; then
    echo "WOULD  #$number$note $title"
  elif output=$(gh pr merge "$number" --repo "$repo" --squash --delete-branch 2>&1 </dev/null); then
    echo "MERGED #$number$note $title"
    merged=$((merged + 1))
  else
    echo "FAILED #$number$note $title: $output"
    failed=$((failed + 1))
  fi
done <<<"$prs"

echo "Done: $merged merged, $skipped skipped, $failed failed."
[[ "$failed" -eq 0 ]]
