#!/bin/sh
set -eu

python /opt/repo-scripts/patch-replay-retention.py
exec ./bin/docker-server
