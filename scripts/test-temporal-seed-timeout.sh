#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TMP/bin"

cat >"$TMP/bin/temporal" <<'STUB'
#!/bin/sh
/bin/sleep 99
STUB
chmod +x "$TMP/bin/temporal"

cat >"$TMP/bin/sleep" <<'STUB'
#!/bin/sh
exit 0
STUB
chmod +x "$TMP/bin/sleep"

set +e
PATH="$TMP/bin:$PATH" \
SEED_RETRIES=2 \
SEED_SLEEP_SECONDS=0 \
SEED_RPC_TIMEOUT_SECONDS=1 \
  timeout 5s sh "$ROOT/my-apps/development/temporal/scripts/seed-namespaces.sh" \
  >"$TMP/out" 2>"$TMP/err"
status=$?
set -e

if [[ "$status" -eq 0 ]]; then
  echo "expected seed script to fail when the Temporal CLI hangs" >&2
  exit 1
fi

if [[ "$status" -eq 124 ]]; then
  echo "seed script was not bounded; outer timeout killed it" >&2
  echo "--- stdout ---" >&2
  cat "$TMP/out" >&2
  echo "--- stderr ---" >&2
  cat "$TMP/err" >&2
  exit 1
fi

if ! grep -q "frontend did not become reachable" "$TMP/err"; then
  echo "expected bounded failure message, got:" >&2
  cat "$TMP/err" >&2
  exit 1
fi
