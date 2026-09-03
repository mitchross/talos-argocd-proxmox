#!/bin/sh
set -eu

BASE=/models/qwen3.8-27b-gguf
REPO=https://huggingface.co/unsloth/Qwen3.8-27B-GGUF/resolve/main
mkdir -p "$BASE/mtp"
apk add --no-cache curl

# The Hub path can move, but content cannot silently change: every artifact is
# SHA-256 pinned before it becomes the durable NFS copy.
fetch() {
  name="$1" dest="$2" expected="$3"
  part="$dest.part"
  stamp="$dest.sha256"

  if [ -f "$dest" ] && [ "$(cat "$stamp" 2>/dev/null || true)" = "$expected" ]; then
    echo "verified (stamp): $name"
    return
  fi

  if [ -f "$dest" ]; then
    actual="$(sha256sum "$dest" | cut -d' ' -f1)"
    if [ "$actual" = "$expected" ]; then
      printf '%s' "$expected" > "$stamp"
      echo "verified: $name"
      return
    fi
    echo "existing file hash mismatch, replacing: $name"
    rm -f "$dest"
  fi

  curl -fL -C - --retry 5 --retry-delay 2 -o "$part" "$REPO/$name"
  actual="$(sha256sum "$part" | cut -d' ' -f1)"
  [ "$actual" = "$expected" ] || {
    echo "SHA MISMATCH: $name: $actual"
    rm -f "$part"
    exit 1
  }
  mv "$part" "$dest"
  printf '%s' "$expected" > "$stamp"
  echo "downloaded and verified: $name"
}

fetch Qwen3.8-27B-UD-Q4_K_XL.gguf \
  "$BASE/Qwen3.8-27B-UD-Q4_K_XL.gguf" \
  3f227079003add2511437e5b1e94812e363385225bf6a9b47b0054a72bc8b01e

fetch mmproj-BF16.gguf \
  "$BASE/mmproj-BF16.gguf" \
  83ee4f4f205fa514161778c41df1ea14144faa0f713510893b63c2395f5c2d53

fetch MTP/mtp-Qwen3.8-27B-Q4_0.gguf \
  "$BASE/mtp/mtp-Qwen3.8-27B-Q4_0.gguf" \
  50d9ce5a6da381bbcfb31061cf73df94a90e6faf8efeddee379a9cb8f1501c6e
