#!/usr/bin/env bash
set -euo pipefail

readonly SEARCH_ROOTS=(infrastructure monitoring my-apps)
readonly BLOCK_PATTERN='(^[[:space:]]*-[[:space:]]*[|>][-+]?[[:space:]]*$)|(^[[:space:]]*(command|args):[[:space:]]*[|>][-+]?[[:space:]]*$)'

# grep exits 0 on a match, 1 on none, >1 on error; only 1 is a pass.
status=0
matches="$(grep -rEn --include='*.yaml' --include='*.yml' -e "$BLOCK_PATTERN" "${SEARCH_ROOTS[@]}")" || status=$?

if [ "$status" -eq 0 ]; then
  echo "ERROR: executable-style YAML block bodies are not allowed:"
  echo "$matches"
  echo "Move the program into the owning app's scripts/ directory, generate a ConfigMap, and mount it read-only."
  exit 1
elif [ "$status" -ne 1 ]; then
  echo "ERROR: grep failed with exit code $status; the check did not run."
  exit "$status"
fi

echo "No inline executable YAML block bodies found."
