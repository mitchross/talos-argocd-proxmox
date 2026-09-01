#!/bin/sh
printf 'nonroot-writer\n' > /data/nonroot-writer.txt
owner="$(stat -c '%u:%g' /data/nonroot-writer.txt)"
printf 'nonroot-writer ownership=%s\n' "$owner"
test "$owner" = "1000:1000"
sleep 3600

