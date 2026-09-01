#!/usr/bin/env bash
set -euo pipefail

readonly SEARCH_ROOTS=(infrastructure monitoring my-apps)
readonly BLOCK_PATTERN='(^[[:space:]]*-[[:space:]]*[|>][-+]?[[:space:]]*$)|(^[[:space:]]*(command|args):[[:space:]]*[|>][-+]?[[:space:]]*$)'

if matches="$(rg -n --glob '*.yaml' --glob '*.yml' "$BLOCK_PATTERN" "${SEARCH_ROOTS[@]}")"; then
  echo "ERROR: executable-style YAML block bodies are not allowed:"
  echo "$matches"
  echo "Move the program into the owning app's scripts/ directory, generate a ConfigMap, and mount it read-only."
  exit 1
fi

echo "No inline executable YAML block bodies found."
