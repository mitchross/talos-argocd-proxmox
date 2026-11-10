# GPU monitoring with DCGM Exporter

## Overview

NVIDIA's DCGM Exporter feeds GPU metrics into the Prometheus/Grafana stack.

## Components added

### 1. DCGM Exporter (`dcgm-exporter.yaml`)

A DaemonSet in the `prometheus-stack` namespace. It runs on GPU nodes only and listens on port 9400. It exports GPU utilization, memory, temperature, power and related metrics.

### 2. ServiceMonitor (`custom-servicemonitors.yaml`)

`dcgm-exporter-metrics` scrapes the DCGM Exporter service every 15s.

### 3. GPU alerts (`gpu-alerts.yaml`)
- High/Critical GPU utilization (90%/95%)
- High/Critical memory usage (85%/95%)
- High/Critical temperature (80°C/90°C)
- High power draw (>400W)
- GPU down/unavailable alerts
- Low clock speed warnings

### 4. Grafana dashboard (`dashboards/ai/gpu-overview.json`)

Dashboard UID `gpu-overview`, in the Grafana folder AI. It shows per-card utilization, VRAM, temperature, power against the 200 W cap, clocks,
PCIe link retries, and which pod holds each card.

## Key metrics

| Metric | Description |
|--------|-------------|
| `DCGM_FI_DEV_GPU_UTIL` | GPU utilization percentage |
| `DCGM_FI_DEV_FB_USED` | GPU memory used (bytes) |
| `DCGM_FI_DEV_FB_TOTAL` | GPU memory total (bytes) |
| `DCGM_FI_DEV_GPU_TEMP` | GPU temperature (°C) |
| `DCGM_FI_DEV_POWER_USAGE` | Power consumption (watts) |
| `DCGM_FI_DEV_SM_CLOCK` | Streaming Multiprocessor clock (MHz) |
| `DCGM_FI_DEV_MEM_CLOCK` | Memory clock (MHz) |

## Quick commands

### Check GPU metrics
```bash
# Port forward to DCGM exporter
kubectl port-forward -n prometheus-stack svc/dcgm-exporter 9400:9400

# View raw metrics
curl localhost:9400/metrics | grep DCGM_FI_DEV
```

### Access Grafana dashboard
1. Open Grafana
2. Navigate to **Dashboards**
3. Open the AI folder, then GPU Overview
4. Or use the direct URL: `/d/gpu-overview`

### Deploy changes
```bash
# Deploy monitoring stack with GPU monitoring
kubectl apply -k monitoring/metrics/prometheus-stack/
```

### Troubleshooting
```bash
# Check DCGM exporter status
kubectl get pods -n prometheus-stack -l app.kubernetes.io/name=dcgm-exporter

# View DCGM logs
kubectl logs -n prometheus-stack -l app.kubernetes.io/name=dcgm-exporter

# Check if metrics are being scraped
kubectl exec -n prometheus-stack deployment/kube-prometheus-stack-prometheus -- \
  promtool query instant 'up{job="dcgm-exporter-metrics"}'
```

## Notes
- DCGM requires privileged containers and GPU nodes. The `prometheus-stack` namespace is already set up for this.
- Prometheus scrapes metrics every 15 seconds.
- The dashboard refreshes every 30 seconds.
- Alert thresholds suit typical GPU workloads.
- DCGM supports NVIDIA GPUs only. 