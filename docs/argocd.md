# 🚀 ArgoCD Installation and Configuration

This guide details the setup and configuration of ArgoCD, which serves as the GitOps engine for our **Talos-based Kubernetes cluster**.

## 📋 Overview & Deployment Flow

The cluster uses a **clean, enterprise-grade GitOps approach** with ArgoCD managing itself and three separate ApplicationSets for different workload types. This pattern is commonly used in production environments for clear separation of concerns and simplified management.

The deployment flow follows this simple pattern:

```mermaid
graph TD;
    subgraph "Git Repository"
        Bootstrap["argocd-app.yaml<br/>(Bootstrap Application)"]
        
        InfraAppSet["infrastructure/root-appset.yaml<br/>(Infrastructure ApplicationSet)"]
        MonAppSet["monitoring/monitoring-components-appset.yaml<br/>(Monitoring ApplicationSet)"]
        AppsAppSet["my-apps/myapplications-appset.yaml<br/>(Applications ApplicationSet)"]
        
        InfraDirs["infrastructure/*/*<br/>(e.g., controllers/argocd)"]
        MonDirs["monitoring/*<br/>(e.g., prometheus-stack)"]
        AppDirs["my-apps/*/*<br/>(e.g., media/plex)"]

        InfraAppSet -- "scans" --> InfraDirs
        MonAppSet -- "scans" --> MonDirs
        AppsAppSet -- "scans" --> AppDirs
    end

    subgraph "Argo CD"
        ArgoCD["ArgoCD Controller"] -- "Deploys itself via" --> Bootstrap
        
        subgraph "Self-Managed ApplicationSets"
            InfraAS["Infrastructure ApplicationSet"]
            MonAS["Monitoring ApplicationSet"] 
            AppsAS["Applications ApplicationSet"]
        end

        Bootstrap -- "Creates" --> InfraAS
        Bootstrap -- "Creates" --> MonAS
        Bootstrap -- "Creates" --> AppsAS
        
        subgraph "Generated Applications"
            InfraApps["infra-argocd<br/>infra-cilium<br/>infra-longhorn<br/>..."]
            MonApps["monitoring-prometheus-stack<br/>monitoring-loki-stack<br/>..."]
            UserApps["media-plex<br/>ai-ollama<br/>home-frigate<br/>..."]
        end

        InfraAS -- "Generates" --> InfraApps
        MonAS -- "Generates" --> MonApps
        AppsAS -- "Generates" --> UserApps
    end
    
    subgraph "Kubernetes Cluster"
        InfraRes["Infrastructure Resources<br/>(ArgoCD, Cilium, Storage)"]
        MonRes["Monitoring Resources<br/>(Prometheus, Grafana, Loki)"]
        AppRes["Application Resources<br/>(Plex, Ollama, Frigate)"]
    end

    InfraApps -- "deploys" --> InfraRes
    MonApps -- "deploys" --> MonRes
    UserApps -- "deploys" --> AppRes

    style Bootstrap fill:#f9f,stroke:#333,stroke-width:2px
    style ArgoCD fill:#9cf,stroke:#333,stroke-width:2px
```

## 📦 Installation Steps

The entire cluster bootstrap process is handled by a single bootstrap `Application` that makes ArgoCD manage itself and all other workloads.

### 1. Install Gateway API CRDs
This is a prerequisite for Cilium's Gateway API integration.
```bash
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.2.0/standard-install.yaml
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.2.0/experimental-install.yaml
```

### 2. Bootstrap ArgoCD (One Command Deployment)
Deploy the self-managing ArgoCD `Application`. This bootstrap application will:
1. Install ArgoCD itself
2. Create the three ApplicationSets 
3. Automatically discover and deploy all infrastructure, monitoring, and applications

```bash
# Apply the ArgoCD bootstrap application - this is the ONLY manual command needed
kubectl apply -f infrastructure/argocd-app.yaml
```

**That's it!** ArgoCD will now manage itself and deploy everything else automatically.

## 🔧 Project Setup

ArgoCD projects define permissions and boundaries for applications. Our cluster uses three main projects with clear separation:

- **infrastructure**: Core cluster components (Cilium, Longhorn, Cert-Manager, etc.)
- **monitoring**: Observability stack (Prometheus, Grafana, Loki, etc.)
- **my-apps**: All user workloads (media, AI, dev, privacy, etc.)

These `AppProject` resources are defined in `infrastructure/projects.yaml` and are deployed automatically.

## 📱 ApplicationSet Management

We use **three simple ApplicationSets** (enterprise pattern):

### 1. Infrastructure ApplicationSet (`infrastructure/root-appset.yaml`)
```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: infrastructure-components
  namespace: argocd
spec:
  generators:
    - git:
        repoURL: https://github.com/mitchross/k3s-argocd-proxmox.git
        revision: HEAD
        directories:
          - path: infrastructure/*/*
  template:
    metadata:
      name: 'infra-{{path.basename}}'
    spec:
      project: infrastructure
      # ... rest of config
```

### 2. Monitoring ApplicationSet (`monitoring/monitoring-components-appset.yaml`)
```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: monitoring-components
  namespace: argocd
spec:
  generators:
    - git:
        directories:
          - path: monitoring/*/*
  template:
    metadata:
      name: 'monitoring-{{path.basename}}'
    spec:
      project: monitoring
      # ... rest of config
```

### 3. Applications ApplicationSet (`my-apps/myapplications-appset.yaml`)
```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: applications
  namespace: argocd
spec:
  generators:
    - git:
        directories:
          - path: my-apps/*/*
  template:
    metadata:
      name: '{{path[1]}}-{{path.basename}}'
    spec:
      project: my-apps
      # ... rest of config
```

## 📂 Repository Structure

The repository follows a clean three-tier structure that maps directly to the ApplicationSets:

```
├── infrastructure/          # Infrastructure ApplicationSet
│   ├── controllers/         # ArgoCD, External Secrets, etc.
│   ├── networking/          # Cilium, Gateway API, etc.
│   ├── storage/             # Longhorn, CSI drivers, etc.
│   ├── database/            # PostgreSQL, Redis operators
│   └── root-appset.yaml     # Infrastructure ApplicationSet
├── monitoring/              # Monitoring ApplicationSet
│   ├── prometheus-stack/    # Prometheus, Grafana, AlertManager
│   ├── loki-stack/          # Loki, Promtail
│   └── monitoring-components-appset.yaml
├── my-apps/                 # Applications ApplicationSet
│   ├── ai/                  # AI tools (Ollama, ComfyUI, etc.)
│   ├── media/               # Media servers (Plex, Jellyfin, etc.)
│   ├── home/                # Home automation (Frigate, HA, etc.)
│   ├── development/         # Dev tools (Headlamp, IT-Tools, etc.)
│   ├── privacy/             # Privacy tools (SearXNG, ProxiTok, etc.)
│   └── myapplications-appset.yaml
└── docs/                    # Documentation
```

## ✅ Key Features

1. **Self-Managing ArgoCD**:
   - ArgoCD manages its own installation and upgrades
   - ApplicationSets are part of the ArgoCD application itself
   - Zero manual intervention after bootstrap

2. **Enterprise Pattern**:
   - Clear separation of concerns with three ApplicationSets
   - Follows GitOps best practices
   - Scalable and maintainable

3. **Simple Directory Discovery**:
   - No complex excludes or wildcards
   - Each ApplicationSet scans its own directory pattern
   - Easy to understand and modify

4. **Production Ready**:
   - Proper error handling and retries
   - Automated sync with self-healing
   - Comprehensive ignore patterns for drift

## 🚀 Deployment Workflow

### Development/Testing
```bash
# Test individual applications
kubectl apply -k infrastructure/controllers/argocd --dry-run=server

# Test entire infrastructure
kubectl apply -k infrastructure/
```

### Production Deployment
```bash
# Single command deployment
kubectl apply -f infrastructure/argocd-app.yaml

# Monitor deployment progress
kubectl get applications -n argocd -w
```

## Best Practices

- **All cluster state is managed in Git** - no manual changes
- **ArgoCD manages itself** - including upgrades and configuration changes
- **Clear separation** - infrastructure, monitoring, and applications are separate
- **Simple patterns** - easy directory discovery without complex logic
- **Production ready** - proper retries, error handling, and monitoring

## Troubleshooting

### Check ArgoCD Applications
```bash
# View all applications
kubectl get applications -n argocd

# Check ApplicationSet status
kubectl get applicationsets -n argocd

# View application details
kubectl describe application infra-argocd -n argocd
```

### Common Issues
| Issue | Solution |
|-------|----------|
| **ApplicationSet not generating apps** | Check directory patterns and Git connectivity |
| **Applications stuck in sync** | Review application logs and sync policies |
| **ArgoCD UI not accessible** | Check HTTPRoute and certificate status |
| **Kustomize plugin errors** | Verify plugin configuration in ArgoCD values |

### ArgoCD Self-Management
```bash
# Check ArgoCD managing itself
kubectl get application argocd -n argocd -o yaml

# View ArgoCD ApplicationSets
kubectl get applicationsets -n argocd
```

## Enterprise Patterns

This setup follows **enterprise GitOps patterns**:

1. **Infrastructure as Code**: Everything defined in Git
2. **Self-Service**: Developers can add applications by creating directories
3. **Separation of Concerns**: Clear boundaries between workload types
4. **Automated Operations**: Zero-touch deployments after bootstrap
5. **Observability**: Full monitoring and alerting stack
6. **Security**: Proper RBAC and project boundaries

## Taking to Production

This homelab setup translates directly to enterprise environments:

1. **Replace Git repo** with your organization's repository
2. **Add proper RBAC** for team-based access
3. **Configure notifications** for Slack/Teams integration
4. **Add policy enforcement** with tools like OPA Gatekeeper
5. **Implement proper secrets management** with External Secrets or Vault
6. **Add multi-cluster support** with ArgoCD ApplicationSets

The patterns and structure remain the same - this is **production-grade GitOps**. 