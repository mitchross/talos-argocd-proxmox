#!/bin/sh
set -eu
DATA_DIR=${DATA_DIR:-/data}
MANIFEST=${MANIFEST:-/opt/library/collections.tsv}
RETRY_DELAY=${RETRY_DELAY:-10}
mkdir -p "$DATA_DIR/.downloads"
cleanup_old_versions() {
    stem=$(printf '%s\n' "$file" | sed -n 's/_[0-9][0-9][0-9][0-9]-[0-9][0-9]\.zim$//p')
    [ -n "$stem" ] || return 0
    version=${file#"${stem}_"}
    version=${version%.zim}
    for old in "$DATA_DIR/${stem}_"*.zim "$DATA_DIR/${stem}_"*.zim.part "$DATA_DIR/.downloads/${stem}_"*.zim.part; do
        [ -f "$old" ] || continue
        name=${old##*/}
        name=${name%.part}
        date=${name#"${stem}_"}
        date=${date%.zim}
        printf '%s\n' "$date" | grep -Eq '^[0-9]{4}-[0-9]{2}$' || continue
        if [ "$(printf '%s' "$date" | tr -d '-')" -lt "$(printf '%s' "$version" | tr -d '-')" ]; then
            echo "Removing superseded archive: $old"
            rm -f "$old" "$DATA_DIR/.downloads/$name.sha256"
        fi
    done
    rm -f "$DATA_DIR/$file.part" "$partial"
}
failed=0
while read -r expected size url; do
    case "$expected" in ''|'#'*) continue ;; esac
    file=${url##*/}
    target="$DATA_DIR/$file"
    partial="$DATA_DIR/.downloads/$file.part"
    marker="$DATA_DIR/.downloads/$file.sha256"
    if [ -f "$target" ]; then
        if [ "$(stat -c %s "$target")" = "$size" ] &&
           [ -f "$marker" ] && [ "$(cat "$marker")" = "$expected" ]; then
            echo "Already verified: $file"
            cleanup_old_versions
            continue
        fi
        if [ "$(stat -c %s "$target")" = "$size" ] &&
           [ "$(sha256sum "$target" | cut -d' ' -f1)" = "$expected" ]; then
            printf '%s\n' "$expected" > "$marker"
            cleanup_old_versions
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
    if [ "$(stat -c %s "$partial")" != "$size" ] ||
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
    cleanup_old_versions
done < "$MANIFEST"
exit "$failed"
