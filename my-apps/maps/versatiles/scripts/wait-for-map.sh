#!/bin/sh
echo "waiting for /data/osm.versatiles..."
until [ -s /data/osm.versatiles ]; do
  sleep 5
done
echo "found archive, starting server"

