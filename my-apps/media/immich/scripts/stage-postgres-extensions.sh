#!/bin/sh
set -eu

case "${1:-}" in
  base)
    mkdir -p /staged/share/extension /staged/lib
    cp -a /usr/share/postgresql/17/extension/. /staged/share/extension/
    ;;
  immich)
    test -f /staged/share/extension/plpgsql.control
    for extension in vector vchord; do
      test -s "/usr/lib/postgresql/17/lib/$extension.so"
      cp "/usr/lib/postgresql/17/lib/$extension.so" /staged/lib/
      cp /usr/share/postgresql/17/extension/"$extension"*.sql /staged/share/extension/
      cp "/usr/share/postgresql/17/extension/$extension.control" /staged/share/extension/
    done
    ;;
  *)
    echo 'Expected base or immich extension staging mode' >&2
    exit 2
    ;;
esac
