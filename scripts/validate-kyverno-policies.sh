#!/usr/bin/env bash
# Validates Kyverno generate policies for dangerous settings that cause API server overload.
# Used by: CI pipeline, pre-commit hook
#
# background: true → continuous background scanning (~30s loop)
# mutateExistingOnPolicyUpdate: true → re-evaluates ALL matching resources on policy change
# synchronize: true → drift watchers create UpdateRequests on every controller status update
# All three caused a 23-hour API server overload incident (2026-03-25).
set -euo pipefail

ERRORS=0

for file in $(grep -rl 'kind: ClusterPolicy\|kind: Policy' infrastructure/controllers/kyverno/ --include='*.yaml' 2>/dev/null); do
  grep -q 'generate:' "$file" || continue

  if grep -q 'background: true' "$file"; then
    echo "ERROR: ${file}"
    echo "  background: true on generate policy causes API server overload."
    echo "  Use: background: false"
    echo ""
    ERRORS=$((ERRORS + 1))
  fi

  if grep -q 'mutateExistingOnPolicyUpdate: true' "$file"; then
    echo "ERROR: ${file}"
    echo "  mutateExistingOnPolicyUpdate: true re-evaluates ALL matching resources on any policy change."
    echo "  Use: mutateExistingOnPolicyUpdate: false"
    echo ""
    ERRORS=$((ERRORS + 1))
  fi

  if grep -q 'synchronize: true' "$file"; then
    echo "ERROR: ${file}"
    echo "  synchronize: true creates drift watchers that generate UpdateRequests on every controller update."
    echo "  Use: synchronize: false"
    echo ""
    ERRORS=$((ERRORS + 1))
  fi
done

if [ "$ERRORS" -gt 0 ]; then
  echo "Found ${ERRORS} dangerous Kyverno policy setting(s)."
  echo "See: infrastructure/controllers/kyverno/CLAUDE.md"
  exit 1
fi

echo "Kyverno generate policies: OK"
