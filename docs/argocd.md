# ArgoCD Setup and Workflow

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