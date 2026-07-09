#!/usr/bin/env bash
# Merge all open PRs in the repo with squash merge + auto-delete branch.
# Safe to re-run: already-merged PRs are skipped by `--state open`.
# PRs with failing CI checks will fail individually — the script continues.
set -euo pipefail

REPO="mitchross/talos-argocd-proxmox"
MERGE_STRATEGY="squash"

echo "Fetching open PRs from $REPO ..."
PR_NUMBERS=$(gh pr list --repo "$REPO" --state open --json number --jq '.[].number')

if [[ -z "$PR_NUMBERS" ]]; then
  echo "No open PRs found. Nothing to do."
  exit 0
fi

TOTAL=$(echo "$PR_NUMBERS" | wc -l | tr -d ' ')
MERGED=0
FAILED=0
SKIPPED=0

echo "Found $TOTAL open PR(s). Merging with '$MERGE_STRATEGY' strategy..."
echo "-------------------------------------------------------"

for NUM in $PR_NUMBERS; do
  TITLE=$(gh pr view "$NUM" --repo "$REPO" --json title --jq '.title')
  STATE=$(gh pr view "$NUM" --repo "$REPO" --json mergeStateStatus --jq '.mergeStateStatus')

  echo -n "PR #$NUM ($STATE): $TITLE ... "

  OUTPUT=$(gh pr merge "$NUM" --repo "$REPO" --squash --delete-branch 2>&1)
  if [[ $? -eq 0 ]]; then
    echo "✓ merged"
    ((MERGED++))
  else
    # Could be already merged, conflict, or failing checks
    echo "✗ $OUTPUT"
    ((FAILED++))
  fi
done

echo "-------------------------------------------------------"
echo "Done: $MERGED merged, $FAILED failed out of $TOTAL total."