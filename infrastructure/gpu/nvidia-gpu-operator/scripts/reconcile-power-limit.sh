#!/bin/bash
set -u

echo "[powerlimit] waiting for nvidia-smi to become available..."
until nvidia-smi >/dev/null 2>&1; do sleep 5; done

echo "[powerlimit] capping all GPUs at ${POWER_LIMIT_WATTS}W; reapplying every ${REAPPLY_SECONDS}s"
while true; do
  # Best-effort: persistence mode keeps the driver loaded between
  # CUDA processes. The reapply loop covers driver reloads.
  nvidia-smi -pm 1 >/dev/null 2>&1 \
    || echo "[powerlimit] WARN: could not enable persistence mode"

  if nvidia-smi -pl "${POWER_LIMIT_WATTS}" >/dev/null; then
    nvidia-smi \
      --query-gpu=index,name,power.limit,power.default_limit,power.max_limit,power.draw \
      --format=csv,noheader
  else
    echo "[powerlimit] WARN: failed to set power limit; retrying in ${REAPPLY_SECONDS}s"
  fi

  sleep "${REAPPLY_SECONDS}"
done

