#!/bin/sh
set -eu
DATA_DIR=${DATA_DIR:-/data}
MANIFEST=${MANIFEST:-/opt/library/collections.tsv}
RETRY_DELAY=${RETRY_DELAY:-10}
mkdir -p "$DATA_DIR/.downloads"
failed=0
while read -r expected size url; do
    case "$expected" in ''|'#'*) continue ;; esac
    file=${url##*/}
    target="$DATA_DIR/$file"
    partial="$DATA_DIR/.downloads/$file.part"
    marker="$DATA_DIR/.downloads/$file.sha256"
    if [ -f "$target" ]; then
        if [ "$(wc -c < "$target" | tr -d ' ')" = "$size" ] &&
           [ -f "$marker" ] && [ "$(cat "$marker")" = "$expected" ]; then
            echo "Already verified: $file"
            continue
        fi
        if [ "$(sha256sum "$target" | cut -d' ' -f1)" = "$expected" ]; then
            printf '%s\n' "$expected" > "$marker"
            continue
        fi
        echo "Existing file differs; preserving it: $file" >&2
        failed=1
        continue
    fi
    attempt=0
    downloaded=0
    while [ "$attempt" -lt 5 ]; do
        attempt=$((attempt + 1))
        echo "Downloading $file (attempt $attempt)"
        if wget -q -c -T 60 -O "$partial" "$url"; then
            downloaded=1
            break
        fi
        sleep "$RETRY_DELAY"
    done
    if [ "$downloaded" -ne 1 ]; then
        failed=1
        continue
    fi
    if [ "$(wc -c < "$partial" | tr -d ' ')" != "$size" ] ||
       [ "$(sha256sum "$partial" | cut -d' ' -f1)" != "$expected" ]; then
        echo "Checksum or size mismatch: $file" >&2
        rm -f "$partial"
        failed=1
        continue
    fi
    # Publish only verified archives; the library indexer never sees partial downloads.
    mv "$partial" "$target"
    printf '%s\n' "$expected" > "$marker"
    echo "Published: $file"
done < "$MANIFEST"
exit "$failed"
