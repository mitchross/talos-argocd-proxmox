# Monitoring Guidelines

## Observability Architecture

```
OTEL Collector Agent (DaemonSet)  →  OTEL Collector Gateway (Deployment)  →  Tempo (traces)
  per node: filelog + OTLP recv        k8sattributes, batch, fan-out     →  Loki (logs)
                                                                         →  Prometheus (metrics)
```

External clients (e.g. the radar-ng mobile app) hit the Gateway over HTTPS at
`otel.vanillax.me/v1/{traces,logs,metrics}` via `collector-gateway-httproute.yaml`.

- **OTEL Operator** (`infrastructure/controllers/opentelemetry-operator/`) — manages Collectors and auto-instrumentation
- **Prometheus + Grafana** (`monitoring/prometheus-stack/`) — metrics storage, dashboards, alerting
- **Loki** (`monitoring/loki-stack/`) — log storage (S3 backend on RustFS)
- **Tempo** (`monitoring/tempo/`) — trace storage (S3 backend on RustFS)
- **k8sgpt** (`monitoring/k8sgpt/`) — AI cluster diagnostics via vLLM (`qwen3.6-27b`)
- **Trivy Operator** (`monitoring/trivy-operator/`) — conservative vulnerability + exposed-secret scanning
- **pod-cleanup** (`monitoring/pod-cleanup/`) — 6-hourly CronJob deleting Failed/Succeeded pods cluster-wide

## Auto-Instrumentation

Apps opt-in by adding an annotation to their Deployment:

```yaml
annotations:
  instrumentation.opentelemetry.io/inject-nodejs: "opentelemetry/default"
  # also: inject-java, inject-go, inject-dotnet
```

The OTEL Operator webhook injects an init container with the OTEL SDK. Traces are sent to the Agent's OTLP endpoint automatically.

**NEVER use `inject-python`** — it crashed every Python app it touched here
(see README § auto-instrumentation), and `instrumentation.yaml` intentionally
pins no python image. Only annotate apps whose main container actually runs
the matching runtime: the injection adds an init container that gates pod
start on an image pull, so it's pure cost on a non-matching runtime (e.g. a
static SPA served by nginx).

## Common Pitfalls

- **Tempo/Loki S3 creds**: Use `extraEnvFrom` with secretRef, NOT inline `${VAR}` in config (they don't expand env vars)
- **ArgoCD metrics**: Must be per-component (`controller.metrics`, `server.metrics`, etc.), top-level `metrics:` key does nothing
- **Longhorn ServiceMonitor**: Select `app: longhorn-manager` (NOT `app.kubernetes.io/name: longhorn-manager`)
- **ArgoCD ignoreDifferences**: Use `jqPathExpressions` NOT `jsonPointers` for wildcards (RFC 6901 doesn't support `*`)
- **PVC storage in ignoreDifferences**: Must ignore `.spec.resources.requests.storage` — can't shrink existing PVCs
- **Loki tenant_id**: Multi-tenant mode requires `X-Scope-OrgID` header or `tenant_id` config — 401 without it
- **OTEL Collector CRDs**: Use `v1beta1` API version for `OpenTelemetryCollector`, `v1alpha1` for `Instrumentation`

## Key Files

- Custom ServiceMonitors: `monitoring/prometheus-stack/custom-servicemonitors.yaml`
- Custom alerts: `monitoring/prometheus-stack/custom-alerts.yaml`
- GPU alerts: `monitoring/prometheus-stack/gpu-alerts.yaml`
- OTEL Collector Agent: `infrastructure/controllers/opentelemetry-operator/collector-agent.yaml`
- OTEL Collector Gateway: `infrastructure/controllers/opentelemetry-operator/collector-gateway.yaml`
- OTEL Gateway public HTTPRoute: `infrastructure/controllers/opentelemetry-operator/collector-gateway-httproute.yaml`
- Auto-instrumentation: `infrastructure/controllers/opentelemetry-operator/instrumentation.yaml`
