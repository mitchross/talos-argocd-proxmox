# Alloy + OpenTelemetry + Honeycomb Design

**Date**: 2026-03-22
**Status**: Implementing

## Goal

Deploy Grafana Alloy as a unified OpenTelemetry collector that dual-ships all telemetry to both local Grafana stack and Honeycomb SaaS. This enables learning OTEL while comparing self-hosted vs SaaS observability.

## Architecture

```
                         ┌──────────────┐
                         │  Honeycomb   │
                         │  (OTLP HTTP) │
                         └──────▲───────┘
                                │
┌───────────────────────────────┼────────────────────────┐
│  Alloy DaemonSet (ns: alloy)  │                        │
│                               │                        │
│  ┌──────────────┐    ┌────────┴─────────┐              │
│  │ Pod log       │───▶│ Batch processor  │──────┐      │
│  │ scraping      │    │ (5s / 1024 batch)│      │      │
│  └──────────────┘    └────────┬─────────┘      │      │
│                               │                 │      │
│  ┌──────────────┐             │                 │      │
│  │ OTLP receiver │─────traces─┘                 │      │
│  │ :4317 / :4318 │─────metrics──────────────────┘      │
│  └──────────────┘                                      │
└───────────────────────────────┼────────────────────────┘
                                │
           ┌────────────────────┼────────────────────┐
           │                    │                    │
    ┌──────▼──────┐   ┌────────▼───────┐   ┌────────▼────────┐
    │ Loki Gateway │   │  Tempo :4317   │   │  Prometheus     │
    │ (loki-stack) │   │  (monitoring)  │   │  remote-write   │
    └─────────────┘   └────────────────┘   └─────────────────┘
```

## Data Flow

| Signal  | Source              | Local Destination                          | Honeycomb |
|---------|---------------------|--------------------------------------------|-----------|
| Logs    | Pod stdout/stderr   | Loki via loki.write                        | OTLP HTTP |
| Logs    | K8s events          | Loki via loki.write                        | OTLP HTTP |
| Traces  | Apps → OTLP :4317/8 | Tempo via OTLP gRPC                        | OTLP HTTP |
| Metrics | Apps → OTLP :4317/8 | Prometheus via remote-write                | OTLP HTTP |

## Components

### New: `monitoring/alloy/`

| File                | Purpose                                    |
|---------------------|--------------------------------------------|
| `ns.yaml`           | Namespace `alloy`                          |
| `kustomization.yaml`| Helm chart reference (alloy 1.6.2)         |
| `values.yaml`       | DaemonSet config + Alloy pipeline          |
| `externalsecret.yaml`| Honeycomb API key from 1Password          |

### Modified: `monitoring/tempo/values.yaml`

Added OTLP gRPC (:4317) and HTTP (:4318) receivers so Tempo accepts traces from Alloy.

## Secrets

| Secret              | Namespace | 1Password Key | Property   |
|---------------------|-----------|---------------|------------|
| `honeycomb-api-key` | `alloy`   | `honeycomb`   | `api-key`  |

## How Apps Send Telemetry

Apps instrumented with OTEL SDKs should set their exporter endpoint to:

```
OTEL_EXPORTER_OTLP_ENDPOINT=http://alloy.alloy.svc.cluster.local:4317
```

Alloy handles the fan-out to all backends.

## Deployment

Auto-discovered by the monitoring AppSet (`monitoring/*` glob) at sync wave 5. No manual Application resource needed.
