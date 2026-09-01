#!/bin/sh
find /var/lib/grafana/dashboards/kubernetes \
  -maxdepth 1 -type f -name '*.json' -delete 2>/dev/null || true
find /var/lib/grafana/dashboards/infrastructure \
  -maxdepth 1 -type f -name 'vpa-autoscaling.json' -delete 2>/dev/null || true

