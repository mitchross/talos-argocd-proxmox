#!/bin/sh
set -eu

SRC=/src/qwen3.8-27b-gguf
DST=/dst/qwen3.8-27b-gguf
READY=/dst/.qwen38-27b-cache-ready
CACHE_REV='qwen3.8-27b-q4kxl|3f227079003add2511437e5b1e94812e363385225bf6a9b47b0054a72bc8b01e|83ee4f4f205fa514161778c41df1ea14144faa0f713510893b63c2395f5c2d53|50d9ce5a6da381bbcfb31061cf73df94a90e6faf8efeddee379a9cb8f1501c6e'

mkdir -p "$DST/mtp"

# Clear readiness before touching the cache. If this Job fails or is killed,
# a new serving pod must wait rather than start against partial/stale files.
rm -f "$READY" "$READY.tmp"

sync_one() {
  rel="$1"
  s="$SRC/$rel"
  d="$DST/$rel"
  want=$(stat -c %s "$s")
  if [ -f "$d" ] && [ "$(stat -c %s "$d")" = "$want" ]; then
    echo "present: $rel ($want bytes)"
    return
  fi

  echo "copying: $rel ($want bytes)"
  cp "$s" "$d.part" || { rm -f "$d.part"; exit 1; }
  got=$(stat -c %s "$d.part")
  [ "$got" = "$want" ] || {
    echo "SIZE MISMATCH $rel: $got != $want"
    rm -f "$d.part"
    exit 1
  }
  mv "$d.part" "$d"
}

sync_one Qwen3.8-27B-UD-Q4_K_XL.gguf
sync_one mmproj-BF16.gguf
sync_one mtp/mtp-Qwen3.8-27B-Q4_0.gguf

# Atomic readiness publication. The serving initContainer requires this exact
# revision plus all three non-empty files before llama-server may start.
printf '%s\n' "$CACHE_REV" > "$READY.tmp"
mv "$READY.tmp" "$READY"

echo "model cache ready: $CACHE_REV"
echo "=== RESULT ==="
du -sb "$DST" | awk '{printf "Qwen3.8-27B cache: %s bytes (%.2f GiB)\n", $1, $1/1073741824}'
df -h /dst
