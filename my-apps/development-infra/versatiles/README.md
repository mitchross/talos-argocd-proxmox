# VersaTiles: self-hosted worldwide map at maps.vanillax.me

## What and why

[VersaTiles](https://versatiles.org) is an open-source map stack: a Rust tile
server plus a MapLibre browser frontend. It serves pre-rendered OpenStreetMap
vector tiles from a single archive file. It needs no database, API key, paid
service, or external tile provider.

Deployed here as shared map infrastructure for the cluster. Future consumers
include RadarNG, Project NOMAD, Home Assistant, and anything location-aware.
This is the first phase: upstream VersaTiles as-is, with no custom frontend,
search, or routing.

- **Public URL.** <https://maps.vanillax.me> (pan/zoom world map, keyless)
- **Dataset.** `osm.20260608.versatiles` is the full planet, zoom 0–14, Shortbread
  schema, 62.0 GiB, from <https://download.versatiles.org/> (free, no
  account, sha256-verified).
- **Storage.** TrueNAS SMB share `//192.168.10.133/k8s/versatiles` via static
  PV + PVC `map-data-smb` (comfyui pattern). Chosen for nuke-survival: the
  archive + bootstrap marker live on the NAS, so a rebuilt cluster's bootstrap
  Job finds them and exits in seconds. There is no 62 GiB re-download per rebuild.
  Backup-exempt (the NAS copy is the durable copy). Accepted tradeoff: random
  tile reads over SMB are slower than local NVMe. If that ever matters, add a
  local cache tier in front. Don't move the durable copy.
  **One-time prereq:** create the `versatiles` folder inside the `k8s` SMB
  share on TrueNAS before first deploy (Finder:
  `smb://192.168.10.133/k8s`, then New Folder `versatiles`).
- **Image.** `versatiles/versatiles-frontend:v4.6.0` (server + bundled
  upstream frontend; Renovate manages bumps)

## How it works

```
download.versatiles.org (osm.YYYYMMDD.versatiles + .sha256)
        │  map-bootstrap Job (ArgoCD Sync hook): download → verify → atomic mv
        ▼
map-data-smb PVC → TrueNAS //192.168.10.133/k8s/versatiles (survives cluster rebuilds)
        │  read-only mount; init container blocks until archive exists
        ▼
versatiles Deployment (serve -c config.yaml /data/osm.versatiles)
        ▼
Service :8080 → HTTPRoute (gateway-external) → https://maps.vanillax.me
```

**Bootstrap.** On first sync the `map-bootstrap` hook Job downloads the
archive (~15–60 min depending on WAN speed). The ArgoCD app shows Progressing
the whole time. This is expected. The Job then verifies the published sha256
and atomically renames the archive into place. The server pod's `wait-for-map`
init container blocks until the file exists, so Job and Deployment can deploy
together in any order. On every later sync the Job re-runs but exits in
seconds via a marker file on the PVC (`/data/.bootstrap-marker`, line 1 = the
dataset URL it downloaded).

**Updates (refresh the planet / change dataset).** Edit `DATASET_URL` +
`DATASET_SHA256_URL` in `kustomization.yaml`'s `configMapGenerator` to a newer
`osm.YYYYMMDD.versatiles` from <https://download.versatiles.org/>, commit, and
push. The hash-suffixed ConfigMap name changes, so the Job spec changes, the
hook re-runs, the marker mismatches, and the Job does a fresh download and
atomic swap. The running server keeps serving the **old** file through its open
file descriptor until restarted, so serving never breaks mid-swap. After the
Job completes:

```bash
kubectl -n versatiles rollout restart deploy/versatiles
```

**Manual re-download (same URL).** Delete the marker, then re-run the hook:

```bash
kubectl -n versatiles exec deploy/versatiles -- rm /data/.bootstrap-marker  # (or via the Job pod)
kubectl -n versatiles delete job map-bootstrap   # next sync recreates + re-downloads
```

The server mounts `/data` read-only. If exec-deleting the marker fails,
run a one-off pod that mounts the PVC read-write.

**Rollback.** Point `DATASET_URL` back at the previous `osm.YYYYMMDD`
snapshot (older versioned files stay downloadable for months), commit, wait
for the hook, and restart the Deployment. If a download fails mid-way, nothing
breaks. The partial file is a `.tmp`, the active archive and marker are
untouched, and the Job retries (`backoffLimit: 4`). Then the ArgoCD app shows
Degraded. That is the failure alert path, via the existing ArgoCD sync
alerts.

## Endpoints

- `https://maps.vanillax.me/`: upstream frontend (map viewer)
- `https://maps.vanillax.me/tiles/index.json`: list of tileset IDs (also the
  k8s readiness probe)
- `https://maps.vanillax.me/tiles/osm/tiles.json`: TileJSON for the planet
  source (id = filename stem `osm`)
- `https://maps.vanillax.me/tiles/osm/{z}/{x}/{y}`: vector tiles (pbf)
- `https://maps.vanillax.me/assets/glyphs/index.json`, `…/assets/sprites/index.json`:
  fonts and sprites (verified live)
- `https://maps.vanillax.me/assets/lib/versatiles-style/versatiles-style.js`:
  the style **library**. The v4.6 frontend has NO static `style.json` URLs of
  its own. Its styles (`colorful`, `eclipse`, `graybeard`, `neutrino`,
  `shadow`) are built **client-side** by `VersaTilesStyle`.
- `https://maps.vanillax.me/styles/light.json` and `…/styles/dark.json`:
  **pre-generated static MapLibre styles** we host for external clients that
  only take a style *URL* (e.g. RadarNG's native app). Light = `colorful`,
  dark = `colorful-dark`, generated by `styles/generate.mjs` and served by the
  `map-styles` nginx (see below). CORS `*` (public map styles).

## CORS

Enabled app-side in `config.yaml` (regex allowlist): any
`https://*.vanillax.me` origin plus localhost dev servers. Everything else is
blocked by default. Extend `allow_patterns` to grant new origins.

## Attribution

Map data © OpenStreetMap contributors, [ODbL](https://opendatacommons.org/licenses/odbl/).
The attribution string is embedded in the archive's TileJSON and rendered by
the upstream frontend/MapLibre attribution control. Keep it visible in any
future custom frontend.

## The map-styles static server

VersaTiles v4.6 builds its styles client-side and serves no static
`style.json`. External clients that only accept a style **URL** (RadarNG's
native MapLibre app) need a concrete document. A tiny nginx (`style-server.yaml`,
`map-styles` Service, ~16Mi) serves two pre-generated styles at `/styles/`:

| URL | Theme (`@versatiles/style`) |
|-----|------|
| `https://maps.vanillax.me/styles/light.json` | `colorful` |
| `https://maps.vanillax.me/styles/dark.json` | `colorful-dark` |
| `https://maps.vanillax.me/styles/satellite.json` | raster, USGS orthoimagery via [`../imagery`](../imagery/README.md) (hand-written, not generated) |

`styles/generate.mjs` generates them (pinned `@versatiles/style@6.0.1`, the
version the running VersaTiles frontend bundles). Keep them in step or sprite
names drift. They are committed to git and served with CORS `*`. Every URL
inside them (tiles, glyphs, sprite) points back at this same VersaTiles host
and is verified `200`. The nginx is kept **separate** from the versatiles
Deployment on purpose. That pod runs `readOnlyRootFilesystem` off a read-only
PVC, so adding static files would mean touching the live map server's args.
To regenerate (e.g. new theme or hostname), edit and run `styles/generate.mjs`,
then commit. The configMapGenerator hash changes and rolls `map-styles`.

## RadarNG integration (contract only, RadarNG stays batteries-included)

RadarNG remains bundled-basemap-by-default for every fork and upstream user.
The clean integration contract is a MapLibre **style URL**, and RadarNG's own
frontend now supports opting into one at build time (see
[`mitchross/radar-ng` PR #30](https://github.com/mitchross/radar-ng/pull/30):
`EXPO_PUBLIC_BASEMAP_*_STYLE_URL`, empty means bundled). To point *my* RadarNG
build at this server, build it with:

```env
EXPO_PUBLIC_BASEMAP_LIGHT_STYLE_URL=https://maps.vanillax.me/styles/light.json
EXPO_PUBLIC_BASEMAP_DARK_STYLE_URL=https://maps.vanillax.me/styles/dark.json
```

With a style URL, RadarNG does not need to know whether the backend is
VersaTiles, Protomaps, or Martin. The `radar-ng` app **in this repo** (the
cluster tile-server + bundled Protomaps basemap subsystem) is intentionally
untouched here. Retiring it is a separate follow-up once my app build is on
external mode.

Alternatively, browser MapLibre clients can build the style client-side, as
the upstream frontend does. No hosted JSON is needed:

```js
import { osm } from 'https://maps.vanillax.me/assets/lib/versatiles-style/versatiles-style.js';
map.setStyle(osm({ theme: 'colorful', urls: { base: 'https://maps.vanillax.me' } }));  // dark: theme 'colorful-dark'
```

## Known limitations

- No routing yet. Geocoding lives in [`../photon`](../photon/README.md) and satellite imagery in
  [`../imagery`](../imagery/README.md).
- Single replica (RWO PVC, `Recreate`), so there is brief downtime on pod moves and updates.
- Dataset refresh is a manual URL bump + rollout restart (no auto-cron yet).
- No native Prometheus metrics upstream. Coverage is the generic kube-state
  + ArgoCD sync/degraded alerts.
- Tile serving reads randomly from the archive over SMB. It is noticeably
  slower than local NVMe under load. We accept that for cross-rebuild
  durability (see Storage above).
- The dataset caps zoom at 14 (Shortbread planet). Street-level detail
  renders fine because vector tiles overzoom client-side.

## Validation

```bash
kubectl -n versatiles get pods,pvc,job
kubectl -n versatiles logs job/map-bootstrap        # download / checksum / swap log
curl -I https://maps.vanillax.me                    # 200 + html
curl -s https://maps.vanillax.me/tiles/index.json   # ["osm"]
curl -sI https://maps.vanillax.me/styles/light.json # 200 + application/json + ACAO *
curl -s https://maps.vanillax.me/styles/dark.json | head -c 60   # {"version":8,"name":"versatiles-colorful-dark"...
```

## Later: local speed tier (not implemented)

Serving currently reads straight from the NAS share. If tile latency ever
matters, add a local NVMe **cache/copy** in front (e.g. a longhorn PVC an
init step rsyncs from the NAS copy). The NAS stays the durable source of
truth that survives cluster rebuilds. Local storage would be pure cache.
Historical `osm.YYYYMMDD` snapshots can also accumulate on the same share as
cheap archive.
