#!/bin/sh
set -eu

SRC=/src/qwen3.8-27b-gguf
DST=/dst/qwen3.8-27b-gguf
mkdir -p "$DST/mtp"

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

echo "=== RESULT ==="
du -sb "$DST" | awk '{printf "Qwen3.8-27B cache: %s bytes (%.2f GiB)\n", $1, $1/1073741824}'
df -h /dst
