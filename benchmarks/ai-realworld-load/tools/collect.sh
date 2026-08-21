#!/usr/bin/env bash
# Baseline A collector — real-world three-way load on the dual-3090 vLLM endpoint.
#
# NOT ArgoCD-managed. benchmarks/ is outside every AppSet glob (my-apps/*/*,
# infrastructure explicit list, monitoring/*, infrastructure/database/*/*).
# Nothing here deploys; it only reads.
#
# Design note: samples via THREE long-lived streams rather than per-tick
# `kubectl exec`. A 2s exec loop costs ~0.5-1s of kubectl overhead per tick and
# would jitter the sample interval badly. nvidia-smi has a native `-l` loop and
# the metrics/log streams run their loop inside the pod, so the only per-sample
# cost is network read.
#
# Usage:
#   collect.sh start [label]   -> begins capture, prints RUN dir
#   collect.sh stop            -> stops capture, finalizes
#   collect.sh status          -> is it running?
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNS="$ROOT/runs"
STATE="$ROOT/.current-run"
# Defaults preserve the historical vLLM control. BENCH_* overrides can target
# another backend only when it exposes the same vLLM metrics contract.
NS=${BENCH_NS:-vllm}
APP=${BENCH_APP:-vllm-server}
DEPLOY=${BENCH_DEPLOY:-vllm-server}
PORT=${BENCH_PORT:-8000}

die() { echo "ERROR: $*" >&2; exit 1; }

vllm_pod() {
  kubectl -n "$NS" get pod -l "app=$APP" \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null
}

cmd_start() {
  local label="${1:-baseline-a}"
  [ -f "$STATE" ] && die "a run is already active ($(cat "$STATE")). Run: collect.sh stop"

  local pod; pod="$(vllm_pod)"
  [ -n "$pod" ] || die "no $APP pod found in $NS"
  kubectl -n "$NS" exec "$pod" -- curl -sf -o /dev/null "http://localhost:$PORT/health" \
    || die "vLLM /health not OK — refusing to start a run against an unhealthy server"

  local ts run
  ts="$(date -u +%Y%m%dT%H%M%SZ)"
  run="$RUNS/${ts}_${label}"
  mkdir -p "$run"
  echo "$run" > "$STATE"

  # ---- Immutable run context: what this baseline actually ran against. -------
  {
    echo "run_started_utc=$ts"
    echo "label=$label"
    echo "bench_ns=$NS"
    echo "bench_app=$APP"
    echo "bench_deploy=$DEPLOY"
    echo "bench_port=$PORT"
    echo "pod=$pod"
    echo "image=$(kubectl -n "$NS" get pod "$pod" -o jsonpath='{.spec.containers[0].image}')"
    echo "image_id=$(kubectl -n "$NS" get pod "$pod" -o jsonpath='{.status.containerStatuses[0].imageID}')"
    echo "node=$(kubectl -n "$NS" get pod "$pod" -o jsonpath='{.spec.nodeName}')"
    echo "git_head=$(git -C "$ROOT" rev-parse HEAD 2>/dev/null)"
  } > "$run/context.env"

  kubectl -n "$NS" get deploy "$DEPLOY" -o jsonpath='{.spec.template.spec.containers[0].args}' \
    > "$run/vllm-args.json" 2>/dev/null
  kubectl -n "$NS" get deploy "$DEPLOY" -o jsonpath='{.spec.template.spec.containers[0].env}' \
    > "$run/vllm-env.json" 2>/dev/null
  kubectl -n "$NS" exec "$pod" -- curl -s "http://localhost:$PORT/v1/models" \
    > "$run/models.json" 2>/dev/null
  # KV capacity ceiling is read from the live engine, never hardcoded — the
  # report divides by this to turn kv_cache_usage_perc into resident tokens.
  kubectl -n "$NS" exec "$pod" -- curl -s "http://localhost:$PORT/metrics" 2>/dev/null \
    | grep 'cache_config_info' > "$run/cache-config.txt"

  # ---- Stream 1: vLLM metrics, 2s, filtered inside the pod ------------------
  # Full /metrics is ~40KB; grepping pod-side keeps this to a few hundred bytes
  # per tick. Histogram *buckets* are kept in full: when a request finishes,
  # exactly one bucket increments, which is how per-request sizes get attributed.
  # shellcheck disable=SC2016
  nohup kubectl -n "$NS" exec "$pod" -- sh -c '
    while true; do
      echo "===TICK $(date -u +%Y-%m-%dT%H:%M:%SZ) $(date +%s)"
      curl -s "http://localhost:'"$PORT"'/metrics" | grep -E "^vllm:" | grep -vE "_created|estimated_"
      sleep 2
    done' > "$run/metrics.stream" 2>"$run/metrics.err" &
  echo $! > "$run/.pid.metrics"

  # ---- Stream 2: per-GPU telemetry via nvidia-smi native loop ---------------
  # Runs in the powerlimit DaemonSet, NOT the inference pod, so sampling never
  # competes with the workload under test.
  local dspod
  dspod="$(kubectl -n gpu-operator get pod -l app=nvidia-powerlimit -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)"
  [ -n "$dspod" ] || dspod="$(kubectl -n gpu-operator get pods -o name 2>/dev/null | grep powerlimit | head -1 | cut -d/ -f2)"
  if [ -n "$dspod" ]; then
    nohup kubectl -n gpu-operator exec "$dspod" -- \
      nvidia-smi --query-gpu=timestamp,index,memory.used,memory.total,utilization.gpu,utilization.memory,power.draw,power.limit,temperature.gpu,pcie.link.gen.current,pcie.link.width.current \
                 --format=csv,noheader,nounits -l 2 \
      > "$run/gpu.csv" 2>"$run/gpu.err" &
    echo $! > "$run/.pid.gpu"
    echo "gpu_source=gpu-operator/$dspod" >> "$run/context.env"
  else
    # Fallback: sample from the inference pod itself. Noted explicitly because
    # it is a slightly worse measurement, not an equivalent one.
    nohup kubectl -n "$NS" exec "$pod" -- \
      nvidia-smi --query-gpu=timestamp,index,memory.used,memory.total,utilization.gpu,utilization.memory,power.draw,power.limit,temperature.gpu,pcie.link.gen.current,pcie.link.width.current \
                 --format=csv,noheader,nounits -l 2 \
      > "$run/gpu.csv" 2>"$run/gpu.err" &
    echo $! > "$run/.pid.gpu"
    echo "gpu_source=vllm-pod-fallback" >> "$run/context.env"
  fi

  # ---- Stream 3: full vLLM log for the window ------------------------------
  # Carries the periodic engine line (Running/Waiting/KV%/prefix-hit-rate) and
  # any preemption / cache-allocation / context-length errors.
  nohup kubectl -n "$NS" logs -f "$pod" --since=10s \
    > "$run/vllm.log" 2>"$run/vllm-log.err" &
  echo $! > "$run/.pid.logs"

  # ---- Stream 4: pod resource + restart state, 10s ------------------------
  # shellcheck disable=SC2016
  nohup bash -c '
    while true; do
      printf "%s," "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
      kubectl -n '"$NS"' get pod '"$pod"' \
        -o jsonpath="{.status.phase},{.status.containerStatuses[0].ready},{.status.containerStatuses[0].restartCount},{.status.containerStatuses[0].lastState.terminated.reason}" 2>/dev/null
      echo ""
      sleep 10
    done' > "$run/pod.csv" 2>/dev/null &
  echo $! > "$run/.pid.pod"

  echo "RUN=$run"
  echo "started 4 streams (metrics 2s / gpu 2s / logs follow / pod 10s)"
}

cmd_stop() {
  [ -f "$STATE" ] || die "no active run"
  local run; run="$(cat "$STATE")"
  NS="$(sed -n 's/^bench_ns=//p' "$run/context.env")"
  APP="$(sed -n 's/^bench_app=//p' "$run/context.env")"
  DEPLOY="$(sed -n 's/^bench_deploy=//p' "$run/context.env")"
  PORT="$(sed -n 's/^bench_port=//p' "$run/context.env")"
  [ -n "$NS" ] && [ -n "$APP" ] && [ -n "$DEPLOY" ] && [ -n "$PORT" ] \
    || die "active run is missing its target identity: $run/context.env"

  for f in "$run"/.pid.*; do
    [ -e "$f" ] || continue
    kill "$(cat "$f")" 2>/dev/null
    rm -f "$f"
  done
  sleep 1
  pkill -f "kubectl -n $NS exec.*$PORT/metrics" 2>/dev/null
  pkill -f "nvidia-smi --query-gpu=timestamp" 2>/dev/null

  local pod; pod="$(vllm_pod)"
  echo "run_ended_utc=$(date -u +%Y%m%dT%H%M%SZ)" >> "$run/context.env"
  # Final absolute counters — the run's totals are (final - first tick).
  kubectl -n "$NS" exec "$pod" -- curl -s "http://localhost:$PORT/metrics" 2>/dev/null \
    | grep -E '^vllm:' > "$run/metrics.final"
  kubectl -n "$NS" get events --sort-by=.lastTimestamp > "$run/events.txt" 2>/dev/null

  rm -f "$STATE"
  echo "stopped. RUN=$run"
  echo "next: tools/report.py \"$run\""
}

cmd_status() {
  if [ -f "$STATE" ]; then
    local run; run="$(cat "$STATE")"
    echo "ACTIVE: $run"
    echo "metric ticks: $(grep -c '===TICK' "$run/metrics.stream" 2>/dev/null || echo 0)"
    echo "gpu samples:  $(wc -l < "$run/gpu.csv" 2>/dev/null || echo 0)"
  else
    echo "no active run"
  fi
}

case "${1:-}" in
  start)  shift; cmd_start "$@" ;;
  stop)   cmd_stop ;;
  status) cmd_status ;;
  *) echo "usage: $0 {start [label]|stop|status}"; exit 1 ;;
esac
