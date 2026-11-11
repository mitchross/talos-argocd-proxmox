#!/bin/sh
# Runs profiles C, D, B, A, E three times each on /data; prints one JSON line per run.
set -eu
RUNS="${RUNS:-3}"
PROFILES="${PROFILES:-c-bulkwrite d-bulkread b-randread a-commit e-smallfiles}"
mkdir -p /data/small
for p in $PROFILES; do
  i=1
  while [ "$i" -le "$RUNS" ]; do
    [ "$p" = e-smallfiles ] && rm -rf /data/small && mkdir -p /data/small
    start=$(date +%s)
    out=$(timeout 180 fio --output-format=json "/bench/fio/$p.fio") || { echo "{\"profile\":\"$p\",\"run\":$i,\"error\":\"fio failed or hit 180 s\"}"; exit 1; }
    end=$(date +%s)
    printf '%s' "$out" | jq -c --arg p "$p" --argjson r "$i" --argjson s "$start" --argjson e "$end" \
      '{profile:$p, run:$r, start:$s, wall_s:($e-$s), job:.jobs[0] | {read:{iops:.read.iops, bw_kib:.read.bw, clat_p50_ns:.read.clat_ns.percentile."50.000000", clat_p99_ns:.read.clat_ns.percentile."99.000000"}, write:{iops:.write.iops, bw_kib:.write.bw, clat_p50_ns:.write.clat_ns.percentile."50.000000", clat_p99_ns:.write.clat_ns.percentile."99.000000"}, sync:{p50_ns:.sync.lat_ns.percentile."50.000000", p99_ns:.sync.lat_ns.percentile."99.000000"}, runtime_ms:.job_runtime}}'
    i=$((i + 1))
  done
done
rm -rf /data/small /data/fio.dat
echo '{"done":true}'
