#!/usr/bin/env bash
# Build and push the two custom app images we maintain in this repo.
#
# Prerequisites:
#   - Docker (or Podman) on the machine running this script.
#   - Network reachability to registry.vanillax.me (internal gateway at
#     192.168.10.50, or Cloudflare tunnel from outside the LAN).
#   - No auth needed — the in-cluster registry at kube-system/registry:5000
#     is anonymous-push.
#
# What gets built:
#   <registry>/news-reader        (Next.js RSS reader UI)
#   <registry>/temporal-worker    (Python Temporal worker)
#   <registry>/basemap-bootstrap  (radar-ng Protomaps extract wrapper)
#
# Usage (TAG is required — no :latest; manifests pin version tags so the
# manifest and the image move atomically through git):
#   TAG=v1.0.0 ./scripts/build-push-custom-apps.sh basemap-bootstrap
#   TAG=v1.2.3 ./scripts/build-push-custom-apps.sh   # build+push all

set -euo pipefail

REGISTRY="${REGISTRY:-ghcr.io/mitchross}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME="${RUNTIME:-docker}"  # override with RUNTIME=podman if preferred
# Cluster nodes are amd64; an arm64 Mac's default build arch would push an
# image the cluster can't exec. Override only for local experiments.
PLATFORM="${PLATFORM:-linux/amd64}"

TAG="${TAG:?TAG is required (e.g. TAG=v1.0.0). Version tags only — no :latest; pin the same tag in the consuming manifest.}"

# Map: app-name => "<context-relative-path>;<dockerfile-relative-path>"
declare -A APPS=(
  [news-reader]="my-apps/development/news-reader/app;my-apps/development/news-reader/app/Dockerfile"
  [temporal-worker]="my-apps/development/temporal-worker;my-apps/development/temporal-worker/Dockerfile"
  [basemap-bootstrap]="my-apps/development/radar-ng/basemap-bootstrap-image;my-apps/development/radar-ng/basemap-bootstrap-image/Dockerfile"
)

build_push() {
  local name="$1"
  local spec="${APPS[$name]}"
  local ctx="${spec%%;*}"
  local dockerfile="${spec##*;}"
  local tag="${REGISTRY}/${name}:${TAG}"

  echo ""
  echo "────────────────────────────────────────────────────────"
  echo "  Building $tag"
  echo "  context:    $ctx"
  echo "  dockerfile: $dockerfile"
  echo "────────────────────────────────────────────────────────"

  "$RUNTIME" build \
    --platform "$PLATFORM" \
    -t "$tag" \
    -f "$REPO_ROOT/$dockerfile" \
    "$REPO_ROOT/$ctx"

  echo ""
  echo "[push] $tag"
  "$RUNTIME" push "$tag"

  echo "[done] $name"
}

if [[ $# -eq 0 ]]; then
  targets=("${!APPS[@]}")
else
  targets=("$@")
fi

for t in "${targets[@]}"; do
  if [[ -z "${APPS[$t]:-}" ]]; then
    echo "ERROR: unknown app '$t'. valid: ${!APPS[*]}" >&2
    exit 2
  fi
  build_push "$t"
done

echo ""
echo "════════════════════════════════════════════════════════"
echo "  All pushes complete."
echo ""
echo "  Pick up the new image:"
for t in "${targets[@]}"; do
  if [[ "$t" == "basemap-bootstrap" ]]; then
    # ArgoCD Sync-hook Job with a pinned tag: deploying = bumping the tag
    # in git. The marker gate keeps the re-run cheap unless REFRESH/BBOX
    # changed.
    echo "    bump image tag to :${TAG} in my-apps/development/radar-ng/job-basemap-bootstrap.yaml, commit + push"
  else
    echo "    pin :${TAG} in the $t manifest, commit + push (or kubectl rollout restart -n $t deploy/$t if still on :latest)"
  fi
done
echo "════════════════════════════════════════════════════════"
