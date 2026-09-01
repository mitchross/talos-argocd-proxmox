#!/bin/sh
echo "waiting for /data/basemap.pmtiles..."
until [ -s /data/basemap.pmtiles ]; do
  sleep 5
done
echo "found $(ls -lh /data/basemap.pmtiles)"

