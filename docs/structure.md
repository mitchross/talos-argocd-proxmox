# Project Structure

```plaintext
.
├── apps/                      # Application manifests
│   ├── ai/                    # AI-related applications
│   ├── media/                 # Media applications
│   └── privacy/               # Privacy-focused applications
├── docs/                      # Documentation
│   ├── argocd.md             # ArgoCD setup and workflow
│   ├── network.md            # Network configuration
│   ├── storage.md            # Storage setup and management
│   └── structure.md          # This file
├── infra/                     # Infrastructure components
│   ├── controllers/          # Kubernetes controllers
│   ├── network/              # Network configurations
│   ├── root-apps/            # Root ArgoCD applications
│   └── storage/              # Storage configurations
├── sets/                      # ApplicationSets
└── README.md                  # Project overview
```

## Directory Organization

### `/apps`
Contains all application manifests organized by category. Each application follows a standard structure:
- `deployment.yaml`: Main application deployment
- `service.yaml`: Service configuration
- `configmap.yaml`: Application configuration
- `httproute.yaml`: Gateway API routes
- `kustomization.yaml`: Kustomize configuration

### `/docs`
Project documentation organized by topic:
- `argocd.md`: ArgoCD setup and workflow details
- `network.md`: Network architecture and configuration
- `storage.md`: Storage setup and management
- `structure.md`: Project structure documentation

### `/infra`
Infrastructure components and configurations:
- `controllers/`: Kubernetes controllers (ArgoCD, Cert-Manager, etc.)
- `network/`: Network configurations (Cilium, CoreDNS, etc.)
- `root-apps/`: Root ArgoCD applications that manage everything
- `storage/`: Storage configurations and classes

### `/sets`
ApplicationSet configurations for dynamic application generation. 