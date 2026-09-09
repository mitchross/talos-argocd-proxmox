#!/bin/sh
set -eu
umask 077
cd "${REDIS_DATA_DIR:-/data}"
aof=appendonlydir
manifest="$aof/appendonly.aof.manifest"
tail="$aof/appendonly.aof.3.incr.aof"
archive=redis-aof-recovery-20260909
[ ! -L "$aof" ] || { echo 'Refusing symlink AOF directory' >&2; exit 1; }
if [ ! -e "$aof" ]; then
  echo 'No AOF directory: normal first startup'
  exit 0
fi
[ -d "$aof" ] && [ -f "$manifest" ] || exit 1
[ -z "$(find "$aof" -mindepth 1 ! -type f -print)" ] || { echo 'Unexpected AOF layout' >&2; exit 1; }
for file in "$aof"/* "$aof"/.[!.]* "$aof"/..?*; do
  [ -e "$file" ] || continue
  case "${file##*/}" in appendonly.aof.*) ;; *) echo 'Unexpected AOF filename' >&2; exit 1 ;; esac
done
report=$(mktemp)
trap 'rm -f "$report"' EXIT
if redis-check-aof "$manifest" >"$report" 2>&1; then
  echo 'AOF validates; no recovery necessary'
  exit 0
fi
# Only the observed incident qualifies; future/different corruption fails closed.
[ "$(wc -c < "$tail")" -eq 36162313 ] || { echo 'Unexpected AOF size' >&2; exit 1; }
grep -Eq 'filename=appendonly.aof.3.incr.aof, size=36162313, ok_up_to=36151654, .*diff=10659$' "$report" || {
  echo 'Checker does not match audited 10659-byte tail; manual review required' >&2
  exit 1
}
bytes=$(du -sk "$aof" | awk '{print $1}')
free=$(df -Pk . | awk 'END {print $4}')
[ "$free" -gt "$((bytes + 65536))" ] || { echo 'Insufficient space to preserve AOF' >&2; exit 1; }
mkdir -m 700 "$archive" # Exclusive: interrupted or previous recovery requires review.
mkdir "$archive/original"
cp -p "$aof"/* "$archive/original/"
for file in "$aof"/*; do
  cmp "$file" "$archive/original/${file##*/}" || exit 1
done
(cd "$archive/original" && sha256sum ./* > ../SHA256SUMS)
sync -f "$archive"
# Truncation can discard queued tasks/results represented by these 10659 bytes.
printf 'y\n' | redis-check-aof --fix "$manifest" > "$archive/repair.log" 2>&1
[ "$(wc -c < "$tail")" -eq 36151654 ] || { echo 'Unexpected repaired length' >&2; exit 1; }
redis-check-aof "$manifest" > "$archive/validation.log" 2>&1
sync -f "$archive"
echo 'Audited AOF tail repaired; complete originals retained in redis-aof-recovery-20260909/original'
