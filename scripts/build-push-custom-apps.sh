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
#   registry.vanillax.me/news-reader:latest      (Next.js RSS reader UI)
#   registry.vanillax.me/temporal-worker:latest  (Python Temporal worker)
#
# After push, the two pending pods auto-heal once kubelet retries the pull:
#   kubectl rollout restart -n news-reader      deploy/news-reader
#   kubectl rollout restart -n temporal-worker  deploy/temporal-worker
#
# Usage:
#   ./scripts/build-push-custom-apps.sh              # build+push both
#   ./scripts/build-push-custom-apps.sh news-reader  # just news-reader
#   ./scripts/build-push-custom-apps.sh temporal-worker

set -euo pipefail

REGISTRY="${REGISTRY:-registry.vanillax.me}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME="${RUNTIME:-docker}"  # override with RUNTIME=podman if preferred

# Map: app-name => "<context-relative-path>;<dockerfile-relative-path>"
declare -A APPS=(
  [news-reader]="my-apps/development/news-reader/app;my-apps/development/news-reader/app/Dockerfile"
  [temporal-worker]="my-apps/development/temporal-worker;my-apps/development/temporal-worker/Dockerfile"
)

build_push() {
  local name="$1"
  local spec="${APPS[$name]}"
  local ctx="${spec%%;*}"
  local dockerfile="${spec##*;}"
  local tag="${REGISTRY}/${name}:latest"

  echo ""
  echo "────────────────────────────────────────────────────────"
  echo "  Building $tag"
  echo "  context:    $ctx"
  echo "  dockerfile: $dockerfile"
  echo "────────────────────────────────────────────────────────"

  "$RUNTIME" build \
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
echo "  Restart the pods so kubelet pulls the new image:"
for t in "${targets[@]}"; do
  echo "    kubectl rollout restart -n $t deploy/$t"
done
echo "════════════════════════════════════════════════════════"
