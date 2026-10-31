#!/bin/sh
set -eu
apply() {
  echo "=== Applying lifecycle to s3://$1 ==="
  aws --endpoint-url http://192.168.10.133:30292 \
    s3api put-bucket-lifecycle-configuration \
    --bucket "$1" \
    --lifecycle-configuration "file:///lifecycle/$2"
  echo "=== Verifying ==="
  aws --endpoint-url http://192.168.10.133:30292 \
    s3api get-bucket-lifecycle-configuration \
    --bucket "$1"
}
apply postgres-backups lifecycle.json
apply loki loki-lifecycle.json
