#!/bin/sh
set -eu

# Every target must exist: set -e stops at the first missing path and skips the rest.
for target in \
  /var \
  /var/mnt/ai-model-cache \
  /var/mnt/longhorn-ssd-flash \
  /var/mnt/longhorn-gpu-bulk
do
  echo "[fstrim] $(date -u +%Y-%m-%dT%H:%M:%SZ) trimming ${target}"
  nsenter --mount=/proc/1/ns/mnt -- \
    /usr/local/sbin/fstrim --verbose "${target}"
done

echo "[fstrim] $(date -u +%Y-%m-%dT%H:%M:%SZ) all targets completed"

