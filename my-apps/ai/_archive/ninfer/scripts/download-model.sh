#!/bin/sh
# Pinned artifact: huggingface.co/neroued/Qwen3.8-27B-NInfer (16.96 GiB, container v2).
EXPECTED_SHA="eec39564993d6e9c7d5e383382a760f093465c9d163ec9a1bd6b80199514bf3e"
URL="https://huggingface.co/neroued/Qwen3.8-27B-NInfer/resolve/main/qwen3_8_27b.ninfer"
F=/models/ninfer/qwen3_8_27b.ninfer
mkdir -p /models/ninfer
if [ -f "$F" ] && [ "$(stat -c %s "$F")" = "18210531328" ]; then
  echo "size matches, verifying sha256..."
  if [ "$(sha256sum "$F" | cut -d' ' -f1)" = "$EXPECTED_SHA" ]; then
    echo "artifact present and verified"; exit 0
  fi
  echo "sha mismatch — re-downloading"
fi
apk add --no-cache curl
curl -fL -C - --retry 5 -o "$F" "$URL"
ACTUAL="$(sha256sum "$F" | cut -d' ' -f1)"
[ "$ACTUAL" = "$EXPECTED_SHA" ] || { echo "SHA MISMATCH: $ACTUAL"; rm -f "$F"; exit 1; }
echo "downloaded and verified: $F"

