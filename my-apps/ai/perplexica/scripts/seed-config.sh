#!/bin/sh
set -eu
umask 077
: "${LITELLM_API_KEY:?LiteLLM credential must be present}"
apk add --no-cache jq >/dev/null
SEED=/seed/config.json
DEST=/data/config.json
mkdir -p /data
seed_with_key=$(mktemp)
trap 'rm -f "$seed_with_key" "$DEST.tmp"' EXIT
jq '(.modelProviders[] | select(.id == "llama-cpp-cluster") | .config.apiKey) = env.LITELLM_API_KEY' \
  "$SEED" > "$seed_with_key"
if [ ! -s "$DEST" ]; then
  cp "$seed_with_key" "$DEST.tmp"
else
  jq --slurpfile seed "$seed_with_key" \
     '.modelProviders = (
        ($seed[0].modelProviders | map(.id)) as $owned
        | [(.modelProviders // [])[] | select(.id as $id | $owned | index($id) | not)]
          + $seed[0].modelProviders
        | map(if ((.config.baseURL // "") | rtrimstr("/")
                   | IN("http://llama-cpp-service.llama-cpp.svc.cluster.local:8080/v1",
                        "http://vllm-service.vllm.svc.cluster.local:8080/v1"))
              then .config.baseURL = "http://litellm-service.litellm.svc.cluster.local:4000/v1"
                   | .config.apiKey = env.LITELLM_API_KEY
              else . end))
      | .search = ((.search // {}) + $seed[0].search)' \
     "$DEST" > "$DEST.tmp"
fi
chmod 600 "$DEST.tmp"
mv "$DEST.tmp" "$DEST"
echo "[seed] authenticated gateway provider reconciled; UI preferences preserved"
