# OpenTelemetry Operator + Honeycomb Design

**Date**: 2026-03-22 (updated 2026-03-23)
**Status**: Implementing

## Goal

Deploy the CNCF OpenTelemetry Operator with Collector (agent + gateway) to replace Grafana Alloy. Dual-ships all telemetry to both local Grafana stack and Honeycomb SaaS. Auto-instrumentation enabled for zero-code trace generation.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  OTEL Operator (Deployment)                                  │
│  - Manages Collector instances via OpenTelemetryCollector CRD│
│  - Injects auto-instrumentation via Instrumentation CRD      │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  OTEL Collector Agent (DaemonSet) — per node                 │
│  - filelog receiver: scrapes /var/log/pods                    │
│  - otlp receiver: accepts traces/metrics from instrumented   │
│    apps on :4317/:4318                                       │
│  - Forwards all signals to Gateway via OTLP gRPC             │
└──────────────────────────┬──────────────────────────────────┘
                           │ OTLP gRPC
┌──────────────────────────▼──────────────────────────────────┐
│  OTEL Collector Gateway (Deployment, 2 replicas)             │
│  - k8sattributes: enriches with k8s metadata from API        │
│  - resource: sets service.name, cluster name                 │
│  - batch: 10s / 8192 items                                   │
│  - Fan-out to all backends:                                  │
│    → Loki via OTLP HTTP (logs)                               │
│    → Tempo via OTLP gRPC (traces)                            │
│    → Prometheus remote-write (metrics)                       │
│    → Honeycomb via OTLP HTTP (everything)                    │
└─────────────────────────────────────────────────────────────┘
```

## Data Flow

| Signal  | Source                          | Local Destination         | Honeycomb  |
|---------|---------------------------------|---------------------------|------------|
| Logs    | Pod stdout/stderr (filelog)     | Loki via OTLP HTTP        | OTLP HTTP  |
| Traces  | Auto-instrumented apps → OTLP  | Tempo via OTLP gRPC       | OTLP HTTP  |
| Metrics | Auto-instrumented apps → OTLP  | Prometheus remote-write   | OTLP HTTP  |

## Components

### New: `infrastructure/controllers/opentelemetry-operator/`

| File                   | Purpose                                              |
|------------------------|------------------------------------------------------|
| `ns.yaml`              | Namespace `opentelemetry`                            |
| `kustomization.yaml`   | Helm chart (opentelemetry-operator 0.105.1)          |
| `values.yaml`          | Operator config, cert-manager webhooks               |
| `externalsecret.yaml`  | Honeycomb API key from 1Password                     |
| `collector-agent.yaml` | OpenTelemetryCollector CRD (DaemonSet mode)          |
| `collector-gateway.yaml`| OpenTelemetryCollector CRD (Deployment mode)        |
| `instrumentation.yaml` | Instrumentation CRD (auto-inject config)             |

### Modified: `infrastructure/controllers/argocd/apps/infrastructure-appset.yaml`

Added `infrastructure/controllers/opentelemetry-operator` to the explicit path list.

### Modified (earlier): `monitoring/tempo/values.yaml`

Added OTLP gRPC (:4317) and HTTP (:4318) receivers.

### Deleted: `monitoring/alloy/`

Entire directory removed — replaced by OTEL Operator + Collector.

## Secrets

| Secret              | Namespace      | 1Password Key | Property   |
|---------------------|----------------|---------------|------------|
| `honeycomb-api-key` | `opentelemetry`| `honeycomb`   | `api-key`  |

## Auto-Instrumentation

Apps opt-in by adding an annotation to their Deployment:

```yaml
metadata:
  annotations:
    instrumentation.opentelemetry.io/inject-python: "true"
    # or: inject-nodejs, inject-java, inject-go, inject-dotnet
```

The Operator's webhook injects an init container with the OTEL SDK. The app automatically generates traces sent to the Agent's OTLP endpoint.

## Deployment

Deployed via the infrastructure AppSet at sync wave 4. The Operator needs cert-manager for webhook TLS (cert-manager is already in the infrastructure AppSet).

## RBAC

The Operator creates ServiceAccounts for the Collectors. The gateway's `otel-gateway` SA needs RBAC to list/watch pods for the `k8sattributes` processor. The Operator handles this automatically.
