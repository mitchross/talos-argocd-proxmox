#!/usr/bin/env bash
set -euo pipefail

# Fix legacy Longhorn CRD conversion fields left from older installs
# Error addressed:
#   spec.conversion.strategy: Required value
#   spec.conversion.webhookClientConfig: Forbidden when strategy != Webhook
# Strategy: remove deprecated spec.conversion.webhookClientConfig and ensure strategy: None

require() {
  command -v "$1" >/dev/null 2>&1 || { echo "FATAL: missing dependency: $1"; exit 1; }
}

require kubectl

# Target only Longhorn CRDs (compatible with macOS bash 3.2)
CRDS="$(kubectl get crd -l app.kubernetes.io/name=longhorn -o name || true)"

if [ -z "${CRDS}" ]; then
  echo "No Longhorn CRDs found. Nothing to do."
  exit 0
fi

echo "Fixing CRD conversion blocks for: ${CRDS}"
for crd in ${CRDS}; do
  name=${crd#*/}
  echo "- ${name}: setting conversion.strategy=None and removing legacy fields in one patch"
  kubectl patch "${crd}" --type=merge -p='{
    "spec": {
      "conversion": {
        "strategy": "None",
        "webhookClientConfig": null,
        "conversionReviewVersions": null,
        "webhook": null
      }
    }
  }'

done

echo "Done. Verify with: kubectl get crd -o jsonpath='{range .items[?(@.metadata.labels."app.kubernetes.io/name"=="longhorn")]}{.metadata.name}{": "}{.spec.conversion.strategy}{"\n"}{end}'"
