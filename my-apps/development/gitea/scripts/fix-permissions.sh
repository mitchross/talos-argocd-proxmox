#!/bin/sh

chown -R 1000:1000 /data
chmod -R 700 /data/git/.ssh 2>/dev/null || true
