#!/usr/bin/env bash
set -euo pipefail

source_revision=ca3d5a3e10d53f7ea672cb9b6178faca3e2807bc
image=ghcr.io/mitchross/llama.cpp:server-cuda-qwen4exp-ca3d5a3e
build_dir=$(mktemp -d)
trap 'rm -rf "$build_dir"' EXIT

git clone --filter=blob:none --no-checkout https://github.com/ggml-org/llama.cpp.git "$build_dir"
git -C "$build_dir" fetch --depth 1 origin "$source_revision"
git -C "$build_dir" checkout --detach "$source_revision"

docker buildx build \
  --platform linux/amd64 \
  --target server \
  --file "$build_dir/.devops/cuda.Dockerfile" \
  --build-arg CUDA_DOCKER_ARCH=86 \
  --build-arg APP_VERSION=qwen4exp-ca3d5a3e \
  --build-arg APP_REVISION="$source_revision" \
  --build-arg BUILD_DATE=2026-08-27T23:49:27Z \
  --build-arg BASE_CUDA_DEV_CONTAINER=docker.io/nvidia/cuda:12.8.1-devel-ubuntu24.04@sha256:520292dbb4f755fd360766059e62956e9379485d9e073bbd2f6e3c20c270ed66 \
  --build-arg BASE_CUDA_RUN_CONTAINER=docker.io/nvidia/cuda:12.8.1-runtime-ubuntu24.04@sha256:ebef3c171eeef0298e4eb2e4be843105edf3b8b0ac45e0b43acee358e8046867 \
  --build-arg NODE_VERSION=24@sha256:be23f54a88d34e8824c741b19b91064094f92c1c97b194144bfc8b50d67258e2 \
  --tag "$image" \
  --provenance=false \
  --push \
  "$build_dir"

crane digest "$image"
