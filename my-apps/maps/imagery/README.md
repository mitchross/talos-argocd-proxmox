# Imagery — self-hosted satellite tiles at maps.vanillax.me/imagery

A caching proxy for public-domain USGS aerial imagery. It gives the home stack a satellite basemap
with no API key. No client ever contacts a third party: phones ask `maps.vanillax.me`, and this pod
fetches each tile from USGS once and then serves it from disk.

## What runs

- **Source:** the USGS National Map orthoimagery tile service
  (`basemap.nationalmap.gov/.../USGSImageryOnly`). US federal data is public domain; attribution
  is "USDA, USGS The National Map: Orthoimagery". Detail is street-level (zoom 16) across the US.
  Canada and Mexico get the service's lower-detail regional imagery.
- **Server:** `nginx-unprivileged` with `proxy_cache`. Config is in `nginx-imagery.conf`.
- **Cache:** 100 Gi Longhorn PVC `imagery-cache`, capped at 90 GB by nginx, least-recently-used
  eviction. It is backup-exempt because it refills from the source.
- **URL:** `https://maps.vanillax.me/imagery/{z}/{x}/{y}.jpg` (XYZ, zoom 0–16). The style that uses
  it is `https://maps.vanillax.me/styles/satellite.json`, served by `../versatiles`' map-styles
  nginx.

Cached tiles are kept 30 days before nginx revalidates them. While USGS is unreachable, nginx
serves the stale copy, so the basemap keeps working through upstream outages once an area has been
viewed.

## Check it

```bash
curl -sI https://maps.vanillax.me/imagery/12/1073/1506.jpg | grep -i x-cache-status   # MISS, then HIT
curl -s https://maps.vanillax.me/styles/satellite.json | head -c 80
```

Zoom levels above 16 return 404 on purpose.

## Rollback

Delete this directory and `styles/satellite.json` from `../versatiles`, then sync. Radar NG falls
back to its bundled satellite style.
