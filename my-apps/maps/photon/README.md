# Photon — self-hosted geocoding for the cluster

[Photon](https://github.com/komoot/photon) is an open-source geocoder built on OpenStreetMap data. It
gives the home stack place search ("Grand Rapids") and reverse geocoding (coordinates → nearest
place name) without calling a public service or holding an API key.

Its first consumer is Radar NG. The tile server proxies `/api/geocode` and `/api/reverse-geocode` to
`http://photon.photon.svc.cluster.local:2322`, so phones never reach Photon directly. Other apps in
the cluster can use the same Service.

## What runs

- **Image:** `rtuszik/photon-docker:2.4.0`, pinned by digest. It is a community image that
  downloads a prebuilt Photon index on first start. Upstream publishes no official container.
- **Region:** `north-america`, which covers the US, Canada and Mexico. About 30 GB compressed.
- **Storage:** 150 Gi Longhorn PVC `photon-data`, backup-exempt. An empty volume re-downloads the
  index, so a cluster rebuild needs no restore.
- **Network:** a ClusterIP Service on port 2322 only. There is no HTTPRoute because nothing outside
  the cluster should call Photon.

## First start

The container downloads and unpacks the index before Photon listens on port 2322. Expect 30–90
minutes, depending on WAN speed. The startup probe allows up to 4 hours; the pod stays `0/1 Ready`
the whole time, which is expected.

Check progress and the result:

```bash
kubectl -n photon logs deploy/photon -f
kubectl -n photon exec deploy/photon -- curl -s 'localhost:2322/api?q=grand%20rapids&limit=1'
```

A ready instance returns GeoJSON with a `Grand Rapids` feature.

## Updates

`UPDATE_STRATEGY=SEQUENTIAL` with `UPDATE_INTERVAL=60d` makes the container download a fresh index
when the current one is older than 60 days. Search is unavailable while it swaps; Radar NG shows
"city search unavailable" in the meantime. To force a refresh, set `FORCE_UPDATE=TRUE`, sync, then
remove it again.

## Rollback

Delete the directory and sync. Radar NG's geocoding routes then answer 503
(`geocoding_not_configured` if `PHOTON_URL` is also removed from the tile server, or 502 if it still
points here) and the rest of the app keeps working.
