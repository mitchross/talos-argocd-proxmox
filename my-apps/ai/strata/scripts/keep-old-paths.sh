#!/bin/sh
# 0.2.x keeps models, packs and the MTP layer in /data/Strata-data. Move the 0.1.x folders there and leave
# links at the old places, so a revert to 0.1.x still finds its files (no ~92 GB download).
set -eu
mkdir -p /data/Strata-data
for d in models packs mtp; do
  if [ -d "/data/$d" ] && [ ! -L "/data/$d" ] && [ ! -e "/data/Strata-data/$d" ]; then
    mv "/data/$d" "/data/Strata-data/$d" && echo "moved /data/$d -> /data/Strata-data/$d"
  fi
  if [ -d "/data/Strata-data/$d" ] && [ ! -e "/data/$d" ]; then
    ln -s "Strata-data/$d" "/data/$d" && echo "linked /data/$d -> Strata-data/$d"
  fi
done
