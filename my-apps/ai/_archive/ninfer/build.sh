#!/usr/bin/env bash
# Reproducible NInfer-3090 image build. NOT deployed by kustomize — run from a
# workstation with docker + push access to registry.vanillax.me.
#
# The fork's CMakeLists hard-enforces CMAKE_CUDA_ARCHITECTURES=86 (FATAL_ERROR
# otherwise), so this build cannot silently produce the upstream sm_120a binary.
set -euo pipefail

TAG="v0.6.0-rtx3090"
COMMIT="2ae51915225d393e299a9d01b099e2c7103cd322"
# registry.vanillax.me refused this image: the docker-distribution S3 driver on
# RustFS fails multi-GB layer uploads ("s3aws: append to zero-size path ...
# unsupported"). ghcr works; make the package public after the first push.
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
