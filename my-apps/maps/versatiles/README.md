# VersaTiles — self-hosted worldwide map at maps.vanillax.me

## What and why

[VersaTiles](https://versatiles.org) is an open-source map stack: a Rust tile
server plus a MapLibre browser frontend, serving pre-rendered OpenStreetMap
vector tiles from a single archive file. No database, no API key, no paid
service, no external tile provider.

Deployed here as **shared map infrastructure** for the cluster (future
consumers: RadarNG, Project NOMAD, Home Assistant, anything location-aware).
This is the first phase: upstream VersaTiles as-is — no custom frontend, no
search, no routing.

- **Public URL:** <https://maps.vanillax.me> (pan/zoom world map, keyless)
- **Dataset:** `osm.20260608.versatiles` — full planet, zoom 0–14, Shortbread
  schema, **62.0 GiB**, from <https://download.versatiles.org/> (free, no
  account, sha256-verified)
- **Storage:** 150Gi PVC `map-data` on the default `longhorn` (NVMe) class —
  62 GiB active + headroom for the atomic download-then-swap during refresh.
  Backup-exempt (re-downloadable public data).
- **Image:** `versatiles/versatiles-frontend:v4.6.0` (server + bundled
  upstream frontend; Renovate manages bumps)

## How it works

```
download.versatiles.org (osm.YYYYMMDD.versatiles + .sha256)
        │  map-bootstrap Job (ArgoCD Sync hook): download → verify → atomic mv
        ▼
map-data PVC (150Gi longhorn)
        │  read-only mount; init container blocks until archive exists
        ▼
versatiles Deployment (serve -c config.yaml /data/osm.versatiles)
        ▼
Service :8080 → HTTPRoute (gateway-external) → https://maps.vanillax.me
```

**Bootstrap:** on first sync the `map-bootstrap` hook Job downloads the
archive (~15–60 min depending on WAN speed; the ArgoCD app shows Progressing
the whole time — this is expected), verifies the published sha256, and
atomically renames it into place. The server pod's `wait-for-map` init
container blocks until the file exists, so Job and Deployment can deploy
together in any order. On every later sync the Job re-runs but exits in
seconds via a marker file on the PVC (`/data/.bootstrap-marker`, line 1 = the
dataset URL it downloaded).

**Updates (refresh the planet / change dataset):** edit `DATASET_URL` +
`DATASET_SHA256_URL` in `kustomization.yaml`'s `configMapGenerator` to a newer
`osm.YYYYMMDD.versatiles` from <https://download.versatiles.org/>, commit,
push. The hash-suffixed ConfigMap name changes → Job spec changes → hook
re-runs → marker mismatch → fresh download → atomic swap. The running server
keeps serving the **old** file through its open file descriptor until
restarted, so serving never breaks mid-swap. After the Job completes:

```bash
kubectl -n versatiles rollout restart deploy/versatiles
```

**Manual re-download (same URL):** delete the marker, then re-run the hook:

```bash
kubectl -n versatiles exec deploy/versatiles -- rm /data/.bootstrap-marker  # (or via the Job pod)
kubectl -n versatiles delete job map-bootstrap   # next sync recreates + re-downloads
```

(Note: the server mounts `/data` read-only; if exec-deleting the marker fails,
run a one-off pod mounting the PVC read-write.)

**Rollback:** point `DATASET_URL` back at the previous `osm.YYYYMMDD`
snapshot (older versioned files stay downloadable for months), commit, wait
for the hook, restart the Deployment. If a download fails mid-way nothing
breaks: the partial file is a `.tmp`, the active archive and marker are
untouched, and the Job retries (`backoffLimit: 4`, then ArgoCD app shows
Degraded — that's the failure alert path, via the existing ArgoCD sync
alerts).

## Endpoints

- `https://maps.vanillax.me/` — upstream frontend (map viewer)
- `https://maps.vanillax.me/tiles/index.json` — list of tileset IDs (also the
  k8s readiness probe)
- `https://maps.vanillax.me/tiles/osm/tiles.json` — TileJSON for the planet
  source (id = filename stem `osm`)
- `https://maps.vanillax.me/tiles/osm/{z}/{x}/{y}` — vector tiles (pbf)
- `https://maps.vanillax.me/assets/styles/<style_id>/style.json` — MapLibre
  styles; `https://maps.vanillax.me/assets/glyphs/…`, `…/assets/sprites/…`
  — fonts and sprites

> **TODO (fill in after first live deploy):** the exact shipped `style_id`
> list (expected: the VersaTiles `colorful` / `graybeard` / `eclipse` /
> `neutrino` family) — verify with
> `curl -s https://maps.vanillax.me/assets/styles/index.json` (or browse
> `/assets/`) and replace this note with the real URLs.

## CORS

Enabled app-side in `config.yaml` (regex allowlist): any
`https://*.vanillax.me` origin plus localhost dev servers. Everything else is
blocked by default. Extend `allow_patterns` to grant new origins.

## Attribution

Map data © OpenStreetMap contributors, [ODbL](https://opendatacommons.org/licenses/odbl/).
The attribution string is embedded in the archive's TileJSON and rendered by
the upstream frontend/MapLibre attribution control. Keep it visible in any
future custom frontend.

## Future RadarNG integration (documentation only — NOT wired up)

RadarNG stays batteries-included upstream (bundled basemap default). The
clean integration contract for *this* deployment is a MapLibre **style URL**,
which encapsulates tile sources, glyphs, sprites, layers, and attribution:

```env
RADAR_BASEMAP_LIGHT_STYLE_URL=https://maps.vanillax.me/assets/styles/<light-style-id>/style.json
RADAR_BASEMAP_DARK_STYLE_URL=https://maps.vanillax.me/assets/styles/<dark-style-id>/style.json
```

(Real style IDs go in once verified live — see TODO above.) That keeps RadarNG
ignorant of whether the backend is VersaTiles, Protomaps, or Martin. The
radar-ng app in this repo is intentionally untouched by this deployment.

## Known limitations

- No geocoding/search, no routing, no satellite imagery (future phases:
  Photon / Valhalla / etc. — deliberately not deployed yet).
- Single replica (RWO PVC, `Recreate`); brief downtime on pod moves/updates.
- Dataset refresh is a manual URL bump + rollout restart (no auto-cron yet).
- No native Prometheus metrics upstream; coverage is the generic kube-state
  + ArgoCD sync/degraded alerts.
- Zoom is capped at 14 by the dataset (Shortbread planet); street-level
  detail renders fine because vector tiles overzoom client-side.

## Validation

```bash
kubectl -n versatiles get pods,pvc,job
kubectl -n versatiles logs job/map-bootstrap        # download / checksum / swap log
curl -I https://maps.vanillax.me                    # 200 + html
curl -s https://maps.vanillax.me/tiles/index.json   # ["osm"]
```

## Later: NAS/RustFS archival (not implemented)

If historical snapshots become worth keeping, stage `osm.YYYYMMDD.versatiles`
files on TrueNAS (SMB/NFS share or RustFS bucket) as archive-only storage and
keep serving from the local PVC — do not put network storage in the tile
serving path (random byte-range reads; see
`docs/domains/storage/storage-tiers.md`).
