#!/bin/sh
set -e
echo "Waiting for Postgres..."
TIMEOUT=120; ELAPSED=0
until python -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('db', 5432))" 2>/dev/null; do
  sleep 2; ELAPSED=$((ELAPSED + 2))
  [ $ELAPSED -ge $TIMEOUT ] && echo "Postgres timeout" && exit 1
done
echo "Waiting for Redis..."
ELAPSED=0
until python -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('redis7', 6379))" 2>/dev/null; do
  sleep 2; ELAPSED=$((ELAPSED + 2))
  [ $ELAPSED -ge $TIMEOUT ] && echo "Redis timeout" && exit 1
done
# RemoteConfig.sync() diffs against Postgres, not Redis — a wiped Redis is never repaired without force=True (flags go all-false, replay stops).
echo "Force-syncing RemoteConfig to Redis..."
python - <<'PY'
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "posthog.settings")

import django

django.setup()

from posthog.models.remote_config import RemoteConfig

for remote_config in RemoteConfig.objects.all():
    remote_config.sync(force=True)
    print(f"force-synced team {remote_config.team_id}")
PY
echo "RemoteConfig sync complete"

