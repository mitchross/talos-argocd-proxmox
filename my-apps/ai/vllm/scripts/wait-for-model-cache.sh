#!/bin/sh
MODEL=Qwen3.8-27B-W4A16-AutoRound-3090-int8lmhead
REVISION=$MODEL:r1
READY=/models/.vllm-sync-complete
i=0
until [ "$(cat "$READY" 2>/dev/null)" = "$REVISION" ]; do
  i=$((i + 1))
  if [ "$i" -gt 360 ]; then
    echo "TIMEOUT: cache-sync never completed (60m)"; exit 1
  fi
  echo "waiting for vllm-cache-sync to finish hydrating the NVMe cache..."
  sleep 10
done
echo "cache ready: $MODEL"

