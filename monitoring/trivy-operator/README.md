# Trivy Operator

Conservative cluster vulnerability scanning via Aqua's Trivy Operator.

This app is auto-discovered by the `monitoring/*` ApplicationSet as
`monitoring-trivy-operator`. Do not add a manual ArgoCD `Application`.

## Scope

Phase 1 is intentionally narrow:

- vulnerability reports: enabled
- exposed-secret reports: enabled
- config audit, RBAC, infra assessment, and compliance scanners: disabled
- scan concurrency: capped at 2
- per-CVE Prometheus metrics: disabled to avoid high-cardinality series
- `dvwa` namespace: excluded because it is intentionally vulnerable

The goal is useful signal without turning the cluster into a policy-noise
generator.

## Useful commands

```bash
kubectl -n trivy-operator get pods
kubectl get vulnerabilityreports.aquasecurity.github.io -A
kubectl get exposedsecretreports.aquasecurity.github.io -A
kubectl -n prometheus-stack get servicemonitor trivy-operator
```

Prometheus scrapes the operator through the chart-rendered ServiceMonitor.
The cluster Prometheus selects ServiceMonitors cluster-wide, so the
ServiceMonitor can stay in the `trivy-operator` namespace.

## Expanding later

If vulnerability reports prove useful, enable extra scanners one at a time in
`values.yaml`. Do not enable compliance/RBAC/config-audit all at once; this repo
already has intentional privileged/system workloads, and bulk enablement will
create noisy dashboards before it creates actionable findings.
