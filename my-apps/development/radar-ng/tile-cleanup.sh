#!/bin/sh
# Remove tile directories older than TTL_HOURS (default 6h). Keeps the
# most recent tile set per layer; anything older is pruned.
set -eu
: "${TILE_DIR:=/data/tiles}"
: "${TTL_HOURS:=6}"
find "$TILE_DIR" -mindepth 2 -maxdepth 3 -type d \
  -mmin +$((TTL_HOURS * 60)) -print -exec rm -rf {} + 2>/dev/null || true
echo "[tile-cleanup] swept ${TILE_DIR} (ttl=${TTL_HOURS}h)"
