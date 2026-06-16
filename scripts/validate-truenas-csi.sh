#!/usr/bin/env bash
# Validate the repository contract for the official TrueNAS CSI deployment.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DRIVER_DIR="infrastructure/storage/truenas-csi"
APPSET="infrastructure/controllers/argocd/apps/appsets/infrastructure-appset.yaml"
POLICY="infrastructure/networking/cilium/policies/block-lan-access.yaml"
# Match the CONTRACT, not a specific version: the official driver image must
# be the official repo, pinned to a semver tag AND a sha256 digest. Renovate
# owns the version+digest of this image, so hardcoding an exact value here
# made every Renovate bump fail this check and deadlock auto-merge repo-wide
# (the v1.0.4->v1.1.0 bump did exactly that). Asserting the format keeps the
# real intent (official + version-and-digest-pinned, never :latest/unpinned)
# while letting Renovate move the pin freely.
EXPECTED_IMAGE_RE='^[[:space:]]+image: ghcr\.io/truenas/truenas-csi:v[0-9]+\.[0-9]+\.[0-9]+@sha256:[0-9a-f]{64}$'
fail=0

check() {
  local description="$1"
  shift

  if "$@"; then
    printf 'OK: %s\n' "$description"
  else
    printf 'ERROR: %s\n' "$description" >&2
    fail=1
  fi
}

not_grep() {
  local pattern="$1"
  local file="$2"
  ! grep -qE "$pattern" "$file"
}

check "TrueNAS CSI kustomization exists" test -f "$DRIVER_DIR/kustomization.yaml"

if [ -f "$DRIVER_DIR/kustomization.yaml" ]; then
  rendered="$(mktemp)"
  trap 'rm -f "$rendered"' EXIT

  if ! kustomize build "$DRIVER_DIR" >"$rendered"; then
    echo "ERROR: failed to render $DRIVER_DIR" >&2
    exit 1
  fi

  check "official CSI driver is registered" \
    grep -qE '^  name: csi\.truenas\.io$' "$rendered"
  check "official driver image is version and digest pinned" \
    grep -qE "$EXPECTED_IMAGE_RE" "$rendered"
  check "NFS StorageClass uses the official provisioner" \
    grep -qE '^provisioner: csi\.truenas\.io$' "$rendered"
  check "NFS datasets stay under the dedicated parent" \
    grep -qE '^[[:space:]]+datasetPath: k8s/nfs/v$' "$rendered"
  check "NFS map-all identity behavior is explicit" \
    bash -c "grep -qE '^[[:space:]]+nfs\\.mapAllUser: root$' '$rendered' && grep -qE '^[[:space:]]+nfs\\.mapAllGroup: wheel$' '$rendered'"
  check "production StorageClass retains backend data" \
    grep -qE '^reclaimPolicy: Retain$' "$rendered"
  check "TrueNAS CSI API key is supplied by External Secrets" \
    grep -qE '^kind: ExternalSecret$' "$rendered"
  check "rendered Secret key is the driver env-var name (envFrom contract)" \
    grep -qE '^[[:space:]]+TRUENAS_API_KEY:.*apiKey' "$rendered"
  check "controller and node consume config via envFrom (no per-pod env copies)" \
    bash -c "[ \"\$(grep -cE '^[[:space:]]+envFrom:$' '$rendered')\" -eq 2 ] && ! grep -qE 'key: truenasURL' '$rendered'"
  check "credential source is the dedicated TrueNAS CSI item" \
    grep -qE '^[[:space:]]+key: truenas-csi$' "$rendered"
  check "canary PVC is not part of the Argo CD application" \
    not_grep '^kind: PersistentVolumeClaim$' "$rendered"
  check "iSCSI StorageClass is not enabled" \
    not_grep 'name: truenas-iscsi|protocol: "?iscsi' "$rendered"
  check "Democratic CSI is absent from rendered resources" \
    not_grep 'org\.democratic-csi' "$rendered"
fi

check "Argo CD deploys the TrueNAS CSI path" \
  grep -q -- '- path: infrastructure/storage/truenas-csi' "$APPSET"
check "Argo CD no longer deploys Democratic CSI" \
  not_grep 'infrastructure/storage/democratic-csi' "$APPSET"
check "Democratic CSI directory has been removed" \
  test ! -d infrastructure/storage/democratic-csi
check "Longhorn remains the default StorageClass" \
  grep -qE '^[[:space:]]*defaultClass:[[:space:]]*true' infrastructure/storage/longhorn/values.yaml
check "TrueNAS API TCP 443 is allowed by the LAN egress policy" \
  bash -c "awk '/ALLOW: TrueNAS/,/ALLOW: Wyze/' '$POLICY' | grep -qE 'port: \"443\"'"
check "iSCSI TCP 3260 is not opened in the TrueNAS policy block" \
  bash -c "! awk '/ALLOW: TrueNAS/,/ALLOW: Wyze/' '$POLICY' | grep -qE 'port: \"3260\"'"

if [ "$fail" -ne 0 ]; then
  echo
  echo "FAIL: official TrueNAS CSI repository contract is not satisfied."
  exit 1
fi

echo
echo "PASS: official TrueNAS CSI repository contract is satisfied."
