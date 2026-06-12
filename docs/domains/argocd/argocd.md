# ArgoCD GitOps Architecture

This is the current ArgoCD bootstrap reference after the full cluster nuke and rebuild.

## Bootstrap Rule

Apply resources in this order:

```text
CRDs first, controllers/apps second, CRs third.
```

Observability is not a core dependency. Core apps must bootstrap without Prometheus.

Do not install Prometheus Operator CRDs early just to satisfy bootstrap apps. ServiceMonitor and PrometheusRule resources belong in later observability overlays. `kube-prometheus-stack` remains the sole owner and provider of `monitoring.coreos.com` CRDs.

## Entry Point Layers

ArgoCD starts from the manually seeded root application:

```text
infrastructure/controllers/argocd/bootstrap/root-application.yaml
```

The root application renders three layers:

1. `core-dependencies`: foundational controllers and storage dependencies.
2. `custom-entrypoints`: repository-specific applications with explicit wave ordering.
3. `applicationsets`: infrastructure, database, monitoring, and workload generators.

See [ArgoCD entrypoints](entrypoints.md) for the concrete files.

## Current Wave Ordering

| Wave | Applications |
|---|---|
| `0` | ArgoCD projects/bootstrap, Cilium, 1Password Connect, External Secrets |
| `1` | cert-manager, Longhorn, snapshot-controller, VolSync |
| `2` | pvc-plumber core, VolSync backup-cluster wiring |
| `3` | CNPG Barman plugin |
| `4` | KEDA core, Temporal worker, infrastructure and database AppSets |
| `5` | OpenTelemetry operator core, monitoring AppSet including `kube-prometheus-stack` |
| `6` | KEDA observability, OpenTelemetry operator observability, workload AppSet |

cert-manager is intentionally Wave `1`: the CNPG Barman plugin depends on it. pvc-plumber Wave `2` is core-only. KEDA and OpenTelemetry ServiceMonitor resources render from Wave `6` observability overlays.

CNPG `enablePodMonitor: true` remains an accepted runtime soft-coupling. It can log transient errors before monitoring exists, but it is not an ArgoCD dry-run blocker.

## Full Nuke Finding

The rebuild validated a design rule: deleting Prometheus must not prevent the core cluster from bootstrapping. An early Prometheus Operator CRD application was considered and explicitly rejected because it would make observability foundational.

## Related Docs

- [ArgoCD entrypoints](entrypoints.md)
- [cluster DR nuke restore runbook](../../docs/disaster-recovery.md)
- [docs index](../../index.md)
