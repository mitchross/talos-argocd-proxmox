#!/usr/bin/env bash
# Tick finding lines on an audit epic after their PR merged.
# Usage: tick_epic.sh <owner/repo> <epic-number> <ID> [<ID> ...]
# Turns '- [ ] **ID**:' into '- [x] **ID**:' and prints the ticked count.
set -euo pipefail
R=$1; EPIC=$2; shift 2
body=$(gh issue view "$EPIC" -R "$R" --json body --jq .body)
for id in "$@"; do
  body=$(printf '%s' "$body" | sed -E "s/^- \[ \] \*\*$id\*\*:/- [x] **$id**:/")
done
gh issue edit "$EPIC" -R "$R" --body "$body" >/dev/null
echo "ticked: $(gh issue view "$EPIC" -R "$R" --json body --jq .body | grep -c '^- \[x\]')"
