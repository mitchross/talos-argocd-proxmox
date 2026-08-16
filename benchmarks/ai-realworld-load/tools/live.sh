#!/usr/bin/env bash
# Live view for the active Baseline A run. Reads ONLY the collector's files —
# it opens no extra connections to vLLM or the GPUs, so watching the run costs
# the run nothing.
#
#   TIME | RUNNING | WAITING | KV% | RESIDENT | GPU0/1 VRAM | GPU0/1 UTIL | GPU0/1 W | PREEMPT
#
# RESIDENT = kv_cache_usage_perc x kv_cache_size_tokens, i.e. how much real
# context is resident across all active requests. This is the number the whole
# single-vs-dual decision turns on, so it is on screen the entire run.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE="$ROOT/.current-run"
[ -f "$STATE" ] || { echo "no active run — start one with: tools/collect.sh start"; exit 1; }
RUN="$(cat "$STATE")"

CAP=$(grep -o 'kv_cache_size_tokens="[0-9]*"' "$RUN/cache-config.txt" 2>/dev/null | grep -o '[0-9]*')
CAP=${CAP:-313367}

printf '\033[1m%-8s %4s %4s %7s %9s  %6s %6s  %4s %4s  %5s %5s %4s\033[0m\n' \
  TIME RUN WAIT "KV%" RESIDENT G0MiB G1MiB G0% G1% G0W G1W PREE
echo "capacity=$CAP tokens   run=$(basename "$RUN")"
printf '%.0s-' {1..92}; echo

while true; do
  # Last complete metrics tick.
  TICK=$(awk '/===TICK/{buf=""} {buf=buf $0 "\n"} END{printf "%s", buf}' "$RUN/metrics.stream" 2>/dev/null)
  T=$(echo "$TICK"  | awk '/===TICK/{print $2}' | cut -dT -f2 | tr -d 'Z')
  RUNQ=$(echo "$TICK" | awk -F' ' '/^vllm:num_requests_running/{print $2}' | head -1)
  WAIT=$(echo "$TICK" | awk -F' ' '/^vllm:num_requests_waiting\{/{print $2}' | head -1)
  KV=$(echo "$TICK"   | awk -F' ' '/^vllm:kv_cache_usage_perc/{print $2}' | head -1)
  PRE=$(echo "$TICK"  | awk -F' ' '/^vllm:num_preemptions_total/{print $2}' | head -1)

  # Latest line per GPU index. Must match FIELD 2 exactly: a substring grep for
  # ", 0," also hits the utilization/temperature columns, which silently made
  # both columns show the same card.
  G0=$(awk -F', *' '$2=="0"' "$RUN/gpu.csv" 2>/dev/null | tail -1)
  G1=$(awk -F', *' '$2=="1"' "$RUN/gpu.csv" 2>/dev/null | tail -1)
  g0m=$(echo "$G0" | awk -F', ' '{print $3}'); g0u=$(echo "$G0" | awk -F', ' '{print $5}'); g0w=$(echo "$G0" | awk -F', ' '{print $7}')
  g1m=$(echo "$G1" | awk -F', ' '{print $3}'); g1u=$(echo "$G1" | awk -F', ' '{print $5}'); g1w=$(echo "$G1" | awk -F', ' '{print $7}')

  RES=$(awk -v k="${KV:-0}" -v c="$CAP" 'BEGIN{printf "%d", k*c}')
  KVP=$(awk -v k="${KV:-0}" 'BEGIN{printf "%.1f", k*100}')

  printf '%-8s %4s %4s %6s%% %9s  %6s %6s  %4s %4s  %5s %5s %4s\n' \
    "${T:-–}" "${RUNQ:-–}" "${WAIT:-–}" "${KVP:-–}" "${RES:-–}" \
    "${g0m:-–}" "${g1m:-–}" "${g0u:-–}" "${g1u:-–}" "${g0w:-–}" "${g1w:-–}" "${PRE:-0}"
  sleep 2
done
