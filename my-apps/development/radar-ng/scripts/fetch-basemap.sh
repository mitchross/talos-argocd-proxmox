#!/bin/sh
# Init container: ensure /data/basemap.pmtiles holds the BBOX extract of the newest Protomaps build.
# Marker format must stay "bbox=<BBOX> refresh=<REFRESH>" or every restart re-runs the ~35-min extract.
set -eu

BASE_URL="https://build.protomaps.com"
BBOX="${BBOX:?BBOX env is required (e.g. -125,24,-66,50)}"
REFRESH="${REFRESH:-0}"
MAX_LOOKBACK="${MAX_LOOKBACK:-14}"
PMTILES_SRC="${PMTILES_SRC:-/opt/go-pmtiles/go-pmtiles}"
OUT="${OUT:-/data/basemap.pmtiles}"
TMP="${OUT}.tmp"
MARKER="${OUT}.marker"

KEY="bbox=${BBOX} refresh=${REFRESH}"
if [ -s "$OUT" ] && [ -f "$MARKER" ] && [ "$(head -n1 "$MARKER")" = "$KEY" ]; then
  echo "marker matches (${KEY}); extract already done"
  exit 0
fi

# Image volumes mount noexec, so run a copy of the binary.
PMTILES=/tmp/pmtiles
install -m 0755 "$PMTILES_SRC" "$PMTILES"

# No `latest` alias and ~6-day retention: walk back from today to the newest build that exists.
now=$(date -u +%s)
resolved=""
build=""
i=0
while [ "$i" -le "$MAX_LOOKBACK" ]; do
  d=$(date -u -d "@$((now - i * 86400))" +%Y%m%d)
  if wget -q --spider -T 30 "${BASE_URL}/${d}.pmtiles"; then
    resolved="${BASE_URL}/${d}.pmtiles"
    build="$d"
    break
  fi
  echo "no build for ${d} (probe ${i}/${MAX_LOOKBACK})"
  i=$((i + 1))
done

if [ -z "$resolved" ]; then
  echo "FATAL: no Protomaps build found in the last ${MAX_LOOKBACK} days" >&2
  exit 1
fi

# Extract to a temp path and rename, so a crash never leaves a partial file that passes the -s check.
echo "extracting bbox=${BBOX} from ${resolved}"
"$PMTILES" extract "$resolved" "$TMP" --bbox="$BBOX"
mv -f "$TMP" "$OUT"
printf '%s\nbuild=%s extracted=%s\n' "$KEY" "$build" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$MARKER"
echo "done: $(ls -lh "$OUT")"
