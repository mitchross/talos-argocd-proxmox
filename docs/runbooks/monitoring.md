# Monitoring Stack Runbook

## Overview
This runbook covers operational checks, troubleshooting, and incident response for the monitoring stack (Prometheus, Grafana, Loki, Alertmanager, Thanos) in a Talos + ArgoCD managed cluster.

---

## 1. Health Checks

### Prometheus
- `kubectl get pods -n monitoring -l app.kubernetes.io/name=prometheus`
- `kubectl port-forward -n monitoring svc/prometheus 9090:9090` (UI access)
- Check `/targets` and `/alerts` in Prometheus UI

### Grafana
- `kubectl get pods -n monitoring -l app.kubernetes.io/name=grafana`
- `kubectl port-forward -n monitoring svc/grafana 3000:3000`
- Log in and check dashboard data sources

### Loki
- `kubectl get pods -n monitoring -l app.kubernetes.io/name=loki`
- `kubectl port-forward -n monitoring svc/loki 3100:3100`
- Query logs in Grafana Explore

### Alertmanager
- `kubectl get pods -n monitoring -l app.kubernetes.io/name=alertmanager`
- `kubectl port-forward -n monitoring svc/alertmanager 9093:9093`
- Check alert status and silences

### Thanos
- `kubectl get pods -n monitoring -l app.kubernetes.io/name=thanos`
- Check Thanos sidecar, store, and query pods

---

## 2. Troubleshooting & Diagnosis

### General
- `kubectl get pods -n monitoring`
- `kubectl describe pod <pod> -n monitoring`
- `kubectl logs <pod> -n monitoring`
- `kubectl get servicemonitor,podmonitor -A`
- `kubectl get prometheusrule -A`

### Common Issues & Fixes
| Symptom | Diagnosis | Remediation |
|---------|-----------|-------------|
| Prometheus targets down | Check `/targets` UI, pod logs | Validate ServiceMonitor, endpoints, network policies |
| Grafana dashboards empty | Check data source config | Validate Prometheus/Loki endpoints, re-sync manifests |
| Loki not ingesting logs | Check promtail/agent logs | Validate DaemonSet, node selectors, scrape configs |
| Alertmanager not sending | Check alertmanager logs, `/alerts` UI | Validate alert rules, notification configs |
| Thanos query slow/missing data | Check Thanos store/query logs | Validate object storage, sidecar connectivity |

---

## 3. Alert Response & Escalation

### On-call SRE Actions
- Acknowledge alert in Alertmanager
- Check runbook link in alert annotation
- Follow diagnosis/remediation steps above
- If unable to resolve, escalate to platform lead

### Escalation Criteria
- Persistent data loss or unavailability
- Repeated alert flapping with no clear cause
- Storage backend (MinIO/Longhorn) outage
- Prometheus/Thanos query failures cluster-wide

---

## 4. GitOps & Talos Notes
- **No manual changes to monitoring manifests.**
- All changes must be made in Git and synced via ArgoCD.
- **No SSH to Talos nodes.**
- Use `kubectl` and `talosctl` for diagnostics only.
- Validate ArgoCD sync status: `kubectl get application -n argocd`

---

## 5. Best Practices
- Monitor monitoring stack itself (meta-monitoring)
- Use ServiceMonitors/PodMonitors for all critical components
- Keep alert rules actionable and annotated with runbook links
- Regularly test alert delivery and notification channels
- Document all incidents and postmortems in `/docs/runbooks/` 