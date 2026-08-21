#!/usr/bin/env bash
# Reproducible qwen38-27b-3090 image build. NOT deployed by kustomize — run from
# a workstation with docker + push access to ghcr (registry.vanillax.me cannot
# take the multi-GB layers — RustFS s3aws append limitation).
#
# The repo has no release tags and moves fast: this pins a raw commit. Bumping
# it is a deliberate act — update COMMIT here and both manifest image pins.
set -euo pipefail

COMMIT="e00bc1b7301faed3737783379cace5fa37416e8a"
IMAGE="${IMAGE:-ghcr.io/mitchross/qwen38-27b-3090:${COMMIT:0:8}}"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

git clone https://github.com/syv-ai/qwen38-27b-rtx3090 "$WORK/src"
git -C "$WORK/src" checkout "$COMMIT"

docker build -t "$IMAGE" "$WORK/src"
docker push "$IMAGE"
docker inspect --format='{{index .RepoDigests 0}}' "$IMAGE"
echo "Pin the printed digest into deployment.yaml and model-prep-job.yaml."
