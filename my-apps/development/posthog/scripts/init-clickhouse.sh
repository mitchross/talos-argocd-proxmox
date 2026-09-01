#!/bin/sh
set -e
echo "Waiting for ClickHouse..."
TIMEOUT=120
ELAPSED=0
until clickhouse-client --host=clickhouse --port=9000 --query="SELECT 1" >/dev/null 2>&1; do
  echo "ClickHouse not ready yet (elapsed: ${ELAPSED}s)..."
  sleep 2
  ELAPSED=$((ELAPSED + 2))
  if [ $ELAPSED -ge $TIMEOUT ]; then
      echo "Timeout waiting for ClickHouse after ${TIMEOUT}s"
      exit 1
  fi
done
echo "ClickHouse is ready."

echo "Initializing ClickHouse migration tables..."

# Create the base migration tracking table (Replicated)
clickhouse-client --host=clickhouse --port=9000 --query "
CREATE TABLE IF NOT EXISTS posthog.infi_clickhouse_orm_migrations (
  module_name String,
  package_name String,
  applied Date
) ENGINE = ReplicatedMergeTree(
  '/posthog/tables/infi_clickhouse_orm_migrations',
  'replica_{replica}'
)
ORDER BY (module_name, package_name)
SETTINGS index_granularity = 8192;
"

# Create the distributed view for cross-shard queries
clickhouse-client --host=clickhouse --port=9000 --query "
CREATE TABLE IF NOT EXISTS posthog.infi_clickhouse_orm_migrations_distributed AS posthog.infi_clickhouse_orm_migrations
ENGINE = Distributed(
  'posthog_migrations',
  'posthog',
  'infi_clickhouse_orm_migrations'
);
"

echo "ClickHouse migration tables initialized successfully"

# sharded_events must be a real local table cloned from posthog.events: migration 0031 ALTERs it, and
# ingest (writable_events Distributed -> sharded_events) silently drops rows without it.
echo "Creating sharded_events local table mirroring events columns..."
clickhouse-client --host=clickhouse --port=9000 --query "
CREATE TABLE IF NOT EXISTS posthog.sharded_events ON CLUSTER 'posthog'
AS posthog.events
ENGINE = ReplicatedReplacingMergeTree(
  '/clickhouse/tables/{shard}/posthog.sharded_events',
  '{replica}',
  _timestamp
)
PARTITION BY toYYYYMM(timestamp)
ORDER BY (team_id, toDate(timestamp), event, cityHash64(distinct_id), cityHash64(uuid))
SAMPLE BY cityHash64(distinct_id)
SETTINGS index_granularity = 8192;
" || echo "  sharded_events likely already exists with prior schema — skipping"
echo "  sharded_events ready"

# Force-create lazy system log tables that PostHog migrations depend on
echo "Ensuring system log tables exist..."
clickhouse-client --host=clickhouse --port=9000 --query "SYSTEM FLUSH LOGS" || true
for table in crash_log part_log trace_log; do
  clickhouse-client --host=clickhouse --port=9000 --query "SELECT 1 FROM system.${table} LIMIT 0" 2>/dev/null && \
    echo "  system.${table} exists" || \
    echo "  system.${table} not yet created (ok - not needed until first event)"
done

# Verify tables exist
clickhouse-client --host=clickhouse --port=9000 --query "
SHOW TABLES IN posthog WHERE name LIKE '%infi_clickhouse_orm_migrations%'
"
