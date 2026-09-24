# Map raster — the VersaTiles basemap as PNG

[tileserver-gl](https://github.com/maptiler/tileserver-gl) renders the same `light` and `dark`
styles the phone uses into PNG images. It serves clients that can't draw vector maps: Radar NG's
Apple Watch app, its home-screen/CarPlay widget and, later, CarPlay. They previously used Apple
MapKit; this keeps them on the home stack with no third-party map service.

## What runs

- **Image:** `maptiler/tileserver-gl:v5.6.0`, pinned by digest, running as uid 1000.
- **Styles:** `styles/light.json` and `styles/dark.json`. These are the in-cluster copies written by
  `../versatiles/styles/generate.mjs`, reading tiles, glyphs and sprites straight from the
  `versatiles` Service (no hairpin through Cloudflare). Don't edit them by hand; re-run the
  generator.
- **URL:** `https://maps.vanillax.me/raster/`, with the prefix stripped by the HTTPRoute. No storage;
  renders are on demand, typically under a second.

## Endpoints

| URL | Returns |
|---|---|
| `/raster/styles/{light,dark}/static/{lon},{lat},{zoom}/{w}x{h}@2x.png` | one image centred on a point. `zoom` uses MapLibre's 512-px convention, so it is one less than the 256-px XYZ zoom. |
| `/raster/styles/{light,dark}/256/{z}/{x}/{y}.png` | 256-px XYZ tiles |
| `/raster/health` | liveness/readiness |

Limits: images up to 1024 px per side, scale up to @3x.

## Check it

```bash
curl -s -o /tmp/static.png -w '%{http_code}\n' \
  'https://maps.vanillax.me/raster/styles/dark/static/-85.668,42.963,6/184x224@2x.png'
```

## Rollback

Delete this directory and sync. The Watch and widget then show their "map unavailable" state
behind the radar overlay.
