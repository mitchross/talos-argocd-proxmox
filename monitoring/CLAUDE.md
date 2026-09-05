# Monitoring Guidelines

## Observability Architecture

```
OTEL Collector Agent (DaemonSet)  →  OTEL Collector Gateway (Deployment)  →  Loki (logs)
  per node: filelog only               k8sattributes, batch
External radar-ng mobile SDK      →                                      →  Tempo (traces)
```

External clients (e.g. the radar-ng mobile app) hit the Gateway over HTTPS at
`otel.vanillax.me/v1/{traces,logs}` via `collector-gateway-httproute.yaml`.

- **OTEL Operator** (`infrastructure/controllers/opentelemetry-operator/`) — manages Collectors
- **Prometheus + Grafana** (`monitoring/prometheus-stack/`) — metrics storage, dashboards, alerting
- **Loki** (`monitoring/loki-stack/`) — log storage (S3 backend on RustFS)
- **Tempo** (`monitoring/tempo/`) — trace storage (S3 backend on RustFS)
- **HolmesGPT** (`monitoring/holmesgpt/`) — AI cluster diagnostics via llama.cpp (`qwen3.8-27b`)
- **Trivy Operator** (`monitoring/trivy-operator/`) — conservative vulnerability + exposed-secret scanning
- **pod-cleanup** (`monitoring/pod-cleanup/`) — 6-hourly CronJob deleting Failed/Succeeded pods cluster-wide

## Telemetry boundary

Do not add blanket auto-instrumentation or OTEL Kubernetes metrics. Prometheus
already owns cluster/application metrics, while the OTEL agents own container
logs. Add application tracing only for a named consumer and an explicit query
or dashboard; send it to the gateway, not the per-node log agents.

## Common Pitfalls

- **VPA ceilings are per container**: keep each monitoring app's `vpa.yaml`
  co-located and name main containers explicitly when a pod has sidecars.
- **VPA update-mode metric**: kube-state-metrics' custom StateSet must include
  `InPlaceOrRecreate`; otherwise active policies disappear from dashboards.

- **Tempo/Loki S3 creds**: Use `extraEnvFrom` with secretRef, NOT inline `${VAR}` in config (they don't expand env vars)
- **ArgoCD metrics**: Must be per-component (`controller.metrics`, `server.metrics`, etc.), top-level `metrics:` key does nothing
- **Longhorn ServiceMonitor**: Select `app: longhorn-manager` (NOT `app.kubernetes.io/name: longhorn-manager`)
- **ArgoCD ignoreDifferences**: Use `jqPathExpressions` NOT `jsonPointers` for wildcards (RFC 6901 doesn't support `*`)
- **PVC storage drift**: Do not globally ignore `.spec.resources.requests.storage`.
  With `RespectIgnoreDifferences=true`, that also suppresses legitimate Git-driven
  expansions. Keep Git at or above the live requested size; use a narrowly scoped
  per-Application ignore only for a known legacy PVC that cannot be reconciled.
- **Loki tenant_id**: Multi-tenant mode requires `X-Scope-OrgID` header or `tenant_id` config — 401 without it
- **Collector recursion**: never collect `opentelemetry` or `loki-stack` pod logs; backend failures otherwise feed their own retry logs back into the failed backend
- **OTEL Collector CRDs**: Use `v1beta1` API version for `OpenTelemetryCollector`, `v1alpha1` for `Instrumentation`

## Key Files

- Custom ServiceMonitors: `monitoring/prometheus-stack/custom-servicemonitors.yaml`
- Custom alerts: `monitoring/prometheus-stack/custom-alerts.yaml`
- GPU alerts: `monitoring/prometheus-stack/gpu-alerts.yaml`
- OTEL Collector Agent: `infrastructure/controllers/opentelemetry-operator/collector-agent.yaml`
- OTEL Collector Gateway: `infrastructure/controllers/opentelemetry-operator/collector-gateway.yaml`
- OTEL Gateway public HTTPRoute: `infrastructure/controllers/opentelemetry-operator/collector-gateway-httproute.yaml`
