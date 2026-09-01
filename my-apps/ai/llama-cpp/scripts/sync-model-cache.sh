#!/bin/sh
SRC=/src/qwen3.8-flash-next-gguf
DST=/dst/qwen3.8-flash-next-gguf
mkdir -p \
  "$DST/unsloth-ud-iq4-xs" \
  "$DST/unsloth-ud-q4-k-xl" \
  "$DST/atomic-ad-4.27-q4-k-m-m64"

sync_one() {
  rel="$1"; s="$SRC/$rel"; d="$DST/$rel"
  want=$(stat -c %s "$s")
  if [ -f "$d" ] && [ "$(stat -c %s "$d")" = "$want" ]; then
    echo "present: $rel ($want bytes)"; return
  fi
  echo "copying: $rel ($want bytes)"
  cp "$s" "$d.part" || { rm -f "$d.part"; exit 1; }
  got=$(stat -c %s "$d.part")
  [ "$got" = "$want" ] || { echo "SIZE MISMATCH $rel: $got != $want"; rm -f "$d.part"; exit 1; }
  mv "$d.part" "$d"
}

for i in 1 2 3; do
  sync_one "unsloth-ud-iq4-xs/Qwen3.8-Flash-Next-UD-IQ4_XS-0000$i-of-00003.gguf"
done

for i in 1 2 3 4; do
  sync_one "unsloth-ud-q4-k-xl/Qwen3.8-Flash-Next-UD-Q4_K_XL-0000$i-of-00004.gguf"
done
sync_one "mmproj-BF16.gguf"

i=1
while [ "$i" -le 33 ]; do
  shard=$(printf '%05d' "$i")
  sync_one "atomic-ad-4.27-q4-k-m-m64/Qwen3.8-Flash-Next-AD-4.27bpw-Q4_K_M-M64-${shard}-of-00033.gguf"
  i=$((i + 1))
done
sync_one "mmproj-F16.gguf"

echo "=== RESULT ==="
du -sb "$DST" | awk '{printf "cache: %s bytes (%.2f GiB)\n", $1, $1/1073741824}'
df -h /dst

