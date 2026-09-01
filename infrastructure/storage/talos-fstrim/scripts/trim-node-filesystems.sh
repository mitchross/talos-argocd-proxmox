#!/bin/sh
set -eu

for target in \
  /var \
  /var/mnt/longhorn-nvme1 \
  /var/mnt/longhorn-ssd-flash
do
  echo "[fstrim] $(date -u +%Y-%m-%dT%H:%M:%SZ) trimming ${target}"
  nsenter --mount=/proc/1/ns/mnt -- \
    /usr/local/sbin/fstrim --verbose "${target}"
done

echo "[fstrim] $(date -u +%Y-%m-%dT%H:%M:%SZ) all targets completed"

