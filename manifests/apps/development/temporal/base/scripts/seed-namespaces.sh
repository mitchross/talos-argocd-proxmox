#!/bin/sh
# Seeds Temporal user namespaces. Run as a PostSync Job after the
# Temporal frontend Deployment is ready. Idempotent — safe to re-run on
# every deploy; existing namespaces are skipped.
#
# Add more namespaces to the loop below as the app fleet grows.
set -eu

FRONTEND="temporal-frontend:7233"

# Wait for the frontend to accept RPCs. After a cluster nuke or fresh
# CNPG bootstrap this can take a minute (Temporal has to finish SQL
# schema bootstrap before it starts serving). 20 retries × 10s = 200s.
echo "[seed] waiting for frontend at $FRONTEND..."
for i in $(seq 1 20); do
  if temporal --address "$FRONTEND" operator namespace list >/dev/null 2>&1; then
    echo "[seed] frontend reachable"
    break
  fi
  echo "[seed] not ready yet (attempt $i/20), sleeping 10s..."
  sleep 10
done

# Namespaces to ensure exist. Listed here instead of parameterized via
# env var so a grep in the repo finds every namespace we use.
for NS in default; do
  echo "[seed] ensuring namespace: $NS"
  if temporal --address "$FRONTEND" operator namespace describe -n "$NS" >/dev/null 2>&1; then
    echo "[seed]   already exists"
  else
    temporal --address "$FRONTEND" operator namespace create \
      --retention 168h \
      --description "Default user namespace (GitOps-seeded)" \
      -n "$NS"
    echo "[seed]   created"
  fi
done

echo "[seed] final namespace list:"
temporal --address "$FRONTEND" operator namespace list | grep "NamespaceInfo.Name"
echo "[seed] done."
