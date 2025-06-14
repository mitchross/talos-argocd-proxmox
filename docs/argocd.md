# 🚀 ArgoCD Installation and Configuration

This guide details the setup and configuration of ArgoCD, which serves as the GitOps engine for our **Talos-based Kubernetes cluster**.

## 📋 Overview

```mermaid
graph TD
    A[Talos Cluster] -->|Install| B[ArgoCD]
    B -->|Create| C[AppProjects]
    C -->|Deploy| D[ApplicationSets]
    D -->|Generate| E[Applications]
    E -->|Sync| F[Resources]
    subgraph "Three-Tier Architecture"
        G[Infrastructure Tier]
        H[Monitoring Tier]
        I[Applications Tier]
    end
    D --> G
    D --> H
    D --> I
```

## 🔄 Deployment Flow

```mermaid
sequenceDiagram
    participant User
    participant ArgoCD
    participant Cluster
    User->>Cluster: Install Initial Components (Talos bootstrapping)
    Note over User,Cluster: talosctl bootstrap, apply configs
    User->>Cluster: Apply ArgoCD projects
    Note over User,Cluster: kubectl apply -f projects.yaml
    User->>Cluster: Apply Infrastructure ApplicationSet
    Note over User,Cluster: kubectl apply -f infrastructure-components-appset.yaml
    Cluster->>ArgoCD: Create Infrastructure Applications
    ArgoCD->>Cluster: Deploy Infrastructure Components (wave -2)
    Note over ArgoCD,Cluster: Cilium, Longhorn, Cert-Manager, etc.
    User->>Cluster: Apply Monitoring ApplicationSet
    Note over User,Cluster: kubectl apply -f monitoring-components-appset.yaml
    Cluster->>ArgoCD: Create Monitoring Applications
    ArgoCD->>Cluster: Deploy Monitoring Components (wave 0)
    Note over ArgoCD,Cluster: Prometheus, Grafana, Loki, etc.
    User->>Cluster: Apply Applications ApplicationSet
    Note over User,Cluster: kubectl apply -f myapplications-appset.yaml
    Cluster->>ArgoCD: Create User Applications
    ArgoCD->>Cluster: Deploy User Applications (wave 1)
    Note over ArgoCD,Cluster: Media apps, AI tools, etc.
```

## 📦 Installation Steps

### 1. Install Gateway API CRDs
```bash
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/latest/download/experimental-install.yaml
```

### 2. Apply custom ArgoCD configuration
```bash
kubectl kustomize --enable-helm infrastructure/controllers/argocd | kubectl apply -f -
```

### 3. Wait for ArgoCD to be ready
```bash
kubectl wait --for=condition=available deployment -l app.kubernetes.io/name=argocd-server -n argocd --timeout=300s
kubectl wait --for=condition=established crd/applications.argoproj.io --timeout=60s
kubectl wait --for=condition=established crd/appprojects.argoproj.io --timeout=60s
```

## 🔧 Project Setup

ArgoCD projects define permissions and boundaries for applications. Our cluster uses four main projects:

- **infrastructure**: Cilium, Longhorn, Cert-Manager, External Secrets, etc.
- **monitoring**: Prometheus, Grafana, Loki, Alertmanager, etc.
- **applications**: User workloads (media, AI, dev, privacy, etc.)
- **ai**: Specialized AI/ML workloads

## 📱 ApplicationSet Management

We use three main ApplicationSets to manage our deployments:

### 1. Infrastructure ApplicationSet
Located at `infrastructure/infrastructure-components-appset.yaml`, this ApplicationSet manages infrastructure components like Cilium, Longhorn, Cert-Manager, and other core services. **All storage (Longhorn, local PVs, StorageClasses) is managed declaratively here.**

### 2. Monitoring ApplicationSet
Located at `monitoring/monitoring-components-appset.yaml`, this ApplicationSet manages monitoring components like Prometheus, Grafana, Loki, and other observability tools.

### 3. Applications ApplicationSet
Located at `my-apps/myapplications-appset.yaml`, this ApplicationSet manages user applications like media servers, AI applications, and other user-facing services.

## 🔢 Deployment Order
Apply the resources in the following order:

1. Apply the projects first:
```bash
kubectl apply -f infrastructure/controllers/argocd/projects.yaml -n argocd
```
2. Apply the ApplicationSets in order:
```bash
kubectl apply -f infrastructure/infrastructure-components-appset.yaml -n argocd
kubectl apply -f monitoring/monitoring-components-appset.yaml -n argocd
kubectl apply -f my-apps/myapplications-appset.yaml -n argocd
```

## 📂 Repository Structure

The repository follows a clean three-tier structure:

- `/infrastructure/` - Infrastructure components (network, storage, security, etc.)
- `/monitoring/` - Monitoring components (Prometheus, Grafana, Loki, etc.)
- `/my-apps/` - User applications (media servers, AI tools, etc.)
- `/docs/` - Documentation
- `/iac/` - Infrastructure as Code (Talos, Terraform, etc.)

## ✅ Key Features

1. **Three-Tier Architecture**:
   - Clear separation of concerns
   - Controlled deployment order
   - Simplified management
2. **Sync Waves**:
   - Infrastructure: -2 (deployed first)
   - Monitoring: 0 (deployed second)
   - Applications: 1 (deployed last)
3. **Declarative Storage**:
   - All storage (Longhorn, StorageClasses, PVs, PVCs) is managed via ArgoCD manifests
   - No manual storage setup required on nodes
4. **No SSH**:
   - All node management via Talosctl API
   - Immutable OS, no shell or package manager

## Best Practices

- **All cluster state is managed in Git** (including storage, monitoring, and user apps)
- **No manual changes** to the cluster; always use GitOps workflow
- **Use sync waves** to control deployment order and dependencies
- **Document all customizations** in `/docs/` and keep manifests up to date
- **Monitor ArgoCD sync status** for drift or errors

## Troubleshooting

| Issue Type | Troubleshooting Steps |
|------------|----------------------|
| **ArgoCD Sync Issues** | • Check application sync status<br>• Review application logs<br>• Check for drift or failed syncs |
| **Storage Issues** | • Verify Longhorn/StorageClass manifests are applied<br>• Check PV/PVC status<br>• Validate node affinity and volume binding |
| **Talos Node Issues** | • `talosctl health`<br>• Check Talos logs: `talosctl logs -n <node-ip> -k` |
| **Monitoring Issues** | • Check Prometheus/Grafana/Alertmanager pod status<br>• Review ServiceMonitor and PodMonitor configs |

### ArgoCD Application Cleanup
```bash
# Remove finalizers from all applications
kubectl get applications -n argocd -o name | xargs -I{} kubectl patch {} -n argocd --type json -p '[{"op": "remove","path": "/metadata/finalizers"}]'
# Delete all applications
kubectl delete applications --all -n argocd
# For stuck ApplicationSets
kubectl get applicationsets -n argocd -o name | xargs -I{} kubectl patch {} -n argocd --type json -p '[{"op": "remove","path": "/metadata/finalizers"}]'
kubectl delete applicationsets --all -n argocd
```

## Talos-Specific Notes
- **No SSH**: All management via `talosctl` API
- **Immutable OS**: No package manager, no shell
- **Declarative**: All config in Git, applied via Talhelper/Talosctl
- **System Extensions**: GPU, storage, and other drivers enabled via config

## See Also
- [Storage Configuration](storage.md)
- [Network Configuration](network.md)
- [Secrets Management](secrets.md)
- [GPU Configuration](gpu.md)

## Design Philosophy

```mermaid
graph TD
    subgraph "Deployment Options"
        A[Pure K8s Manifests] --> B[Kustomize]
        C[Helm Charts] --> D[values.yaml]
    end

    subgraph "Developer Experience"
        B --> E[Direct kubectl apply]
        B --> F[ArgoCD Sync]
        D --> G[helm install]
        D --> F
    end

    style A fill:#9f9,stroke:#333
    style C fill:#f9f,stroke:#333
    style F fill:#9cf,stroke:#333
```

### Why Pure Kubernetes Manifests?

1. **Portability**
   - Manifests can be applied directly with `kubectl`
   - No dependency on ArgoCD for development/testing
   - Easy to understand and modify

2. **Transparency**
   - Clear view of what's being deployed
   - No templating abstraction
   - Direct mapping to Kubernetes objects

3. **Flexibility**
   - Mix and match with Helm when needed
   - Easy to customize with Kustomize
   - No lock-in to specific tools

## Manifest vs Helm Comparison

```mermaid
graph TD
    subgraph "Pure Manifests"
        A[YAML Files] --> B[Kustomize]
        B --> C[Overlay Management]
        C --> D[Direct Application]
    end

    subgraph "Helm Charts"
        E[Templates] --> F[values.yaml]
        F --> G[Chart Dependencies]
        G --> H[Package Management]
    end

    style A fill:#9f9,stroke:#333
    style E fill:#f9f,stroke:#333
```

### When to Use Each

1. **Pure Manifests + Kustomize**
   - Simple applications
   - Clear configuration needs
   - Direct control requirements
   - Development environments

2. **Helm Charts**
   - Complex applications
   - Many configuration options
   - Version management needed
   - Third-party applications

## ArgoCD Configuration

### Helm Support
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: example-helm-app
spec:
  source:
    chart: example
    repoURL: https://charts.example.com
    targetRevision: 1.2.3
    helm:
      values: |
        key: value
```

### Pure Manifest Support
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: example-kustomize-app
spec:
  source:
    path: apps/example
    repoURL: https://github.com/org/repo
    targetRevision: HEAD
```

## Repository Structure

```mermaid
graph TD
    subgraph "Application Types"
        A[Pure Manifests] --> B[apps/*]
        C[Helm Charts] --> D[charts/*]
    end

    subgraph "Configuration"
        B --> E[kustomization.yaml]
        D --> F[values.yaml]
    end

    subgraph "ArgoCD"
        E --> G[Application CR]
        F --> G
    end
```

## Deployment Strategies

### 1. Development Workflow
```mermaid
sequenceDiagram
    participant Dev
    participant Git
    participant K8s
    participant ArgoCD

    Dev->>Git: Push manifests
    Note over Dev,K8s: Can test directly
    Dev->>K8s: kubectl apply
    Note over Git,ArgoCD: Or use GitOps
    Git->>ArgoCD: Webhook
    ArgoCD->>K8s: Apply changes
```

### 2. Production Workflow
```mermaid
sequenceDiagram
    participant Dev
    participant Git
    participant ArgoCD
    participant K8s

    Dev->>Git: Push changes
    Git->>ArgoCD: Webhook
    ArgoCD->>ArgoCD: Validate
    ArgoCD->>K8s: Sync
    K8s->>ArgoCD: Status
```

## Best Practices

### 1. Manifest Organization
- Group related resources
- Use consistent naming
- Leverage labels and annotations
```yaml
metadata:
  labels:
    app.kubernetes.io/name: example
    app.kubernetes.io/part-of: system
```

### 2. Kustomize Usage
```yaml
# kustomization.yaml
resources:
  - deployment.yaml
  - service.yaml
commonLabels:
  app: example
```

### 3. Helm Integration
```yaml
# Application with both Kustomize and Helm
spec:
  source:
    plugin:
      name: kustomize-with-helm
```

## ArgoCD Enhancement

### 1. Plugin Support
```yaml
configManagementPlugins: |
  - name: kustomize-with-helm
    generate:
      command: ["sh", "-c"]
      args: ["kustomize build --enable-helm"]
```

### 2. Sync Waves
```yaml
metadata:
  annotations:
    argocd.argoproj.io/sync-wave: "1"
```

### 3. Health Checks
```yaml
spec:
  ignoreDifferences:
  - group: apps
    kind: Deployment
    jsonPointers:
    - /spec/replicas
```

## Migration Strategies

### From Helm to Pure Manifests
1. Export current Helm values
2. Generate manifests
3. Adapt to Kustomize
4. Test with kubectl
5. Commit to Git

### From Pure Manifests to Helm
1. Create Helm templates
2. Extract values
3. Test locally
4. Update ArgoCD application

## Validation and Testing

```mermaid
graph TD
    A[New Manifest] --> B{Test Locally}
    B -->|Success| C[Commit to Git]
    B -->|Fail| D[Modify]
    C --> E[ArgoCD Sync]
    E -->|Success| F[Done]
    E -->|Fail| D
```

## Deployment Flow

```mermaid
graph TD
    subgraph "1. Initial Setup"
        A[Install ArgoCD] --> B[Create Projects]
        B --> C[infrastructure project]
        B --> D[applications project]
        B --> M[monitoring project]
        B --> N[ai project]
    end

    subgraph "2. Infrastructure Deployment"
        C --> E[Apply infrastructure ApplicationSet]
        E --> F[networking]
        E --> G[storage]
        E --> H[controllers]
        E --> J[database]
    end

    subgraph "3. Monitoring Deployment"
        M --> O[Apply monitoring ApplicationSet]
        O --> P[k8s-monitoring]
    end

    subgraph "4. Application Deployment"
        N --> K[Apply myapplications ApplicationSet]
        K --> L[home apps]
        K --> Q[media apps]
        K --> R[ai apps]
        K --> S[development apps]
        K --> T[external apps]
        K --> U[privacy apps]
    end

    %% Dependencies
    F & G & H & J --> O
    O --> K
    
    style A fill:#f9f,stroke:#333
    style C fill:#9cf,stroke:#333
    style D fill:#9cf,stroke:#333
    style M fill:#9cf,stroke:#333
    style N fill:#9cf,stroke:#333
    style E fill:#9f9,stroke:#333
    style O fill:#9f9,stroke:#333
    style K fill:#9f9,stroke:#333
```

## Installation

Our ArgoCD installation uses a Kustomize-based approach with custom configurations:

### 1. Installation Steps
```bash
# Install Gateway API CRDs first
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/latest/download/experimental-install.yaml

# Install ArgoCD with our custom configuration
kubectl kustomize --enable-helm infrastructure/controllers/argocd | kubectl apply -f -

# Wait for ArgoCD to be ready
kubectl wait --for=condition=available deployment -l app.kubernetes.io/name=argocd-server -n argocd --timeout=300s

# Wait for CRDs to be established
kubectl wait --for=condition=established crd/applications.argoproj.io --timeout=60s
kubectl wait --for=condition=established crd/appprojects.argoproj.io --timeout=60s
```

### 2. Project Setup
We use the following projects to separate different types of applications:

```yaml
# Project definitions (infrastructure/controllers/argocd/projects.yaml)
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: infrastructure
  namespace: argocd
spec:
  sourceRepos:
    - '*'
  destinations:
    - namespace: '*'
      server: '*'
  clusterResourceWhitelist:
    - group: '*'
      kind: '*'
---
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: applications
  namespace: argocd
spec:
  sourceRepos:
    - '*'
  destinations:
    - namespace: '*'
      server: '*'
  clusterResourceWhitelist:
    - group: '*'
      kind: 'PersistentVolume'
    - group: cert-manager.io
      kind: ClusterIssuer
    - group: '*'
      kind: 'CustomResourceDefinition'
    - group: '*'
      kind: 'Namespace'
---
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: monitoring
  namespace: argocd
spec:
  sourceRepos:
    - '*'
  destinations:
    - namespace: '*'
      server: '*'
  clusterResourceWhitelist:
    - group: '*'
      kind: '*'
---
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: ai
  namespace: argocd
spec:
  sourceRepos:
    - '*'
  destinations:
    - namespace: '*'
      server: '*'
  clusterResourceWhitelist:
    - group: '*'
      kind: 'PersistentVolume'
    - group: '*'
      kind: 'CustomResourceDefinition'
    - group: '*'
      kind: 'ClusterRole'
    - group: '*'
      kind: 'ClusterRoleBinding'
    - group: '*'
      kind: 'Namespace'
```

### 3. Application Management
We use three main ApplicationSets to manage our deployments:

```yaml
# Infrastructure ApplicationSet (infrastructure/infrastructure-components-appset.yaml)
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: infrastructure-components
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "-2"
spec:
  generators:
    - git:
        repoURL: https://github.com/mitchross/k3s-argocd-proxmox
        revision: HEAD
        directories:
          - path: infrastructure/*/*
  template:
    metadata:
      name: 'infra-{{path.basename}}'
      labels:
        type: infrastructure
    spec:
      project: infrastructure
      source:
        plugin:
          name: kustomize-build-with-helm
        repoURL: https://github.com/mitchross/k3s-argocd-proxmox
        targetRevision: HEAD
        path: '{{path}}'
      destination:
        server: https://kubernetes.default.svc
        namespace: '{{path.basename}}'
      syncPolicy:
        automated:
          selfHeal: true
          prune: true

# Monitoring ApplicationSet (monitoring/monitoring-components-appset.yaml)
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: monitoring-components
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "0"
spec:
  generators:
    - git:
        repoURL: https://github.com/mitchross/k3s-argocd-proxmox
        revision: HEAD
        directories:
          - path: monitoring/*/*
  template:
    metadata:
      name: 'monitoring-{{path.basename}}'
      labels:
        type: monitoring
    spec:
      project: infrastructure
      source:
        plugin:
          name: kustomize-build-with-helm
        repoURL: https://github.com/mitchross/k3s-argocd-proxmox
        targetRevision: HEAD
        path: '{{path}}'
      destination:
        server: https://kubernetes.default.svc
        namespace: '{{path.basename}}'
      syncPolicy:
        automated:
          selfHeal: true
          prune: true

# Applications ApplicationSet (my-apps/myapplications-appset.yaml)
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: applications
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "1"
spec:
  generators:
    - git:
        repoURL: https://github.com/mitchross/k3s-argocd-proxmox
        revision: HEAD
        directories:
          - path: my-apps/*/*
  template:
    metadata:
      name: '{{path[1]}}-{{path.basename}}'
      labels:
        type: application
    spec:
      project: ai
      source:
        plugin:
          name: kustomize-build-with-helm
        repoURL: https://github.com/mitchross/k3s-argocd-proxmox
        targetRevision: HEAD
        path: '{{path}}'
      destination:
        server: https://kubernetes.default.svc
        namespace: '{{path.basename}}'
      syncPolicy:
        automated:
          selfHeal: true
          prune: true
```

### 4. Deployment Order
Important: Follow this specific order for deployment:

1. Apply projects first:
```bash
kubectl apply -f infrastructure/controllers/argocd/projects.yaml -n argocd
```

2. Apply infrastructure and wait for it to be ready:
```bash
kubectl apply -f infrastructure/infrastructure-components-appset.yaml -n argocd
```

3. Apply monitoring:
```bash
kubectl apply -f monitoring/monitoring-components-appset.yaml -n argocd
```

4. Finally, apply applications:
```bash
kubectl apply -f my-apps/myapplications-appset.yaml -n argocd
```

### Repository Structure
```
.
├── infrastructure/           # Infrastructure components
│   ├── controllers/          # Kubernetes controllers
│   │   └── argocd/           # ArgoCD configuration and projects
│   ├── networking/           # Network configurations
│   ├── storage/              # Storage configurations
│   └── infrastructure-components-appset.yaml  # Main infrastructure ApplicationSet
├── monitoring/               # Monitoring components
│   ├── k8s-monitoring/       # Kubernetes monitoring stack
│   └── monitoring-components-appset.yaml  # Main monitoring ApplicationSet
├── my-apps/                  # User applications
│   ├── ai/                   # AI-related applications
│   ├── media/                # Media applications
│   ├── development/          # Development tools
│   ├── external/             # External service integrations
│   ├── home/                 # Home automation apps
│   ├── privacy/              # Privacy-focused applications
│   └── myapplications-appset.yaml  # Main applications ApplicationSet
```

### Key Features
- Three-tier architecture separating infrastructure, monitoring, and applications
- Sync waves ensure proper deployment order
- Simple directory patterns without complex exclude logic
- All applications managed through just three top-level ApplicationSets
``` 