#!/bin/sh
set -e
echo "Waiting for Postgres..."
TIMEOUT=120; ELAPSED=0
until python -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('db', 5432))" 2>/dev/null; do
  sleep 2; ELAPSED=$((ELAPSED + 2))
  [ $ELAPSED -ge $TIMEOUT ] && echo "Postgres timeout" && exit 1
done
echo "Postgres ready"
echo "Waiting for ClickHouse..."
ELAPSED=0
until wget -q --spider --timeout=2 http://clickhouse:8123/ping 2>/dev/null; do
  sleep 2; ELAPSED=$((ELAPSED + 2))
  [ $ELAPSED -ge $TIMEOUT ] && echo "ClickHouse timeout" && exit 1
done
echo "ClickHouse ready"
echo "Flushing ClickHouse system logs..."
wget -q -O- "http://clickhouse:8123/?query=SYSTEM+FLUSH+LOGS" 2>/dev/null || true
echo "Running Django migrations..."
python manage.py migrate --noinput
# MUST run AFTER manage.py migrate: posthog_person doesn't exist on a fresh DB. IF NOT EXISTS keeps it idempotent.
echo "Applying self-hosted Postgres schema guards..."
python - <<'PY'
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "posthog.settings")

import django

django.setup()

from django.db import connection

with connection.cursor() as cursor:
    cursor.execute(
        "ALTER TABLE public.posthog_person "
        "ADD COLUMN IF NOT EXISTS last_seen_at timestamptz NULL"
    )
    # Library is preloaded via postgres args; without the extension the
    # hourly monitoring task errors in the db log.
    cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
PY
echo "Running ClickHouse migrations..."
python manage.py migrate_clickhouse
# --check is the gate: a pending required migration fails the Job and the sync (beats a silent worker CrashLoop). Never remove.
# Single-node CH gotcha: 0007* queries posthog.sharded_events; if hit, mark Complete in the PostHog admin and re-sync.
echo "Running async ClickHouse migrations..."
python manage.py run_async_migrations || true
python manage.py run_async_migrations --check
echo "All migrations complete"

