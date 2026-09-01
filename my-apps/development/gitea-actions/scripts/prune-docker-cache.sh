#!/bin/sh
while true; do
  # Wait for dockerd before first prune (pod fresh-start case)
  for _ in $(seq 1 30); do
    docker info >/dev/null 2>&1 && break
    sleep 2
  done
  echo "[prune] starting cycle at $(date -u)"
  docker buildx prune -af --keep-storage 20GB --filter until=24h 2>&1 || true
  docker system prune -af --filter "until=72h" 2>&1 || true
  df -h /var/lib/docker 2>/dev/null || true
  sleep 21600
done
