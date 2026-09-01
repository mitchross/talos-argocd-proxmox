#!/bin/sh
set -eu
TARGET="/data/${TARGET_FILE}"
TMP="${TARGET}.tmp"
MARKER="/data/.bootstrap-marker"

# Fast path: the hook re-runs every sync; a marker matching DATASET_URL means nothing to do.
if [ -s "$TARGET" ] && [ -f "$MARKER" ] && [ "$(head -n1 "$MARKER")" = "$DATASET_URL" ]; then
  echo "marker matches (${DATASET_URL}); archive already present, nothing to do"
  exit 0
fi

# The origin drops long single streams; restarting from byte 0 never finishes 62GB, so resume with wget -c.
# A stale partial from a different DATASET_URL is caught by the sha256 check (mismatch deletes the tmp).
echo "downloading ${DATASET_URL} -> ${TMP}"
attempt=0
while ! wget -q -c -O "$TMP" "$DATASET_URL"; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 200 ]; then
    echo "FATAL: download did not complete after ${attempt} resume attempts" >&2
    exit 1
  fi
  echo "connection dropped at $(wc -c <"$TMP" 2>/dev/null || echo 0) bytes, resuming (attempt ${attempt})"
  sleep 5
done

echo "verifying sha256 (${DATASET_SHA256_URL})"
EXPECTED="$(wget -q -O - "$DATASET_SHA256_URL" | cut -d' ' -f1)"
ACTUAL="$(sha256sum "$TMP" | cut -d' ' -f1)"
if [ "$EXPECTED" != "$ACTUAL" ]; then
  echo "FATAL: sha256 mismatch: expected ${EXPECTED}, got ${ACTUAL}" >&2
  rm -f "$TMP"
  exit 1
fi

# Atomic swap (same filesystem); a running server keeps the OLD file open until the Deployment restarts.
mv -f "$TMP" "$TARGET"
printf '%s\nsize=%s downloaded=%s\n' "$DATASET_URL" "$(wc -c <"$TARGET")" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$MARKER"
echo "done: ${TARGET} ($(wc -c <"$TARGET") bytes)"

