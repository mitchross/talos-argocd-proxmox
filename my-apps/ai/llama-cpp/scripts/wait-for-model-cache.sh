#!/bin/sh
set -eu

BASE=/models/qwen3.8-27b-gguf
READY=/models/.qwen38-27b-cache-ready
CACHE_REV='qwen3.8-27b-q4kxl|3f227079003add2511437e5b1e94812e363385225bf6a9b47b0054a72bc8b01e|83ee4f4f205fa514161778c41df1ea14144faa0f713510893b63c2395f5c2d53|50d9ce5a6da381bbcfb31061cf73df94a90e6faf8efeddee379a9cb8f1501c6e'

MODEL="$BASE/Qwen3.8-27B-UD-Q4_K_XL.gguf"
MMPROJ="$BASE/mmproj-BF16.gguf"
MTP="$BASE/mtp/mtp-Qwen3.8-27B-Q4_0.gguf"

# Argo sync hooks stage NFS -> local NVMe, but an already-existing Deployment
# can be rolled before those hooks finish. Never let llama-server enter a
# crash-loop against a half-hydrated cache.
i=0
while :; do
  stamp="$(cat "$READY" 2>/dev/null || true)"
  if [ "$stamp" = "$CACHE_REV" ] && [ -s "$MODEL" ] && [ -s "$MMPROJ" ] && [ -s "$MTP" ]; then
    echo "model cache ready: $CACHE_REV"
    exit 0
  fi

  i=$((i + 1))
  if [ $((i % 6)) -eq 1 ]; then
    echo "waiting for Qwen3.8-27B local-NVMe cache hydration (stamp=${stamp:-missing})"
    ls -lh "$BASE" "$BASE/mtp" 2>/dev/null || true
  fi
  sleep 5
done
