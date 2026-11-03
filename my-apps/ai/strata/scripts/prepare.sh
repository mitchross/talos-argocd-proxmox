#!/bin/sh
# docker-entrypoint.sh's first-start setup.py call, run once as an init step; later starts skip it.
# setup.py pins the GGUF and MTP revisions (HF_REVISIONS, tools/mtp_fetch.py); REINSTALL=1 redoes it.
set -eu
cd /opt/strata
tag="$(printf '%s' "$MODEL" | tr 'A-Z' 'a-z')"
cfg="$STRATA_DATA/config/strata-$tag.json"
if [ -f "$cfg" ] && [ "${REINSTALL:-0}" != "1" ]; then
  echo "Already prepared: $cfg"
  exit 0
fi
mkdir -p "$STRATA_DATA/config"
.venv/bin/python setup.py --setup --yes --no-start \
  --family "$FAMILY" --model "$MODEL" --context "$CONTEXT" --vision "$VISION" \
  --kv "$KV" --low-ram "$LOW_RAM" --kv-streaming "$KV_STREAMING" --gpu "$GPU" \
  --data-dir "$STRATA_DATA" --host "$HOST" --port "$PORT" --api-key ""
cp -f "/opt/strata/strata-$tag.json" "$cfg"
echo "Prepared: $cfg"
