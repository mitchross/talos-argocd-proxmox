#!/bin/sh
ZIM_FILES=$(find /data -name '*.zim' 2>/dev/null)
if [ -z "$ZIM_FILES" ]; then
  echo "No ZIM files found in /data, sleeping..."
  sleep infinity
else
  exec kiwix-serve --address=0.0.0.0 --port=8080 /data/*.zim
fi

