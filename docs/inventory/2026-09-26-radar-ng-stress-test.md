# radar-ng stress test — September 26, 2026

A stair-step load test of the radar-ng tile-server (Caddy for tiles, one uvicorn process for `/api/*`, one pod on the GPU worker) to find what breaks first. The test harness and the raw per-pod results are in [radar-ng#70](https://github.com/mitchross/radar-ng/pull/70) (`load/k6-radar.js`, `PROFILE=stress`).

## Method

- **Load:** 60 in-cluster k6 pods, each one client IP. Each ramps 5 → 10 → 15 → 20 users in 3-minute steps: 300, 600, 900 and 1,200 users in total. No pod exceeds the API's per-IP rate limit (20 rps, burst 60); zero 429s were recorded.
- **Traffic mix:** app sessions (manifest, forecast, alerts, nowcast point, geocode, 2 FPS radar playback of a 3×3 z6 viewport) and widget refreshes, across 15 US cities.
- **Placement:** load pods are kept off the tile-server's node by pod anti-affinity. Their nodes (hp-elite, hp-sff) peaked at 62% CPU, so the client side was not the limit.
- **Window:** 21:01–21:14 UTC, tile-server v1.1.20, CPU limit 2.

## Results

| Step (users) | Time (UTC) | Tile req/s | API req/s | API p95 (Caddy) | Tile-server CPU | Throttled periods |
|---:|---|---:|---:|---:|---:|---:|
| 300 | 21:01–21:04 | 1,800–2,470 | 150–197 | 0.3 s | 1.94 cores | 49% |
| 600 | 21:04–21:07 | 2,220–2,430 | 180–196 | 3 s | 1.89 | 37% |
| 900 | 21:07–21:10 | 2,120–2,250 | 171–182 | 7 s | 1.83 | 29% |
| 1,200 | 21:10–21:13 | 1,700–2,190 | 138–178 | 10–12 s | 1.82 | 38% |

The whole test served 1.81 M requests (2,318 req/s average). Tile p95 was 30 ms (median pod) and playback frames 68 ms p95, but the API was far outside its targets: manifest and nowcast point p95 about 10 s.

**The tile-server was restarted twice under load** (about 21:11 and 21:12:29, exit 137, "failed liveness probe"). With one replica, both restarts, plus the readiness failures just before them, emptied the Service, so every request got `connection refused`. That caused most of the 17,011 failed requests; only 26 were 5xx.

## What broke, in order

1. **The Python API tops out around 190 req/s.** It's a single uvicorn process, so about one core regardless of the pod limit, and it saturates between 300 and 600 users. Its time goes to avoidable work, fixed in radar-ng:
   - `/api/nowcast/{lat}/{lon}` parses the whole 130 KB manifest from disk on every request.
   - `/api/manifest.json` re-serializes the cached manifest on every request.
   - uvicorn writes an access-log line per request, duplicating Caddy's JSON access log.
2. **The liveness and readiness probes turned API saturation into a total outage.** Both probed `/api/livez` with the default 1 s timeout. `/api/livez` waits in the same queue as real API requests, so under load it missed the timeout: readiness dropped the only endpoint, and liveness then killed the container, Caddy included, even though Caddy was serving tiles fine.
3. **The container sat at its 2-CPU limit from the first step onward** (Caddy about 1 core, uvicorn about 1 core) while the GPU worker was about 35% busy.

Tiles (Caddy file_server on the Longhorn `longhorn-flash` volume) never became the bottleneck. Their throughput stayed flat only because each simulated user's session waited on slow API calls.

## Changes

This PR:

- **Liveness:** `timeoutSeconds: 5`, `failureThreshold: 4`. The container restarts only after about 60 s of a dead or wedged API, not a busy one.
- **Readiness:** `tcpSocket` on 8080. The pod stays in the Service while Caddy accepts connections, so tiles keep flowing when the API is slow.
- **CPU limit:** 2 → 3. The request stays at 250m because it's the HPA denominator, and HPA maxReplicas stays 1 because of the RWO tile volume.

radar-ng (follow-up image bump here):

- Share the TTL-cached manifest with the nowcast point route.
- Cache the serialized manifest.
- Drop the duplicate uvicorn access log.

The stress test is rerun after both land to measure the new API ceiling.

## Not changed, and why

- **More uvicorn workers:** per-process state (the rate limiter's buckets, caches, the `/api/metrics` counters) would split per worker, so it needs its own change.
- **Rust:** serving is dominated by avoidable per-request work in Python, not by Python's speed. Fix that first, and revisit only if the API still caps below the target after the rerun.
