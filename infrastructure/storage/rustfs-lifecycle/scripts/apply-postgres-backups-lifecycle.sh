#!/bin/sh
set -eu
echo "=== Applying lifecycle to s3://postgres-backups ==="
aws --endpoint-url http://192.168.10.133:30292 \
  s3api put-bucket-lifecycle-configuration \
  --bucket postgres-backups \
  --lifecycle-configuration file:///lifecycle/lifecycle.json
echo "=== Verifying ==="
aws --endpoint-url http://192.168.10.133:30292 \
  s3api get-bucket-lifecycle-configuration \
  --bucket postgres-backups

