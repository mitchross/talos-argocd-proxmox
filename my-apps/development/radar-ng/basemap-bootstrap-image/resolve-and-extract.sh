#!/bin/sh
# Resolve the newest available Protomaps planet build and extract the
# configured bbox into /data/basemap.pmtiles. No date is ever pinned —
# build.protomaps.com has no `latest` alias and ~6-day retention, so we
# walk backward from today until we hit a build that exists.
#
# Env:
#   BBOX            extract bbox, "minLon,minLat,maxLon,maxLat" (required)
#   MAX_LOOKBACK    how many days back to probe before giving up (default 14)
#   OUT             output path (default /data/basemap.pmtiles)
set -eu

BASE_URL="https://build.protomaps.com"
BBOX="${BBOX:?BBOX env is required (e.g. -125,24,-66,50)}"
MAX_LOOKBACK="${MAX_LOOKBACK:-14}"
OUT="${OUT:-/data/basemap.pmtiles}"
TMP="${OUT}.tmp"

resolved=""
i=0
while [ "$i" -le "$MAX_LOOKBACK" ]; do
  d="$(date -u -d "-${i} days" +%Y%m%d)"
  url="${BASE_URL}/${d}.pmtiles"
  if curl -fsI --max-time 30 "$url" >/dev/null 2>&1; then
    resolved="$url"
    echo "resolved newest available build: ${d} (${url})"
    break
  fi
  echo "no build for ${d} (probe ${i}/${MAX_LOOKBACK}), going back a day"
  i=$((i + 1))
done

if [ -z "$resolved" ]; then
  echo "FATAL: no Protomaps build found in the last ${MAX_LOOKBACK} days" >&2
  echo "       (checked ${BASE_URL}/YYYYMMDD.pmtiles back from $(date -u +%Y%m%d))" >&2
  exit 1
fi

# Extract to a temp path, then atomically rename. The basemap Deployment's
# init container blocks on a non-empty /data/basemap.pmtiles; a crash
# mid-extract must NOT leave a partial file that satisfies that check.
echo "extracting bbox=${BBOX} -> ${OUT}"
pmtiles extract "$resolved" "$TMP" --bbox="$BBOX"
mv -f "$TMP" "$OUT"
echo "done: $(ls -lh "$OUT")"
