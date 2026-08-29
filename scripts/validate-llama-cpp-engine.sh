#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_DIR="$ROOT_DIR/my-apps/ai/llama-cpp/beellama-image"
WORKFLOW="$ROOT_DIR/.github/workflows/llama-cpp-beellama-image.yml"
DEPLOYMENT="$ROOT_DIR/my-apps/ai/llama-cpp/deployment.yaml"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

[[ -f "$WORKFLOW" ]] || fail "missing Beellama image workflow"
[[ -f "$IMAGE_DIR/VERSION" ]] || fail "missing immutable Beellama image version"
[[ -f "$IMAGE_DIR/SOURCE_REF" ]] || fail "missing pinned Beellama source revision"

version="$(<"$IMAGE_DIR/VERSION")"
source_ref="$(<"$IMAGE_DIR/SOURCE_REF")"

[[ "$version" =~ ^beellama-staging-v[0-9]+\.[0-9]+\.[0-9]+-r[0-9]+-sm86$ ]] ||
  fail "VERSION must be an immutable Beellama release tag suffixed with -sm86"
[[ "$source_ref" =~ ^[0-9a-f]{40}$ ]] || fail "SOURCE_REF must be a full Git commit SHA"

grep -Fq "SOURCE_REF: $source_ref" "$WORKFLOW" ||
  fail "workflow source revision does not match SOURCE_REF"
grep -Fq 'platforms: linux/amd64' "$WORKFLOW" || fail "workflow must build linux/amd64"
grep -Fq 'CUDA_DOCKER_ARCH=86' "$WORKFLOW" || fail "workflow must target the RTX 3090 SM86 architecture"
grep -Fq 'target: server' "$WORKFLOW" || fail "workflow must publish the server-only image"
grep -Eq 'BASE_CUDA_DEV_CONTAINER=.*@sha256:[0-9a-f]{64}' "$WORKFLOW" ||
  fail "CUDA build base must be digest-pinned"
grep -Eq 'BASE_CUDA_RUN_CONTAINER=.*@sha256:[0-9a-f]{64}' "$WORKFLOW" ||
  fail "CUDA runtime base must be digest-pinned"
grep -Eq 'NODE_VERSION=.*@sha256:[0-9a-f]{64}' "$WORKFLOW" ||
  fail "Node build base must be digest-pinned"

image="$(sed -n 's|^[[:space:]]*image:[[:space:]]*\(ghcr.io/mitchross/llama-cpp-beellama:[^[:space:]#]*\).*|\1|p' "$DEPLOYMENT")"
[[ "$image" =~ ^ghcr\.io/mitchross/llama-cpp-beellama:"$version"@sha256:[0-9a-f]{64}$ ]] ||
  fail "deployment must pin ghcr.io/mitchross/llama-cpp-beellama:$version by digest"
[[ ! "$image" =~ @sha256:0{64}$ ]] || fail "deployment image digest cannot be a placeholder"

printf 'llama.cpp Beellama engine contract is valid\n'
