# radar-ng observability cookbook

This page shows how to find out what radar-ng, the weather radar app, is doing
at this moment. It gives the dashboard, the log queries, the metrics and the
alerts for that one app. Use it when a user reports a slow app or stale radar.

The platform docs (collector layout, retention, storage backends) are in
[`monitoring/README.md`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/monitoring/README.md).

The stack has three stores. Loki stores logs, Tempo stores traces, and
Prometheus stores metrics. Grafana reads all three.

## Signal sources

| Component | Store | How the signal gets there |
|---|---|---|
| `radar-ng-mobile` (Expo app) | Tempo + Loki | OTel SDK in `src/lib/telemetry.ts` sends OTLP/HTTP to `otel.vanillax.me` (gateway) |
| `tile-server` API logs | Loki | stdout JSON goes to otel-agent (DaemonSet), then the gateway, then Loki |
| `tile-server` `/api/metrics` | Prometheus | ServiceMonitor at `my-apps/personal-projects/radar-ng/servicemonitor.yaml` |
| `radar-ng-worker-*` (`mrms`, `hrrr`, `nowcast`, `aux`, `alerts`), `basemap`, and `open-meteo` logs | Loki | same pipeline as tile-server |
| Pod CPU / memory / OOM | Prometheus | kube-state-metrics + cadvisor |

The ingest and nowcast code runs in five Temporal worker pools named
`radar-ng-worker-*` (`mrms`, `nowcast`, `hrrr`, `aux`, `alerts`). The `aux`
pool runs lightning, tropical, and air quality. If a query returns no data,
run `kubectl -n radar-ng get pods` and check the `k8s_pod_name` selector.

Loki uses OTel-semconv labels: `k8s_namespace_name`, `k8s_pod_name`,
`k8s_container_name` and `service_name`. Promtail-style `namespace` and
`pod` labels do not exist. A selector that uses them returns "No data".

## Grafana: the radar-ng dashboard

Grafana imports this dashboard from [`monitoring/metrics/prometheus-stack/dashboards/apps/radar-ng.json`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/monitoring/metrics/prometheus-stack/dashboards/apps/radar-ng.json).
The dashboard has the label `grafana_dashboard: "1"`, and the Grafana sidecar
loads every dashboard with that label. In Grafana, open Dashboards and search
for "radar-ng".

| Panel | What it tells you |
|---|---|
| MRMS radar data age (s) | live `radar_ng_mrms_age_seconds`. Green < 300, red > 600 |
| tile-server requests/sec by endpoint | rate(`radar_ng_*_requests_total`). Shows the split between manifest and forecast traffic |
| Forecast cache hit % | `radar_ng_forecast_cache_hits_total / radar_ng_forecast_requests_total` |
| Log volume by container | Loki `count_over_time({k8s_namespace_name="radar-ng"})` |
| Recent error lines | Loki tail filtered by error/warn |
| Tile timestamps per layer | gauge per layer. Expect 3 frames behind in steady state |
| Pod CPU vs request | which pods are CPU-bound and which are idle |
| Pod memory vs limit | early warning before an OOM kill |
| tile-server replicas | 1 ready replica. A gap means a restart or an unscheduled pod |
| OOM kills (1h) | expect 0 |
| Container restarts (1h) | expect 0 |

The dashboard also has rows for client traffic, the Open-Meteo forecast sync,
and the API and geocoding routes.

## Loki query cookbook

Paste these into Grafana, under Explore, with Loki as the data source.

### Catch-all: anything bad happening in radar-ng

```logql
{k8s_namespace_name="radar-ng"} |~ "(?i)error|warn|exception|traceback"
```

### Render-cycle timing for the MRMS worker

```logql
{k8s_namespace_name="radar-ng", k8s_pod_name=~"radar-ng-worker-mrms.*"}
  | json
  | msg = "frame_done"
  | line_format "{{.timestamp}} took {{.duration_s}}s"
```

Steady state is ~120 s per frame with parallel palettes. If a frame takes
more than 200 s, check CPU saturation.

### Tile-server slow requests

```logql
{k8s_namespace_name="radar-ng", k8s_pod_name=~"tile-server.*"}
  | json
  | duration > 1.0
  | line_format "{{.duration}}s {{.request_uri}}"
```

### Lightning ingester reconnects

```logql
{k8s_namespace_name="radar-ng", k8s_pod_name=~"radar-ng-worker-aux.*"}
  |~ "ws_disconnect|reconnect"
```

The Blitzortung WebSocket drops several times per hour. That is normal. One
reconnect per minute or more means an upstream problem, not a problem in this
cluster.

### Mobile app red-screen crashes

```logql
{service_name="radar-ng-mobile"} |= "ERROR"
```

The app's `telemetry.ts` registers a handler with `ErrorUtils.setGlobalHandler`.
Every fatal red-screen and unhandled promise rejection arrives in Loki with a
stack trace.

### Find logs for a specific trace

In Tempo, copy the trace_id. Then run:

```logql
{k8s_namespace_name="radar-ng"} |= "<trace_id>"
```

A backend log line includes the trace_id in its JSON envelope when an
instrumented client call started the request.

### Tile-server connection failures

```logql
{k8s_namespace_name="radar-ng", k8s_pod_name=~"tile-server.*"}
  |~ "dial tcp .* connect: (refused|timed out|operation not permitted)"
```

Expect a short spike during a pod rollout, for example when the basemap pod
restarts. The spike stops without action. For errors that continue, check the
basemap pod (`kubectl get pods -n radar-ng -l app=basemap`).

## Tempo (traces): what spans the mobile app emits

`src/lib/telemetry.ts` exposes a `trace()` helper:

```ts
await trace("manifest.fetch", async (span) => {
  span.setAttribute("server", serverUrl);
  return await fetchSelfHostedManifest(serverUrl);
});
```

The app emits one instrumented span:

| Span name | Where | Attributes |
|---|---|---|
| `map.fetchStyle` | `WeatherMap.tsx::usePatchedMapStyle` | `map.style`, `http.status_code` |

The service name is `radar-ng-mobile`. In Grafana, open Explore, select Tempo,
and search by service. Click a span, then "Logs for this span", to see the
matching Loki lines.

Backend spans do not exist yet. FastAPI in `tile-server` does not pass the
`traceparent` header to its logger. To correlate a client trace with backend
logs, add that propagation to the backend.

## Prometheus: radar-ng metric reference

`tile-server.radar-ng.svc/api/metrics` exposes these metrics. The
ServiceMonitor at `my-apps/personal-projects/radar-ng/servicemonitor.yaml`
tells Prometheus to scrape them.

| Metric | Type | What it is |
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

# Per-layer tile retention: should hover near a fixed number
radar_ng_tile_timestamps
```

## Alerts

The alert rules are in
[`my-apps/personal-projects/radar-ng/prometheusrule.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/personal-projects/radar-ng/prometheusrule.yaml).
That file is the source of truth. These rules cover radar freshness and the API:

| Alert | Fires when |
|---|---|
| `RadarNgObservedRadarStale` | `radar_ng_mrms_age_seconds > 600` for 5 minutes |
| `RadarNgFreshnessMetricMissing` | `radar_ng_mrms_age_seconds` is absent for 10 minutes |
| `RadarNgApiHighErrorRate` | the API 5xx ratio stays above 5 percent for 10 minutes |

The file also has rules for the Open-Meteo sync, the geocoder, worker memory
and restarts, missing tile layers, Temporal pollers and schedules, and volume
space.

### A candidate that is not in the rule file

This rule is not deployed. Add it to `prometheusrule.yaml` if you need it.
Worker restarts already have a deployed rule, `RadarNgWorkerRestarting`.

```yaml
- alert: RadarNgForecastUpstreamErrors
  expr: rate(radar_ng_forecast_upstream_errors_total[5m]) > 0.1
  for: 10m
  annotations:
    summary: "radar-ng: Open-Meteo upstream errors"
```

## Troubleshooting flow

```text
user reports: app slow / radar stale
        │
        ▼
check Grafana radar-ng dashboard
        │
        ├─ MRMS age red ─────────────▶ radar-ng-worker-mrms not keeping up
        │                                     │
        │                              Loki: render-cycle timing query
        │                                     ├─ frames over 200 s ─▶ bump the worker CPU/RAM
        │                                     │                       or check NOAA S3 latency
        │                                     └─ no frame_done ─────▶ OOM kill or crash
        │                                                             (kubectl describe pod)
        │
        ├─ tile-server req/sec spike ─▶ traffic surge (single replica; check CPU vs request, VPA adjusts it)
        │
        └─ all panels green ─────────▶ client-side issue (check Tempo for radar-ng-mobile)
                                              ├─ Tempo: span errors for radar-ng-mobile
                                              └─ Loki: service_name=radar-ng-mobile errors
```

Read the flow from the top. Start at the Grafana dashboard, then follow the
branch that matches the red panel.

## Related links

- [`monitoring/README.md`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/monitoring/README.md): platform observability layout
- [`monitoring/CLAUDE.md`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/monitoring/CLAUDE.md): design reasons and known problems
- [`radar-ng/RUNBOOK.md`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/personal-projects/radar-ng/RUNBOOK.md): worker pools, queues and recovery
- [`monitoring/metrics/prometheus-stack/dashboards/apps/radar-ng.json`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/monitoring/metrics/prometheus-stack/dashboards/apps/radar-ng.json): the dashboard JSON
- [`my-apps/personal-projects/radar-ng/servicemonitor.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/personal-projects/radar-ng/servicemonitor.yaml): Prometheus scrape config
- radar-ng repo: `src/lib/telemetry.ts`, mobile OTel wiring
- radar-ng repo: `services/shared/logger.py`, backend JSON logger
