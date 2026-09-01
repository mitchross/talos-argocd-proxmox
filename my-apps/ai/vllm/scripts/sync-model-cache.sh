#!/bin/sh
MODEL=Qwen3.8-27B-W4A16-AutoRound-3090-int8lmhead
REVISION=$MODEL:r1 # Bump here and in deployment.yaml for in-place source changes.
SRC=/src/$MODEL
DST=/dst/$MODEL
STATE=/dst/.vllm-cache-revision
READY=/dst/.vllm-sync-complete
STATE_TMP=$STATE.part
READY_TMP=$READY.part
mkdir -p "$DST"

# The Deployment may land before this Sync hook, so publish readiness last.
LAST_REVISION=$(cat "$STATE" 2>/dev/null || true)
FORCE_COPY=0
if [ -n "$LAST_REVISION" ] && [ "$LAST_REVISION" != "$REVISION" ]; then
  FORCE_COPY=1
fi
rm -f "$READY" "$STATE_TMP" "$READY_TMP"

[ -d "$SRC" ] || { echo "MISSING SOURCE: $SRC"; exit 1; }

sync_one() {
  rel="$1"; s="$SRC/$rel"; d="$DST/$rel"
  want=$(stat -c %s "$s")
  if [ "$FORCE_COPY" -eq 0 ] && [ -f "$d" ] && [ "$(stat -c %s "$d")" = "$want" ]; then
    echo "present: $rel ($want bytes)"; return
  fi
  echo "copying: $rel ($want bytes)"
  cp "$s" "$d.part" || { rm -f "$d.part"; exit 1; }
  got=$(stat -c %s "$d.part")
  [ "$got" = "$want" ] || { echo "SIZE MISMATCH $rel: $got != $want"; rm -f "$d.part"; exit 1; }
  mv "$d.part" "$d"
}

# Whole checkpoint dir, flat — weights plus tokenizer/config/template
# files. vLLM refuses to load if any of them is missing.
for path in "$SRC"/*; do
  [ -f "$path" ] && sync_one "${path##*/}"
done

printf '%s\n' "$REVISION" > "$STATE_TMP"
mv "$STATE_TMP" "$STATE"
printf '%s\n' "$REVISION" > "$READY_TMP"
mv "$READY_TMP" "$READY"

echo "=== RESULT ==="
ls -1 "$DST" | wc -l | awk '{print "files: " $1}'
du -sb "$DST" | awk '{printf "model: %s bytes (%.2f GiB)\n", $1, $1/1073741824}'
df -h /dst
