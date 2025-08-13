# Project Overview

This repository provisions and manages a GitOps-driven Kubernetes cluster using Talos OS and K3s, deployed onto Proxmox VMs. Argo CD is used to orchestrate continuous delivery of infrastructure and application manifests structured with Kustomize and Helm.

Applications are categorized into `infrastructure`, `monitoring`, and `my-apps`, each managed by its own Argo CD `ApplicationSet` and GitOps workflow.

# Folder Structure

- `/bootstrap/`: Cluster bootstrap and Argo CD bootstrapping
- `/infrastructure/`: Cluster controllers and components (Cilium, Longhorn, Vault plugin, CRDs)
- `/monitoring/`: Prometheus, Grafana, Loki, and related stacks
- `/my-apps/`: User applications deployed with GPU configs, Helm charts, and Gateway routing
- `/apps/`, `/infrastructure/controllers/`: Subdirectories containing Kustomize or Helm-based deployments
- `/terraform/`, `/packer/`, `/talos/`: VM provisioning and image building layers

# Argo CD ApplicationSet Strategy

## ApplicationSet: `infrastructure`

```yaml
  - path: infrastructure/controllers/*
  - path: infrastructure/database/*/*
  - path: infrastructure/networking/*
  - path: infrastructure/storage/*
  - path: infrastructure/crds
```

- Sync wave: `"1"` (after Argo CD bootstrap, before apps)
- Namespace: `{{path.basename}}`
- Project: `infrastructure`
- Use `ignoreDifferences` for CRDs (e.g., `preserveUnknownFields`)
- Sync options:
  - `CreateNamespace=true`
  - `ServerSideApply=true`
  - `RespectIgnoreDifferences=true`
  - `ApplyOutOfSyncOnly=true`
- Retry: exponential backoff, max 5 attempts, 3m cap

## ApplicationSet: `monitoring`

```yaml
  - path: monitoring/*
```

- Sync wave: `"0"` (early sync)
- Project: `monitoring`
- Similar sync options and retry strategy
- Uses `info` fields for Argo CD UI annotation:
  ```yaml
  info:
    - name: Description
      value: Monitoring component: {{path.basename}}
  ```

## ApplicationSet: `my-apps`

```yaml
  - path: my-apps/*/*
```

- Sync wave: `"2"` (after infra + monitoring)
- Project: `my-apps`
- Used for user apps like `comfyui`, `ollama`, etc.
- Auto namespace creation, Helm + Kustomize integration
- `ApplicationSet` dynamically generates per app path
- Supports GPU workloads, Gateway integration, custom storage

# GitOps Best Practices

- All ApplicationSets use `git.directories` generator to reflect file layout in Git
- Use declarative Kustomize overlays or Helm charts per app/environment
- Every folder rendered must include a valid `kustomization.yaml`
- Helm values go into `values.yaml` in app folders
- All apps must support `kustomize build` locally
- Use `ignoreDifferences` for Helm-managed labels, CRDs, and known noisy fields

# Helm + Kustomize Integration

Refer to `1password-connect` as a pattern:

```yaml
helmCharts:
  - name: connect
    repo: https://1password.github.io/connect-helm-charts
    version: 2.0.2
    releaseName: 1password-connect
    valuesFile: values.yaml
    includeCRDs: true
```

Patch Helm resources with Kustomize to:
- Add `HTTPRoute` (Gateway API)
- Mount PVCs or add ConfigMaps
- Inject GPU tolerations and node selectors

# GPU Workload Standards

Apps like `ollama` and `comfyui` follow:

- GPU scheduling using:
  - `nvidia.com/gpu` requests
  - Tolerations for `gpu=true`
  - Node selectors for `pci-0300_10de`
- Runtime classes: `nvidia`
- PVCs for `/root`, `/models`, etc.
- ConfigMaps for GPU runtime tuning
- Liveness and readiness probes with cold start tolerances
- Gateway API exposure via `HTTPRoute` + custom hostnames

# App Structure Conventions

Each app directory contains:

- `namespace.yaml`
- `deployment.yaml`
- `pvc.yaml`
- `service.yaml`
- `httproute.yaml` (for Gateway)
- Optional `configmap.yaml`, `secret.yaml`, `values.yaml`
- Labeled with:
  ```yaml
  labels:
    app: <name>
    app.kubernetes.io/name: <name>
    app.kubernetes.io/component: <component>
  ```

## Service Configuration for HTTPRoute

**CRITICAL**: Services used with HTTPRoute MUST include a named port:

```yaml
apiVersion: v1
kind: Service
spec:
  ports:
    - name: http          # REQUIRED for HTTPRoute
      protocol: TCP
      port: 8080
      targetPort: http
```

**Without the `name: http` field, HTTPRoute will fail silently!**

Common port names:
- `http` - For HTTP services (most common)
- `https` - For HTTPS services 
- `grpc` - For gRPC services

# Cluster Tooling

- Kubernetes: K3s
- OS: Talos OS
- GitOps: Argo CD + ApplicationSet
- Networking: Cilium, MetalLB, Gateway API
- Storage: Longhorn
- Monitoring: Prometheus, Grafana, Loki
- Secrets: Argo Vault Plugin + 1Password
- GPU Workloads: RuntimeClass, tolerations, securityContext
