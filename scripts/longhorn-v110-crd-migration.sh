#!/usr/bin/env bash
set -euo pipefail

# Longhorn v1.10 pre-upgrade CRD storage migration helper
# This script follows the release notes instructions to ensure all storedVersions are v1beta2.

NS=${NS:-longhorn-system}
WEBHOOK=longhorn-webhook-validator

require() {
  command -v "$1" >/dev/null 2>&1 || { echo "FATAL: missing dependency: $1"; exit 1; }
}

require kubectl
require jq

echo "Temporarily disabling Longhorn settings UPDATE validation in webhook..."
kubectl patch validatingwebhookconfiguration ${WEBHOOK} \
  --type=merge \
  -p "$(kubectl get validatingwebhookconfiguration ${WEBHOOK} -o json | \
    jq '.webhooks[0].rules |= map(if .apiGroups == ["longhorn.io"] and .resources == ["settings"] then .operations |= map(select(. != "UPDATE")) else . end)')"

migration_time="$(date +%Y-%m-%dT%H:%M:%S)"
echo "Finding Longhorn CRDs with stored v1beta1 resources..."
mapfile -t crds < <(kubectl get crd -l app.kubernetes.io/name=longhorn -o json | jq -r '.items[] | select(.status.storedVersions | index("v1beta1")) | .metadata.name')

if [ ${#crds[@]} -eq 0 ]; then
  echo "No CRDs report v1beta1 in storedVersions. Skipping migration."
else
  echo "CRDs to migrate: ${crds[*]}"
  for crd in "${crds[@]}"; do
    echo "Migrating ${crd} ..."
    mapfile -t names < <(kubectl -n "${NS}" get "${crd}" -o jsonpath='{.items[*].metadata.name}') || true
    for name in "${names[@]:-}"; do
      echo "  Patching ${crd}/${name} with migration-time annotation"
      kubectl patch "${crd}" "${name}" -n "${NS}" --type=merge -p='{"metadata":{"annotations":{"migration-time":"'"${migration_time}"'"}}}' || true
    done
    echo "  Cleaning up storedVersions to [\"v1beta2\"] for CRD ${crd}"
    kubectl patch crd "${crd}" --type=merge -p '{"status":{"storedVersions":["v1beta2"]}}' --subresource=status
  done
fi

echo "Re-enabling Longhorn settings UPDATE validation in webhook..."
kubectl patch validatingwebhookconfiguration ${WEBHOOK} \
  --type=merge \
  -p "$(kubectl get validatingwebhookconfiguration ${WEBHOOK} -o json | \
    jq '.webhooks[0].rules |= map(if .apiGroups == ["longhorn.io"] and .resources == ["settings"] then .operations |= (. + ["UPDATE"] | unique) else . end)')"

echo "Verifying storedVersions for Longhorn CRDs..."
kubectl get crd -l app.kubernetes.io/name=longhorn -o=jsonpath='{range .items[*]}{.metadata.name}{": "}{.status.storedVersions}{"\n"}{end}'

echo "Done. Ensure all entries list only [\"v1beta2\"]. If not, investigate and retry."
