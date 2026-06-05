#!/usr/bin/env bash
# validate-cluster-layout.sh - enforce the cluster-centric Kustomize layout.

set -euo pipefail

ERRORS=0

fail() {
  echo "ERROR: $*"
  ERRORS=$((ERRORS + 1))
}

echo "=== Cluster-Centric Kustomize Layout Validation ==="

while IFS= read -r path; do
  fail "legacy deploy-target entrypoint remains: $path"
done < <(find manifests -path '*/deploy-targets/*/kustomization.yaml' -print | sort)

while IFS= read -r path; do
  fail "Argo metadata must live under clusters/<cluster>: $path"
done < <(find manifests -path '*/.argocd/config.json' -print | sort)

while IFS= read -r path; do
  fail "app overlay metadata is derivable and must not remain: $path"
done < <(
  find clusters/talos/apps clusters/openshift/apps \
    -path '*/.argocd/config.json' -type f -print | sort
)

for cluster in talos openshift; do
  while IFS= read -r metadata; do
    source_path="$(
      python3 - "$metadata" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    print(json.load(fh).get("sourcePath", ""))
PY
    )"

    case "$source_path" in
      "clusters/$cluster/"*) ;;
      *) fail "$metadata sourcePath must start with clusters/$cluster/: $source_path" ;;
    esac
  done < <(find "clusters/$cluster" -path '*/.argocd/config.json' -print | sort)
done

while IFS= read -r path; do
  fail "OpenShift overlay imports Talos content: $path"
done < <(rg -l 'clusters/talos|\.\./talos' clusters/openshift --glob 'kustomization.yaml' || true)

while IFS= read -r path; do
  fail "OpenShift Gateway API resources must use *.gateway.apps.sno-ai-lab.vanillax.xyz: $path"
done < <(
  rg -n 'apps\.sno-ai-lab\.vanillax\.xyz' clusters/openshift --glob '*.{yaml,yml}' \
    | rg -v 'gateway\.apps\.sno-ai-lab\.vanillax\.xyz' || true
)

while IFS= read -r path; do
  fail "escaped inline patch string remains: $path"
done < <(
  rg -l 'patch:\s*".*\\n' clusters manifests --glob 'kustomization.yaml' || true
)

while IFS= read -r path; do
  fail "multiline inline patch remains: $path"
done < <(
  rg -l '^[[:space:]]+patch:[[:space:]]+\|[-+]?$' \
    clusters manifests --glob 'kustomization.yaml' || true
)

while IFS= read -r path; do
  fail "deprecated Kustomize patch field remains: $path"
done < <(
  rg -l '^[[:space:]]*(patchesStrategicMerge|patchesJson6902|bases):' \
    clusters manifests --glob 'kustomization.yaml' || true
)

while IFS= read -r path; do
  fail "manifest-generate-paths must not use a source-relative clusters/ path: $path"
done < <(rg -l 'manifest-generate-paths:[[:space:]]+clusters/' clusters --glob '*.yaml' || true)

while IFS= read -r path; do
  fail "manifest-generate-paths must include consumed shared bases: $path"
done < <(rg -l -F 'manifest-generate-paths: "{{.sourcePath}}"' clusters --glob '*.yaml' || true)

while IFS= read -r base; do
  relative_app="${base#manifests/apps/}"
  relative_app="${relative_app%/base}"
  for cluster in talos openshift; do
    if [ ! -f "clusters/$cluster/apps/$relative_app/kustomization.yaml" ]; then
      fail "missing $cluster overlay for shared app base: $base"
    fi
  done
done < <(find manifests/apps -mindepth 3 -maxdepth 3 -type d -name base | sort)

while IFS= read -r path; do
  fail "shared app base contains a cluster-specific local storage class: $path"
done < <(rg -l 'storageClass(Name)?:\s*(longhorn|lvms-vg1)' manifests/apps --glob '*.{yaml,yml}' || true)

if [ "$ERRORS" -gt 0 ]; then
  echo "FAILED: $ERRORS cluster layout error(s)"
  exit 1
fi

echo "PASSED: cluster layout is cluster-centric"
