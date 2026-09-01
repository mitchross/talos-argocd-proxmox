#!/bin/sh
until test -f /data/root-writer.txt; do sleep 1; done
cat /data/root-writer.txt
for file in /data/*; do
  test -f "$file" || continue
  stat -c '%n ownership=%u:%g mode=%a' "$file"
done
sleep 3600

