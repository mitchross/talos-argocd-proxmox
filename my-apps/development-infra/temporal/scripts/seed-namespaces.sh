#!/bin/sh
# PostSync seeds missing Temporal namespaces after the frontend is ready; safe to rerun.
set -eu

FRONTEND="${FRONTEND:-temporal-frontend:7233}"
SEED_RETRIES="${SEED_RETRIES:-20}"
SEED_SLEEP_SECONDS="${SEED_SLEEP_SECONDS:-10}"
SEED_RPC_TIMEOUT_SECONDS="${SEED_RPC_TIMEOUT_SECONDS:-30}"

temporal_rpc() {
  timeout "$SEED_RPC_TIMEOUT_SECONDS" temporal --address "$FRONTEND" "$@"
}

# Wait for schema initialization before sending namespace RPCs.
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

# Keep radar-ng histories and task queues isolated; default serves workloads not yet migrated.
for NS in default radar-ng; do
  echo "[seed] ensuring namespace: $NS"
  if temporal_rpc operator namespace describe -n "$NS" >/dev/null 2>&1; then
    echo "[seed]   already exists"
  else
    DESCRIPTION="Application namespace (GitOps-seeded)"
    if [ "$NS" = "default" ]; then
      DESCRIPTION="Default user namespace (GitOps-seeded)"
    fi
    temporal_rpc operator namespace create \
      --retention 168h \
      --description "$DESCRIPTION" \
      -n "$NS"
    echo "[seed]   created"
  fi
done

echo "[seed] final namespace list:"
temporal_rpc operator namespace list | grep "NamespaceInfo.Name"
echo "[seed] done."
