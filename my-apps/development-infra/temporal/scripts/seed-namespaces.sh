#!/bin/sh
# Seeds Temporal user namespaces. Run as a PostSync Job after the
# Temporal frontend Deployment is ready. Idempotent — safe to re-run on
# every deploy; existing namespaces are skipped.
#
# Add more namespaces to the loop below as the app fleet grows.
set -eu

FRONTEND="${FRONTEND:-temporal-frontend:7233}"
SEED_RETRIES="${SEED_RETRIES:-20}"
SEED_SLEEP_SECONDS="${SEED_SLEEP_SECONDS:-10}"
SEED_RPC_TIMEOUT_SECONDS="${SEED_RPC_TIMEOUT_SECONDS:-30}"

temporal_rpc() {
  timeout "$SEED_RPC_TIMEOUT_SECONDS" temporal --address "$FRONTEND" "$@"
}

# Wait for the frontend to accept RPCs. After a cluster nuke or fresh
# CNPG bootstrap this can take a minute (Temporal has to finish SQL
# schema bootstrap before it starts serving). 20 retries × 10s = 200s.
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

# How long Temporal keeps a closed workflow before deleting it.
# radar-ng runs ~4,600 workflows a day, so it keeps 2 days; the rest keep 7.
retention_for() {
  case "$1" in
    radar-ng) echo 48h ;;
    *) echo 168h ;;
  esac
}

# Namespaces to ensure exist. Listed here instead of parameterized via
# env var so a grep in the repo finds every namespace we use.
# One namespace per app keeps histories, schedules and task queues apart.
# `default` stays so nothing breaks before an app has moved.
for NS in default radar-ng deal-scout deal-scout-beta news-reader; do
  echo "[seed] ensuring namespace: $NS"
  RETENTION=$(retention_for "$NS")
  if temporal_rpc operator namespace describe -n "$NS" >/dev/null 2>&1; then
    echo "[seed]   already exists; setting retention $RETENTION"
    # Existing namespaces keep their create-time retention unless updated here.
    temporal_rpc operator namespace update --retention "$RETENTION" -n "$NS"
  else
    DESCRIPTION="Application namespace (GitOps-seeded)"
    if [ "$NS" = "default" ]; then
      DESCRIPTION="Default user namespace (GitOps-seeded)"
    fi
    temporal_rpc operator namespace create \
      --retention "$RETENTION" \
      --description "$DESCRIPTION" \
      -n "$NS"
    echo "[seed]   created"
  fi
done

echo "[seed] final namespace list:"
temporal_rpc operator namespace list | grep "NamespaceInfo.Name"
echo "[seed] done."
