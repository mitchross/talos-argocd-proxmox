#!/bin/sh
set -eu
apk add --no-cache jq >/dev/null
SEED=/seed/config.json
DEST=/data/config.json
mkdir -p /data
if [ ! -s "$DEST" ]; then
  echo "[seed] fresh PVC, writing config.json verbatim"
  cp "$SEED" "$DEST"
else
  echo "[seed] merging modelProviders + search from seed into existing config.json"
  jq --slurpfile seed "$SEED" \
     '.modelProviders = $seed[0].modelProviders
      | .search = $seed[0].search' \
     "$DEST" > "$DEST.tmp"
  mv "$DEST.tmp" "$DEST"
fi
echo "[seed] done. providers now:"
jq -r '.modelProviders[] | "  - \(.name) (\(.type)) — \(.chatModels | length) models"' "$DEST"

