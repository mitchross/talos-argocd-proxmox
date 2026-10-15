#!/bin/sh
set -eu
DATA_DIR=${DATA_DIR:-/data}
LIBRARY_DIR=${LIBRARY_DIR:-/library}
mkdir -p "$LIBRARY_DIR"
rebuild() {
    set -- "$DATA_DIR"/*.zim
    if [ ! -f "$1" ]; then
        set --
    fi
    printf '%s\n' "$@" > "$LIBRARY_DIR/files.next"
    if [ -f "$LIBRARY_DIR/library.xml" ] &&
       cmp -s "$LIBRARY_DIR/files.next" "$LIBRARY_DIR/files.current"; then
        return 0
    fi
    printf '%s\n' '<?xml version="1.0" encoding="UTF-8"?><library version="20110515"></library>' > "$LIBRARY_DIR/library.next.xml"
    if [ "$#" -gt 0 ]; then
        kiwix-manage "$LIBRARY_DIR/library.next.xml" add "$@" || return 1
    fi
    # Atomic publication keeps kiwix-serve from reading a partially written library.
    mv "$LIBRARY_DIR/library.next.xml" "$LIBRARY_DIR/library.xml"
    mv "$LIBRARY_DIR/files.next" "$LIBRARY_DIR/files.current"
    echo "Indexed $# ZIM archives"
}
if [ "${1:-}" = '--once' ]; then
    rebuild
    exit
fi
while :; do
    if ! rebuild; then
        echo 'Index update failed; retaining the previous library' >&2
    fi
    sleep 60
done
