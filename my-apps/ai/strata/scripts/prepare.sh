#!/bin/sh
# docker-entrypoint.sh's first-start setup.py call, run as an init step so the server's probes never time out on it.
# Reruns only when the settings change; setup.py pins the GGUF and MTP revisions (HF_REVISIONS, tools/mtp_fetch.py).
set -eu
cd /opt/strata
tag="$(printf '%s' "$MODEL" | tr 'A-Z' 'a-z')"
cfg="$STRATA_DATA/config/strata-$tag.json"
GPU="${GPU:-}" GPUS="${GPUS:-}"
want="$(printf '%s ' "$FAMILY" "$MODEL" "$CONTEXT" "$VISION" "$KV" "$LOW_RAM" "$KV_STREAMING" "$GPU" "$GPUS" "$HOST" "$PORT")"
if [ -f "$cfg" ] && [ "$(cat "$cfg.settings" 2>/dev/null)" = "$want" ]; then
  echo "Already prepared: $cfg ($want)"
  exit 0
fi
mkdir -p "$STRATA_DATA/config"
# GPUS ("0,1"): one model split by layers over several cards (docs/MULTI_GPU.md); GPU: one card.
if [ -n "$GPUS" ]; then set -- --gpus "$GPUS"; else set -- --gpu "${GPU:-0}"; fi
.venv/bin/python setup.py --setup --yes --no-start \
  --family "$FAMILY" --model "$MODEL" --context "$CONTEXT" --vision "$VISION" \
  --kv "$KV" --low-ram "$LOW_RAM" --kv-streaming "$KV_STREAMING" "$@" \
  --data-dir "$STRATA_DATA" --host "$HOST" --port "$PORT" --api-key ""
cp -f "/opt/strata/strata-$tag.json" "$cfg"
printf '%s' "$want" > "$cfg.settings"
echo "Prepared: $cfg ($want)"
