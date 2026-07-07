# Trivy Operator

Conservative cluster vulnerability scanning via Aqua's Trivy Operator.

This app is auto-discovered by the `monitoring/*` ApplicationSet as
`monitoring-trivy-operator`. Do not add a manual ArgoCD `Application`.

## Scope

Phase 1 is intentionally narrow:

- vulnerability reports: enabled
- exposed-secret reports: enabled
- config audit, RBAC, infra assessment, and compliance scanners: disabled
- SBOM generation: disabled
- scan concurrency: capped at 2
- per-CVE Prometheus metrics: disabled to avoid high-cardinality series
- cluster-wide Secret/ServiceAccount access for image pull credentials: disabled
- `dvwa` namespace: excluded because it is intentionally vulnerable

The goal is useful signal without turning the cluster into a policy-noise
generator.

## Useful commands

```bash
kubectl -n argocd get app monitoring-trivy-operator
kubectl -n trivy-operator get pods
kubectl -n trivy-operator get deploy,svc,servicemonitor
kubectl get vulnerabilityreports.aquasecurity.github.io -A
kubectl get exposedsecretreports.aquasecurity.github.io -A
kubectl -n trivy-operator get servicemonitor trivy-operator
kubectl -n trivy-operator logs deploy/trivy-operator --tail=100
```

Prometheus scrapes the operator through the chart-rendered ServiceMonitor.
The cluster Prometheus selects ServiceMonitors cluster-wide, so the
ServiceMonitor can stay in the `trivy-operator` namespace.

On first sync, expect the operator and CRDs to appear before reports are
populated. Reports are created by scan jobs and can lag the ArgoCD sync by a few
minutes.

## Private images

`accessGlobalSecretsAndServiceAccount` is disabled. That keeps Trivy from
getting cluster-wide Secret/ServiceAccount read permissions just to discover
image pull credentials.

If reports are missing for private images and the operator logs show pull/auth
errors, either add narrowly-scoped registry credentials for Trivy or explicitly
revisit that value. Do not enable it preemptively.

## Expanding later

If vulnerability reports prove useful, enable extra scanners one at a time in
`values.yaml`. Do not enable compliance/RBAC/config-audit all at once; this repo
already has intentional privileged/system workloads, and bulk enablement will
create noisy dashboards before it creates actionable findings.
