# Monitoring Guidelines

## Common Pitfalls

- **Tempo/Loki S3 creds**: Use `extraEnvFrom` with secretRef, NOT inline `${VAR}` in config (they don't expand env vars)
- **ArgoCD metrics**: Must be per-component (`controller.metrics`, `server.metrics`, etc.), top-level `metrics:` key does nothing
- **Longhorn ServiceMonitor**: Select `app: longhorn-manager` (NOT `app.kubernetes.io/name: longhorn-manager`)
- **ArgoCD ignoreDifferences**: Use `jqPathExpressions` NOT `jsonPointers` for wildcards (RFC 6901 doesn't support `*`)
- **PVC storage in ignoreDifferences**: Must ignore `.spec.resources.requests.storage` — can't shrink existing PVCs

## Key Files

- Custom ServiceMonitors: `monitoring/prometheus-stack/custom-servicemonitors.yaml`
- Custom alerts: `monitoring/prometheus-stack/custom-alerts.yaml`
- GPU alerts: `monitoring/prometheus-stack/gpu-alerts.yaml`
