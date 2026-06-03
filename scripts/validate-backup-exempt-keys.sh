#!/usr/bin/env bash
# Guard against the pvc-plumber backup-exempt admission contract drifting.
#
# Why this exists:
#   pvc-plumber v2.1+ enforces, at PVC admission (CREATE only), that any PVC
#   carrying the label `backup-exempt: "true"` ALSO carries the annotation
#   `storage.vanillax.dev/backup-exempt-reason`. The annotation key MUST be
#   fully qualified — the bare key `backup-exempt-reason` is NOT recognized
#   and the validating webhook denies the PVC.
#
#   Because the webhook is CREATE-only, an existing PVC with the wrong key
#   keeps running and looks fine. The bug only detonates when the PVC is
#   recreated: app delete/re-add, namespace rebuild, or full cluster DR.
#   That is the worst possible time to discover it. This script makes the
#   contract violation fail in CI instead of during a recovery.
#
# Exit 1 if any PVC manifest has `backup-exempt: "true"` but is missing the
# fully-qualified `storage.vanillax.dev/backup-exempt-reason` annotation
# (including the case where only the bare key is present).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

FQ_KEY="storage.vanillax.dev/backup-exempt-reason"
fail=0

# 1. Bare key anywhere is always wrong — the operator ignores it.
while IFS= read -r hit; do
  [ -z "$hit" ] && continue
  echo "ERROR: bare 'backup-exempt-reason' key (operator requires '${FQ_KEY}'):"
  echo "       $hit"
  fail=1
done < <(grep -rn --include='*.yaml' -E '^[[:space:]]+backup-exempt-reason:' \
           manifests/apps/ manifests/infra/ manifests/database/ 2>/dev/null || true)

# 2. Every file that marks a PVC backup-exempt must carry the FQ reason key.
#    (File-level check: PVCs share files; this catches a labeled PVC whose
#    file has no FQ reason annotation at all.)
while IFS= read -r f; do
  [ -z "$f" ] && continue
  if ! grep -qE "^[[:space:]]+${FQ_KEY//./\\.}:" "$f"; then
    echo "ERROR: '$f' has backup-exempt:\"true\" but no '${FQ_KEY}' annotation"
    fail=1
  fi
done < <(grep -rln --include='*.yaml' -E '^[[:space:]]+backup-exempt:[[:space:]]*"true"' \
           manifests/apps/ manifests/infra/ manifests/database/ 2>/dev/null || true)

if [ "$fail" -ne 0 ]; then
  echo
  echo "FAIL: backup-exempt contract violation (see docs/volsync-storage-recovery.md)."
  echo "Fix: label 'backup-exempt: \"true\"' requires annotation"
  echo "     '${FQ_KEY}: \"<why this PVC is safe to not back up>\"'"
  exit 1
fi

echo "OK: all backup-exempt PVCs use the fully-qualified ${FQ_KEY} annotation."
