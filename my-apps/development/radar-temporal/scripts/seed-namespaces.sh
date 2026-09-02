#!/bin/sh
# Seeds the Radar Temporal control plane's user namespace. Run as a
# PostSync Job after the frontend Deployment is ready. Idempotent — safe
# to re-run on every deploy; an existing namespace is skipped.
set -eu

FRONTEND="${FRONTEND:-radar-temporal-frontend:7233}"
SEED_RETRIES="${SEED_RETRIES:-20}"
SEED_SLEEP_SECONDS="${SEED_SLEEP_SECONDS:-10}"
SEED_RPC_TIMEOUT_SECONDS="${SEED_RPC_TIMEOUT_SECONDS:-30}"

temporal_rpc() {
  timeout "$SEED_RPC_TIMEOUT_SECONDS" temporal --address "$FRONTEND" "$@"
}

# Wait for the frontend to accept RPCs. On a fresh database this can take
# a minute (SQL schema bootstrap finishes before serving). 20 × 10s = 200s.
echo "[seed] waiting for frontend at $FRONTEND..."
frontend_ready=0
for i in $(seq 1 "$SEED_RETRIES"); do
  if temporal_rpc operator namespace list >/dev/null 2>&1; then
    echo "[seed] frontend reachable"
    frontend_ready=1
    break
  fi
  echo "[seed] not ready yet (attempt $i/$SEED_RETRIES), sleeping ${SEED_SLEEP_SECONDS}s..."
  sleep "$SEED_SLEEP_SECONDS"
done

if [ "$frontend_ready" != 1 ]; then
  echo "[seed] frontend did not become reachable after $SEED_RETRIES attempts" >&2
  exit 1
fi

# Only `radar-ng` lives on this control plane — no `default`, so nothing
# lands here by accident. Named here (not an env var) so a repo grep finds it.
NS="radar-ng"
echo "[seed] ensuring namespace: $NS"
if temporal_rpc operator namespace describe -n "$NS" >/dev/null 2>&1; then
  echo "[seed]   already exists"
else
  temporal_rpc operator namespace create \
    --retention 168h \
    --description "Radar NG application namespace (GitOps-seeded)" \
    -n "$NS"
  echo "[seed]   created"
fi

echo "[seed] final namespace list:"
temporal_rpc operator namespace list | grep "NamespaceInfo.Name"
echo "[seed] done."
