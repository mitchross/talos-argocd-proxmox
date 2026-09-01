#!/bin/sh
printf 'root-writer\n' > /data/root-writer.txt
stat -c 'root-writer ownership=%u:%g mode=%a' /data/root-writer.txt
sleep 3600

