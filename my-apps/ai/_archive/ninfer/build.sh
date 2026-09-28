#!/usr/bin/env bash
# Build the archived NInfer candidate on a workstation with Docker and registry access.
# The fork enforces CUDA architecture 86, preventing an incompatible upstream sm_120a binary.
set -euo pipefail

TAG="v0.6.0-rtx3090"
COMMIT="2ae51915225d393e299a9d01b099e2c7103cd322"
# Publish to GHCR: RustFS rejects multi-GB layer appends. Make the package public after the first push.
IMAGE="${IMAGE:-ghcr.io/mitchross/ninfer-3090:${TAG}}"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

git clone --depth 1 --branch "$TAG" https://github.com/Don-Chad/ninfer-3090 "$WORK/src"
HEAD="$(git -C "$WORK/src" rev-parse HEAD)"
[ "$HEAD" = "$COMMIT" ] || { echo "TAG MOVED: expected $COMMIT got $HEAD — refusing to build"; exit 1; }

docker build -t "$IMAGE" "$WORK/src"
docker push "$IMAGE"
docker inspect --format='{{index .RepoDigests 0}}' "$IMAGE"
echo "Pin the printed digest into deployment.yaml (image: ...@sha256:...)."
