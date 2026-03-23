# Monitoring Guidelines

## Observability Architecture

```
OTEL Collector Agent (DaemonSet)  →  OTEL Collector Gateway (Deployment)  →  Honeycomb (OTLP)
  per node: filelog + OTLP recv        k8sattributes, batch, fan-out    →  Tempo (traces)
                                                                         →  Loki (logs)
                                                                         →  Prometheus (metrics)
```

- **OTEL Operator** (`infrastructure/controllers/opentelemetry-operator/`) — manages Collectors and auto-instrumentation
- **Prometheus + Grafana** (`monitoring/prometheus-stack/`) — metrics storage, dashboards, alerting
- **Loki** (`monitoring/loki-stack/`) — log storage (S3 backend on RustFS)
- **Tempo** (`monitoring/tempo/`) — trace storage (S3 backend on RustFS)
- **Honeycomb** — SaaS observability, receives all signals via OTLP

## Auto-Instrumentation

Apps opt-in by adding an annotation to their Deployment:

```yaml
annotations:
  instrumentation.opentelemetry.io/inject-python: "true"
  # also: inject-nodejs, inject-java, inject-go, inject-dotnet
```

The OTEL Operator webhook injects an init container with the OTEL SDK. Traces are sent to the Agent's OTLP endpoint automatically.

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
- Auto-instrumentation: `infrastructure/controllers/opentelemetry-operator/instrumentation.yaml`
- Honeycomb secret: `infrastructure/controllers/opentelemetry-operator/externalsecret.yaml`
