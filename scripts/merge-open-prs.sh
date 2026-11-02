#!/usr/bin/env bash
# Squash-merge every open PR that GitHub reports as ready. Usage: merge-open-prs.sh [--dry-run]
set -euo pipefail

dry_run=false
case "${1:-}" in
  "") ;;
  --dry-run) dry_run=true ;;
  *) echo "Usage: $0 [--dry-run]" >&2; exit 2 ;;
esac

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
  # GitHub accepts a merge when only non-required checks fail, so read the state first.
  # The state is from the start of the run: a conflict from an earlier merge fails at the merge below.
  case "$state" in
    CLEAN | HAS_HOOKS) ;;
    *)
      echo "SKIP   #$number [$state] $title"
      skipped=$((skipped + 1))
      continue
      ;;
  esac

  if "$dry_run"; then
    echo "WOULD  #$number $title"
  elif output=$(gh pr merge "$number" --repo "$repo" --squash --delete-branch 2>&1 </dev/null); then
    echo "MERGED #$number $title"
    merged=$((merged + 1))
  else
    echo "FAILED #$number $title: $output"
    failed=$((failed + 1))
  fi
done <<<"$prs"

echo "Done: $merged merged, $skipped skipped, $failed failed."
[[ "$failed" -eq 0 ]]
