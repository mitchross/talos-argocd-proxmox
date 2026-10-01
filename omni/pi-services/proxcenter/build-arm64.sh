#!/usr/bin/env bash
set -euo pipefail

[[ $(uname -m) == aarch64 ]] || { echo 'Build on the ARM64 Pi.' >&2; exit 1; }
source_revision=533d8127b60fd5f5d59985109893725c80f1c687
base_image=node:26.10.0-alpine3.24@sha256:f78d6d4ca1b1463e66837575f9ac0035aaad30d9497dc9f3bc611b544be2ab15
image_tag=ghcr.io/adminsyspro/proxcenter-frontend:1.4.10-arm64-20261001
build_dir=$(mktemp -d /var/tmp/proxcenter-arm64.XXXXXX)
trap 'rm -rf "$build_dir"' EXIT

curl --fail --silent --show-error --location \
  "https://codeload.github.com/adminsyspro/proxcenter-ui/tar.gz/$source_revision" \
  -o "$build_dir/source.tar.gz"
tar -xzf "$build_dir/source.tar.gz" -C "$build_dir" --strip-components=1
python3 - "$build_dir/frontend/Dockerfile" "$base_image" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
source = path.read_text()
assert source.count('FROM node:26-alpine AS ') == 3, 'Upstream base stages changed'
assert source.count('RUN npm run build\n') == 1, 'Upstream build command changed'
source = source.replace('FROM node:26-alpine AS ', f'FROM {sys.argv[2]} AS ')
# Pi type checking needs a larger build heap; do not enlarge the runtime heap.
source = source.replace('RUN npm run build\n',
                        'RUN NODE_OPTIONS="--max-old-space-size=5120" npm run build\n')
path.write_text(source)
PY

docker build --pull --platform linux/arm64 \
  --build-arg "GIT_SHA=$source_revision" --build-arg APP_VERSION=1.4.10 \
  --label org.opencontainers.image.source=https://github.com/adminsyspro/proxcenter-ui \
  --label "org.opencontainers.image.revision=$source_revision" \
  --tag "$image_tag" "$build_dir/frontend"
docker image inspect "$image_tag" --format '{{.Architecture}} {{.Id}}'
