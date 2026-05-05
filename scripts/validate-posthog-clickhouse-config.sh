#!/usr/bin/env bash
# validate-posthog-clickhouse-config.sh - catches PostHog ClickHouse cluster
# definitions that are not reachable from PostHog application pods.

set -euo pipefail

CONFIG_FILE="my-apps/development/posthog/config/clickhouse/config.d/default.xml"
DEPLOYMENT_FILE="my-apps/development/posthog/data-layer/clickhouse.yaml"
CLICKHOUSE_LOCAL_FQDN="clickhouse.clickhouse-headless.posthog.svc.cluster.local"
ERRORS=0

echo "=== PostHog ClickHouse Config Validation ==="
echo ""

if [ ! -f "$CONFIG_FILE" ]; then
  echo "ERROR: $CONFIG_FILE not found"
  exit 1
fi

echo "--- Check 1: Cluster hosts are pod-reachable ---"

if grep -n "<host>127.0.0.1</host>" "$CONFIG_FILE"; then
  echo "  ERROR: remote_servers contains 127.0.0.1"
  echo "         PostHog migration pods read system.clusters and connect via native TCP."
  echo "         127.0.0.1 points at the migration pod, not the ClickHouse pod."
  ERRORS=$((ERRORS + 1))
else
  echo "  OK: No cluster host points at migration-pod localhost"
fi

echo ""
echo "--- Check 2: Single-node clusters use the ClickHouse pod FQDN ---"

host_count=$(grep -c "<host>${CLICKHOUSE_LOCAL_FQDN}</host>" "$CONFIG_FILE" || true)
if [ "$host_count" -ne 9 ]; then
  echo "  ERROR: Expected 9 remote_servers hosts to use ${CLICKHOUSE_LOCAL_FQDN}, found $host_count"
  echo "         The name must resolve from PostHog pods and still identify as local in system.clusters."
  ERRORS=$((ERRORS + 1))
else
  echo "  OK: All 9 PostHog ClickHouse clusters use ${CLICKHOUSE_LOCAL_FQDN}"
fi

echo ""
echo "--- Check 3: ClickHouse pod DNS identity is stable ---"

if ! grep -q "^[[:space:]]*hostname: clickhouse$" "$DEPLOYMENT_FILE"; then
  echo "  ERROR: ClickHouse pod spec must set hostname: clickhouse"
  ERRORS=$((ERRORS + 1))
elif ! grep -q "^[[:space:]]*subdomain: clickhouse-headless$" "$DEPLOYMENT_FILE"; then
  echo "  ERROR: ClickHouse pod spec must set subdomain: clickhouse-headless"
  ERRORS=$((ERRORS + 1))
else
  echo "  OK: ClickHouse pod has a stable DNS identity"
fi

echo ""
if [ "$ERRORS" -gt 0 ]; then
  echo "Validation failed with $ERRORS error(s)"
  exit 1
fi

echo "Validation passed"
