# GPU Monitoring with DCGM Exporter

## Overview
GPU monitoring is integrated into the Prometheus/Grafana stack using NVIDIA's DCGM Exporter.

## Components Added

### 1. DCGM Exporter (`dcgm-exporter.yaml`)
- **Namespace**: `prometheus-stack`
- **Type**: DaemonSet (runs on GPU nodes only)
- **Port**: 9400
- **Metrics**: Full GPU telemetry (utilization, memory, temperature, power, etc.)

### 2. ServiceMonitor (`custom-servicemonitors.yaml`)
- **Name**: `dcgm-exporter-metrics`
- **Scrape Interval**: 15s
- **Target**: DCGM Exporter service

### 3. GPU Alerts (`gpu-alerts.yaml`)
- High/Critical GPU utilization (90%/95%)
- High/Critical memory usage (85%/95%)
- High/Critical temperature (80°C/90°C)
- High power draw (>400W)
- GPU down/unavailable alerts
- Low clock speed warnings

### 4. Grafana Dashboard (`gpu-dashboard.yaml`)
- **Dashboard UID**: `gpu-monitoring`
- **Panels**:
  - GPU Utilization (%)
  - Memory Usage (bytes)
  - Temperature (°C)
  - Power Usage (watts)
  - Clock Speeds (SM/Memory)
  - Status Overview Table

## Key Metrics

| Metric | Description |
|--------|-------------|
| `DCGM_FI_DEV_GPU_UTIL` | GPU utilization percentage |
| `DCGM_FI_DEV_FB_USED` | GPU memory used (bytes) |
| `DCGM_FI_DEV_FB_TOTAL` | GPU memory total (bytes) |
| `DCGM_FI_DEV_GPU_TEMP` | GPU temperature (°C) |
| `DCGM_FI_DEV_POWER_USAGE` | Power consumption (watts) |
| `DCGM_FI_DEV_SM_CLOCK` | Streaming Multiprocessor clock (MHz) |
| `DCGM_FI_DEV_MEM_CLOCK` | Memory clock (MHz) |

## Quick Commands

### Check GPU Metrics
```bash
# Port forward to DCGM exporter
kubectl port-forward -n prometheus-stack svc/dcgm-exporter 9400:9400

# View raw metrics
curl localhost:9400/metrics | grep DCGM_FI_DEV
```

### Access Grafana Dashboard
1. Open Grafana
2. Navigate to **Dashboards**
3. Find **GPU Monitoring Dashboard**
4. Or use direct URL: `/d/gpu-monitoring/gpu-monitoring-dashboard`

### Deploy Changes
```bash
# Deploy monitoring stack with GPU monitoring
kubectl apply -k monitoring/prometheus-stack/
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
- DCGM requires privileged containers and GPU nodes (the `prometheus-stack` namespace has been configured for this).
- Metrics are collected every 15 seconds
- Dashboard auto-refreshes every 30 seconds
- Alerts are configured for typical GPU workload thresholds
- Compatible with NVIDIA GPUs only 