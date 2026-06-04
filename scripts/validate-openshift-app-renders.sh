#!/usr/bin/env bash
# validate-openshift-app-renders.sh - OpenShift app portability guardrails.

set -euo pipefail

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

RENDERED="$WORK_DIR/openshift-apps.yaml"
ERRORS=0
COUNT=0

fail() {
  echo "ERROR: $*"
  ERRORS=$((ERRORS + 1))
}

echo "=== OpenShift App Render Validation ==="

while IFS= read -r kustomization; do
  app_dir="${kustomization%/kustomization.yaml}"
  COUNT=$((COUNT + 1))
  if ! kustomize build --enable-helm "$app_dir" >>"$RENDERED"; then
    fail "render failed: $app_dir"
  fi
  echo "---" >>"$RENDERED"
done < <(find clusters/openshift/apps -name kustomization.yaml -print | sort)

if [ "$COUNT" -eq 0 ]; then
  fail "no OpenShift app overlays found"
fi

if rg -n 'pvc-plumber\.io|volsync\.backube|restore-policy:|dataSourceRef:' "$RENDERED"; then
  fail "OpenShift app renders contain Talos backup or restore policy"
fi

if rg -n 'storageClassName:\s*(longhorn|lvms-vg1)' "$RENDERED"; then
  fail "OpenShift app renders contain a cluster-specific local storage class"
fi

if rg -n 'name:\s*gateway-(internal|external)' "$RENDERED"; then
  fail "OpenShift app renders contain a Talos Gateway parentRef"
fi

if [ "$ERRORS" -gt 0 ]; then
  echo "FAILED: $ERRORS OpenShift render error(s)"
  exit 1
fi

echo "PASSED: $COUNT OpenShift app overlays render without Talos-only policy"
