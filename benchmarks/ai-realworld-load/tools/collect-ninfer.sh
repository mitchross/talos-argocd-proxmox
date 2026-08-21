#!/usr/bin/env bash
# Candidate collector — NInfer run capture, structurally parallel to collect.sh
# (which remains the untouched vLLM control collector).
#
# NInfer has NO Prometheus endpoint. The authoritative per-request source is the
# schema-v8 request-log JSONL the server writes to /logs (emptyDir). Streams:
#   1. request-log JSONL  (tail -n0 -F: only events inside the run window)
#   2. per-GPU telemetry  (nvidia-smi loop in the powerlimit DaemonSet)
#   3. server stderr log  (throughput lines + errors)
#   4. pod state          (phase/ready/restarts, 10s)
# stop additionally copies the FULL JSONL (server_start KV ledger + history).
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNS="$ROOT/runs"
STATE="$ROOT/.current-run-ninfer"
NS=ninfer

die() { echo "ERROR: $*" >&2; exit 1; }

ninfer_pod() {
  kubectl -n "$NS" get pod -l app=ninfer-server \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null
}

cmd_start() {
  local label="${1:-ninfer}"
  [ -f "$STATE" ] && die "a ninfer run is already active ($(cat "$STATE")). Run: collect-ninfer.sh stop"

  local pod; pod="$(ninfer_pod)"
  [ -n "$pod" ] || die "no ninfer-server pod found"
  # Runtime image ships no curl; health is checked from the host via the LAN route.
  curl -skf -o /dev/null --max-time 10 https://ninfer.vanillax.me/health \
    || die "ninfer /health not OK — refusing to start a run against an unhealthy server"

  local ts run
  ts="$(date -u +%Y%m%dT%H%M%SZ)"
  run="$RUNS/${ts}_${label}"
  mkdir -p "$run"
  echo "$run" > "$STATE"

  {
    echo "run_started_utc=$ts"
    echo "label=$label"
    echo "backend=ninfer-3090"
    echo "pod=$pod"
    echo "image=$(kubectl -n $NS get pod "$pod" -o jsonpath='{.spec.containers[0].image}')"
    echo "node=$(kubectl -n $NS get pod "$pod" -o jsonpath='{.spec.nodeName}')"
    echo "git_head=$(git -C "$ROOT" rev-parse HEAD 2>/dev/null)"
  } > "$run/context.env"

  kubectl -n "$NS" get deploy ninfer-server -o jsonpath='{.spec.template.spec.containers[0].args}' \
    > "$run/ninfer-args.json" 2>/dev/null
  curl -sk --max-time 10 https://ninfer.vanillax.me/v1/models > "$run/models.json" 2>/dev/null

  # ---- Stream 1: request-log JSONL, run-window only -------------------------
  nohup kubectl -n "$NS" exec "$pod" -- tail -n0 -F /logs/serve.requests.jsonl \
    > "$run/requests.jsonl.stream" 2>"$run/requests.err" &
  echo $! > "$run/.pid.requests"

  # ---- Stream 2: per-GPU telemetry (never from the pod under test) ----------
  local dspod
  dspod="$(kubectl -n gpu-operator get pod -l app=nvidia-powerlimit -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)"
  [ -n "$dspod" ] || dspod="$(kubectl -n gpu-operator get pods -o name 2>/dev/null | grep powerlimit | head -1 | cut -d/ -f2)"
  [ -n "$dspod" ] || die "no nvidia-powerlimit pod found for GPU sampling"
  nohup kubectl -n gpu-operator exec "$dspod" -- \
    nvidia-smi --query-gpu=timestamp,index,memory.used,memory.total,utilization.gpu,utilization.memory,power.draw,power.limit,temperature.gpu,pcie.link.gen.current,pcie.link.width.current \
               --format=csv,noheader,nounits -l 2 \
    > "$run/gpu.csv" 2>"$run/gpu.err" &
  echo $! > "$run/.pid.gpu"
  echo "gpu_source=gpu-operator/$dspod" >> "$run/context.env"

  # ---- Stream 3: server log (5s throughput lines, errors) -------------------
  nohup kubectl -n "$NS" logs -f "$pod" --since=10s \
    > "$run/ninfer.log" 2>"$run/ninfer-log.err" &
  echo $! > "$run/.pid.logs"

  # ---- Stream 4: pod state, 10s --------------------------------------------
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
  echo "started 4 streams (requests JSONL / gpu 2s / logs follow / pod 10s)"
}

cmd_stop() {
  [ -f "$STATE" ] || die "no active ninfer run"
  local run; run="$(cat "$STATE")"

  for f in "$run"/.pid.*; do
    [ -e "$f" ] || continue
    kill "$(cat "$f")" 2>/dev/null
    rm -f "$f"
  done
  sleep 1
  pkill -f "kubectl -n $NS exec.*serve.requests.jsonl" 2>/dev/null

  local pod; pod="$(ninfer_pod)"
  echo "run_ended_utc=$(date -u +%Y%m%dT%H%M%SZ)" >> "$run/context.env"
  # Full JSONL: contains server_start (KV sizing ledger, arenas, argv) + all requests.
  kubectl -n "$NS" exec "$pod" -- cat /logs/serve.requests.jsonl \
    > "$run/requests.jsonl" 2>/dev/null
  kubectl -n "$NS" get events --sort-by=.lastTimestamp > "$run/events.txt" 2>/dev/null

  rm -f "$STATE"
  echo "stopped. RUN=$run"
  echo "next: tools/report-ninfer.py \"$run\""
}

cmd_status() {
  if [ -f "$STATE" ]; then
    local run; run="$(cat "$STATE")"
    echo "ACTIVE: $run"
    echo "request events: $(wc -l < "$run/requests.jsonl.stream" 2>/dev/null || echo 0)"
    echo "gpu samples:    $(wc -l < "$run/gpu.csv" 2>/dev/null || echo 0)"
  else
    echo "no active ninfer run"
  fi
}

case "${1:-}" in
  start)  shift; cmd_start "$@" ;;
  stop)   cmd_stop ;;
  status) cmd_status ;;
  *) echo "usage: $0 {start [label]|stop|status}"; exit 1 ;;
esac
