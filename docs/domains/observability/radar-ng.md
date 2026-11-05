# radar-ng observability cookbook

App-specific guide to the radar-ng observability stack. It shows how to find out what
radar-ng is doing right now. Platform-level docs (collector layout, retention,
storage backends) live in
[`monitoring/README.md`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/monitoring/README.md).

## Signal sources

| component | sink | how it gets there |
|---|---|---|
| `radar-ng-mobile` (Expo app) | Tempo + Loki | OTel SDK in `src/lib/telemetry.ts` sends OTLP/HTTP to `otel.vanillax.me` (gateway) |
| `tile-server` API logs | Loki | stdout JSON goes to otel-agent (DaemonSet), then the gateway, then Loki |
| `tile-server` `/api/metrics` | Prometheus | ServiceMonitor at `my-apps/personal-projects/radar-ng/servicemonitor.yaml` |
| `ingest-mrms` / `ingest-hrrr` / `ingest-lightning` / `ingest-tropical` / `nowcast` / `basemap` / `open-meteo` logs | Loki | same pipeline as tile-server |
| Pod CPU / memory / OOM | Prometheus | kube-state-metrics + cadvisor |

Loki uses OTel-semconv labels: `k8s_namespace_name`, `k8s_pod_name`,
`k8s_container_name` and `service_name`. Promtail-style `namespace` and
`pod` labels do **not** exist. Selectors that use them return "No data".

## Grafana: the radar-ng dashboard

Grafana imports this dashboard automatically from [`monitoring/metrics/prometheus-stack/dashboards/apps/radar-ng.json`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/monitoring/metrics/prometheus-stack/dashboards/apps/radar-ng.json).
The dashboard has the label `grafana_dashboard: "1"`, which the sidecar picks up. In
Grafana, open Dashboards and search for "radar-ng".

| panel | tells you |
|---|---|
| **MRMS radar data age (s)** | live `radar_ng_mrms_age_seconds`. Green < 300, red > 600 |
| **tile-server requests/sec by endpoint** | rate(`radar_ng_*_requests_total`) ; shows the manifest versus forecast traffic split |
| **Forecast cache hit %** | `radar_ng_forecast_cache_hits_total / radar_ng_forecast_requests_total` |
| **Log volume by container** | Loki `count_over_time({k8s_namespace_name="radar-ng"})` |
| **Recent error lines** | Loki tail filtered by error/warn |
| **Tile timestamps per layer** | gauge per layer. Should always be 3 frames behind in steady state |
| **Pod CPU vs request** | which pods are CPU-bound vs idle |
| **Pod memory vs limit** | early-warning before OOM |
| **tile-server replicas** | 1 ready replica. A gap means a restart or an unscheduled pod |
| **OOM kills (1h)** | should be 0 |
| **Container restarts (1h)** | should be 0 |

## Loki query cookbook

Paste these into Grafana, under Explore, with Loki as the data source.

### Catch-all: anything bad happening in radar-ng

```logql
{k8s_namespace_name="radar-ng"} |~ "(?i)error|warn|exception|traceback"
```

### Render-cycle timing for ingest-mrms

```logql
{k8s_namespace_name="radar-ng", k8s_pod_name=~"ingest-mrms.*"}
  | json
  | msg = "frame_done"
  | line_format "{{.timestamp}} took {{.duration_s}}s"
```

Steady state is ~120 s per frame with parallel palettes. If a frame takes > 200 s, look at
CPU saturation.

### Tile-server slow requests

```logql
{k8s_namespace_name="radar-ng", k8s_pod_name=~"tile-server.*"}
  | json
  | duration > 1.0
  | line_format "{{.duration}}s {{.request_uri}}"
```

### Backlog growing on ingest-mrms

```logql
{k8s_namespace_name="radar-ng", k8s_pod_name=~"ingest-mrms.*"}
  | json | msg = "processing_batch"
  | line_format "backlog={{.backlog}} rendering={{.rendering}}"
```

If `backlog` keeps climbing across cycles, the ingester is falling behind.

### Lightning ingester reconnects

```logql
{k8s_namespace_name="radar-ng", k8s_pod_name=~"ingest-lightning.*"}
  |~ "ws_disconnect|reconnect"
```

Blitzortung WS drops several times per hour. That is normal. Sustained
reconnects (one per minute or worse) mean an upstream issue, not a problem on your side.

### Mobile app red-screen crashes

```logql
{service_name="radar-ng-mobile"} |= "ERROR"
```

The app's `telemetry.ts` hooks into `ErrorUtils.setGlobalHandler`. Every
fatal red-screen and unhandled promise rejection arrives here with a stack trace.

### Find logs for a specific trace

In Tempo, copy the trace_id, then:

```logql
{k8s_namespace_name="radar-ng"} |= "<trace_id>"
```

Backend logs include the trace_id in the JSON envelope when an instrumented client call
triggered the request.

### Tile-server connection failures (e.g. basemap pod restarting)

```logql
{k8s_namespace_name="radar-ng", k8s_pod_name=~"tile-server.*"}
  |~ "dial tcp .* connect: (refused|timed out|operation not permitted)"
```

Spikes during pod rollouts are expected and resolve themselves. For sustained errors,
check basemap pod health (`kubectl get pods -n radar-ng -l app=basemap`).

## Tempo (traces): what spans the mobile app emits

`src/lib/telemetry.ts` exposes a `trace()` helper:

```ts
await trace("manifest.fetch", async (span) => {
  span.setAttribute("server", serverUrl);
  return await fetchSelfHostedManifest(serverUrl);
});
```

Currently instrumented spans:

| span name | where | attributes |
|---|---|---|
| `map.fetchStyle` | `WeatherMap.tsx::usePatchedMapStyle` | `map.style`, `http.status_code` |

Service name: `radar-ng-mobile`. In Grafana, open Explore, pick Tempo, and search by
service. Click any span, then "Logs for this span", to pull correlated Loki lines.

To correlate with the backend, make the backend hook propagate the
`traceparent` header from the OTLP request to its own logger. FastAPI
in `tile-server` doesn't propagate it automatically. Instrumentation is a TODO.

## Prometheus: radar-ng metric reference

`tile-server.radar-ng.svc/api/metrics` exposes them. The ServiceMonitor at
`my-apps/personal-projects/radar-ng/servicemonitor.yaml` picks them up.

| metric | type | what it is |
|---|---|---|
| `radar_ng_forecast_requests_total` | counter | every `/api/forecast/{lat}/{lon}` hit |
| `radar_ng_forecast_cache_hits_total` | counter | the subset served from in-memory 5-min cache |
| `radar_ng_forecast_upstream_errors_total` | counter | Open-Meteo upstream 5xx |
| `radar_ng_manifest_requests_total` | counter | every `/api/manifest.json` hit (mostly mobile clients) |
| `radar_ng_tile_timestamps{layer="…"}` | gauge | how many frames are currently retained per layer |
| `radar_ng_mrms_age_seconds` | gauge | seconds since the latest MRMS frame was rendered |

### Useful PromQL

```promql
# Manifest QPS over the last 5 min
rate(radar_ng_manifest_requests_total[5m])

# Forecast cache hit ratio (one number)
sum(rate(radar_ng_forecast_cache_hits_total[5m]))
  / clamp_min(sum(rate(radar_ng_forecast_requests_total[5m])), 1)

# Are tiles current? alert if MRMS age > 10 min for 5 min
radar_ng_mrms_age_seconds > 600

# Per-layer tile retention — should hover near a fixed number
radar_ng_tile_timestamps
```

## Alert candidates (not yet wired)

Add these PrometheusRule entries when you want pager-grade alerts:

```yaml
- alert: RadarNgMrmsStale
  expr: radar_ng_mrms_age_seconds > 900
  for: 5m
  annotations:
    summary: "radar-ng: MRMS frame > 15 min old"

- alert: RadarNgIngestMrmsRestarting
  expr: increase(kube_pod_container_status_restarts_total{namespace="radar-ng",pod=~"ingest-mrms.*"}[15m]) > 2
  for: 5m
  annotations:
    summary: "radar-ng: ingest-mrms restarting"

- alert: RadarNgForecastUpstreamErrors
  expr: rate(radar_ng_forecast_upstream_errors_total[5m]) > 0.1
  for: 10m
  annotations:
    summary: "radar-ng: Open-Meteo upstream errors"
```

Drop these into `monitoring/metrics/prometheus-stack/` as a `PrometheusRule`.

## Troubleshooting flow

```text
user reports: app slow / radar stale
        │
        ▼
check Grafana radar-ng dashboard
        │
        ├─ MRMS age red ─────────────▶ ingest-mrms not keeping up
        │                                     │
        │                              Loki: ingest-mrms backlog query
        │                                     ├─ backlog growing ─▶ bump ingest-mrms CPU/RAM
        │                                     │                     or check NOAA S3 latency
        │                                     └─ backlog flat ────▶ OOM kill or crash
        │                                                           (kubectl describe pod)
        │
        ├─ tile-server req/sec spike ─▶ traffic surge (single replica; check CPU vs request, VPA adjusts it)
        │
        └─ all panels green ─────────▶ client-side issue (check Tempo for radar-ng-mobile)
                                              ├─ Tempo: span errors for radar-ng-mobile
                                              └─ Loki: service_name=radar-ng-mobile errors
```

## Related links

- [`monitoring/README.md`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/monitoring/README.md): platform observability layout
- [`monitoring/CLAUDE.md`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/monitoring/CLAUDE.md): design rationale and pitfalls
- [`monitoring/metrics/prometheus-stack/dashboards/apps/radar-ng.json`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/monitoring/metrics/prometheus-stack/dashboards/apps/radar-ng.json): the dashboard JSON
- [`my-apps/personal-projects/radar-ng/servicemonitor.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/personal-projects/radar-ng/servicemonitor.yaml): Prometheus scrape config
- radar-ng repo: `src/lib/telemetry.ts`, mobile OTel wiring
- radar-ng repo: `services/shared/logger.py`, backend JSON logger
