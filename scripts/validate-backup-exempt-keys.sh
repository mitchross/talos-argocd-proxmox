#!/usr/bin/env bash
# Guard against the pvc-plumber backup-exempt contract drifting.
#
# Why this exists:
#   The pvc-plumber v4 contract for exempting a PVC from backup is the
#   label `backup-exempt: "true"` PLUS the fully-qualified annotation
#   `storage.vanillax.dev/backup-exempt-reason`. The bare key
#   `backup-exempt-reason` is NOT recognized by the operator's label
#   parser — it classifies the PVC as ExemptMissingReason, which lands
#   in /audit as `needs-human-review` and (in any future strict mode)
#   would be denied at admission. v4.0.1 is a permissive reconciler with
#   no admission webhook, so in production the bare key surfaces only as
#   audit noise that masks real findings — exactly what happened on
#   2026-06-09, when two prometheus-stack PVCs sat in needs-human-review
#   because their exemption reasons used the bare key inside Helm values.
#   This script makes the contract violation fail in CI instead.
#
# Exit 1 if any manifest has `backup-exempt: "true"` but is missing the
# fully-qualified `storage.vanillax.dev/backup-exempt-reason` annotation
# (including the case where only the bare key is present).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

FQ_KEY="storage.vanillax.dev/backup-exempt-reason"
fail=0

# Every directory tree that holds Kubernetes manifests or Helm values.
# Helm values files count: chart-embedded volumeClaimTemplates (e.g.
# kube-prometheus-stack) carry the same label/annotation contract and
# were the 2026-06-09 blind spot when only my-apps/ and infrastructure/
# were scanned. docs/ and scripts/ are deliberately excluded (they may
# quote the bare key as an anti-pattern example).
MANIFEST_ROOTS=(my-apps/ infrastructure/ monitoring/)

# 1. Bare key anywhere is always wrong — the operator ignores it.
while IFS= read -r hit; do
  [ -z "$hit" ] && continue
  echo "ERROR: bare 'backup-exempt-reason' key (operator requires '${FQ_KEY}'):"
  echo "       $hit"
  fail=1
done < <(grep -rn --include='*.yaml' --include='*.yml' -E '^[[:space:]]+backup-exempt-reason:' \
           "${MANIFEST_ROOTS[@]}" 2>/dev/null || true)

# 2. Every file that marks a PVC backup-exempt must carry the FQ reason
#    key. (File-level check: PVCs share files; this catches a labeled
#    PVC whose file has no FQ reason annotation at all.)
while IFS= read -r f; do
  [ -z "$f" ] && continue
  if ! grep -qE "^[[:space:]]+${FQ_KEY//./\\.}:" "$f"; then
    echo "ERROR: '$f' has backup-exempt:\"true\" but no '${FQ_KEY}' annotation"
    fail=1
  fi
done < <(grep -rln --include='*.yaml' --include='*.yml' -E '^[[:space:]]+backup-exempt:[[:space:]]*"true"' \
           "${MANIFEST_ROOTS[@]}" 2>/dev/null || true)

if [ "$fail" -ne 0 ]; then
  echo
  echo "FAIL: backup-exempt contract violation (see docs/volsync-storage-recovery.md)."
  echo "Fix: label 'backup-exempt: \"true\"' requires annotation"
  echo "     '${FQ_KEY}: \"<why this PVC is safe to not back up>\"'"
  exit 1
fi

echo "OK: all backup-exempt PVCs use the fully-qualified ${FQ_KEY} annotation."
