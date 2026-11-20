#!/bin/sh
# One-time import + publish of the two replay cases (radar-ng docs/develop/replay-publish.md, #285).
# The image is distroless plus busybox: only sh/wget/ls/cat/find/test/touch/sleep are on PATH,
# everything else is called as `busybox <applet>`.
set -eu

TILES="${TILE_DIR:?TILE_DIR is required}"
W="${WORK_DIR:-/work}"
REV=full-1
PUB="${REV}-public"

# A dropped archive download stops an import; the same command resumes it.
retry() { for n in 1 2 3; do "$@" && return 0; echo "attempt $n failed: $*"; sleep 30; done; return 1; }

report() {
  dir="$TILES/replays/$1/$2"
  echo "== $1/$2: allocated KiB, files"
  busybox du -sk "$dir"
  find "$dir" -type f | busybox wc -l
  if test -f "$dir/progress.json"; then
    echo "== $1/$2: distinct archive object sha256 in progress.json"
    busybox grep -oE '[0-9a-f]{64}' "$dir/progress.json" | busybox sort -u | busybox wc -l
  fi
}

# The importer writes .staging-<rev>/ and renames it to <rev>/ only when every frame is done.
# So <rev>/ means finished (re-import refuses it); .staging-<rev>/ resumes with the same command.
# A published case is skipped whole: a fresh warnings fetch could differ from the published one.
run_case() {
  case_id="$1"; shift
  if test -d "$TILES/replays/$case_id/$PUB"; then
    echo "== $case_id: $PUB already published, skipping"
    report "$case_id" "$PUB"
    return 0
  fi
  if test -d "$TILES/replays/$case_id/$REV"; then
    echo "== $case_id: $REV already imported, skipping import"
  else
    if test -d "$TILES/replays/$case_id/.staging-$REV"; then
      echo "== $case_id: resuming unfinished .staging-$REV"
      report "$case_id" ".staging-$REV"
    fi
    echo "== $case_id: import $(busybox date -u +%FT%TZ)"
    retry radar replay import --case "$case_id" --revision "$REV" --verify-crop "$@"
  fi
  echo "== $case_id: warnings $(busybox date -u +%FT%TZ)"
  retry radar import-replay-warnings "$case_id" "$W/$case_id.geojson"
  echo "== $case_id: warnings sha256"
  busybox sha256sum "$W/$case_id.geojson"
  echo "== $case_id: publish $(busybox date -u +%FT%TZ)"
  radar replay publish --case "$case_id" --revision "$REV" --warnings "$W/$case_id.geojson"
  report "$case_id" "$REV"
  report "$case_id" "$PUB"
}

# The importer itself enforces the 10 GiB replay quota and 20 GiB live free headroom.
echo "== free space before"
busybox df -h "$TILES"
busybox df -i "$TILES"

run_case greenfield-2024
run_case rolling-fork-2023 \
  --exclude-object CONUS/MergedBaseReflectivityQC_00.50/20230324/MRMS_MergedBaseReflectivityQC_00.50_20230324-231159.grib2.gz

echo "== free space after"
busybox df -h "$TILES"
busybox du -sk "$TILES/replays"

# The API caches readiness for 10 s.
sleep 15
echo "== /api/replays"
wget -qO- http://tile-server.radar-ng.svc:8080/api/replays
echo
echo "== done $(busybox date -u +%FT%TZ)"
