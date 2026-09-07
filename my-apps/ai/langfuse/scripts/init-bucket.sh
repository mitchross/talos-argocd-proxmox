#!/usr/bin/env bash
set -euo pipefail

endpoint=http://192.168.10.133:30292
bucket=langfuse
error_file=$(mktemp)
trap 'rm -f "$error_file"' EXIT

if ! aws --endpoint-url "$endpoint" s3api head-bucket --bucket "$bucket" 2>"$error_file"; then
  if ! grep -Eq '\(404\)|NoSuchBucket|Not Found' "$error_file"; then
    cat "$error_file" >&2
    exit 1
  fi
  aws --endpoint-url "$endpoint" s3api create-bucket --bucket "$bucket"
fi

aws --endpoint-url "$endpoint" s3api put-bucket-cors \
  --bucket "$bucket" --cors-configuration file:///scripts/bucket-cors.json
printf 'Langfuse bucket and browser CORS are ready.\n'
