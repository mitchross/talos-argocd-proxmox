# Project Structure

```plaintext
.
├── infrastructure/           # Infrastructure components
│   ├── argocd-app.yaml       # ArgoCD self-management Application
│   ├── root-appset.yaml      # Root ApplicationSet to deploy all tiers
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
├── docs/                     # Documentation
│   ├── argocd.md             # ArgoCD setup and workflow
│   ├── network.md            # Network configuration
│   ├── storage.md            # Storage setup and management
│   └── structure.md          # This file
└── README.md                 # Project overview
```

## Key Organization Principles

1. **Three-Tier Structure**
   - Infrastructure components (foundation layer)
   - Monitoring components (observability layer)
   - User applications (workload layer)

2. **Application Categories** 
   - Each category folder contains related applications
   - Standardized application structure in each folder

3. **Simplified Management**
   - A root ApplicationSet deploys one ApplicationSet per tier
   - Clear separation of concerns
   - Controlled deployment order through sync waves

## Bootstrap and ApplicationSet Organization

This project uses a two-file bootstrap model located in the `/infrastructure` directory, followed by a set of tier-specific ApplicationSets that are discovered automatically.

### Bootstrap Files
- **`infrastructure/argocd-app.yaml`**: This is an Argo CD `Application` that manages Argo CD itself. It points to `infrastructure/controllers/argocd` to deploy the Helm chart and all its configurations, including the `AppProject` definitions. This is the "app of apps" pattern.
- **`infrastructure/root-appset.yaml`**: This is an `ApplicationSet` that acts as the "appset of appsets". It automatically discovers and deploys all `*appset.yaml` files within the repository, effectively deploying all three tiers of the architecture.

### Tier ApplicationSets

#### `/infrastructure/infrastructure-components-appset.yaml`
- Manages all infrastructure components
- Uses infrastructure project
- Deploys with negative sync wave (-2) to ensure it runs first
- Pattern: `infrastructure/*/*`

#### `/monitoring/monitoring-components-appset.yaml`
- Manages all monitoring components
- Uses infrastructure project
- Deploys with neutral sync wave (0)
- Pattern: `monitoring/*/*`

#### `/my-apps/myapplications-appset.yaml`
- Manages all user applications
- Uses ai project (provides necessary permissions)
- Deploys with positive sync wave (1) to ensure it runs last
- Pattern: `my-apps/*/*`

## Directory Contents

### `/infrastructure`
Infrastructure components and configurations:
- `controllers/`: Core Kubernetes controllers (ArgoCD, Cert-Manager, etc.)
- `networking/`: Network configurations (Cilium, Cloudflared, etc.)
- `storage/`: Storage configurations and classes
- `database/`: Database operators and configurations

### `/monitoring`
Monitoring and observability components:
- `k8s-monitoring/`: Kubernetes monitoring stack (Prometheus, Grafana, etc.)
- Additional monitoring components as needed

### `/my-apps`
User applications organized by category:
- `ai/`: AI-related applications (Ollama, ComfyUI, etc.)
- `media/`: Media applications (Plex, Jellyfin, etc.)
- `development/`: Development tools (Kafka, Temporal, etc.)
- `external/`: External integrations (Proxmox, TrueNAS, etc.)
- `home/`: Home automation (Frigate, Wyze-Bridge, etc.)
- `privacy/`: Privacy applications (Searxng, Libreddit, etc.)

## Standard Application Structure
Each application follows a standard structure:
- `deployment.yaml`: Main application deployment
- `service.yaml`: Service configuration
- `configmap.yaml`: Application configuration
- `httproute.yaml`: Gateway API routes
- `kustomization.yaml`: Kustomize configuration
- `pvc.yaml`: Persistent volume claims (if needed) 