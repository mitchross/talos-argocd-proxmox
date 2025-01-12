# Storage Configuration

## Overview

```mermaid
graph TD
    subgraph "Storage Types"
        A[Local Storage] --> B[Node-bound PVs]
        C[SMB Storage] --> D[Network PVs]
    end

    subgraph "Volume Binding"
        B --> E[Local Path Provisioner]
        D --> F[SMB CSI Driver]
    end

    subgraph "Applications"
        E --> G[Application Data]
        F --> H[Media Storage]
    end

    style A fill:#f9f,stroke:#333
    style C fill:#bbf,stroke:#333
```

## Directory Structure

```plaintext
/datapool/kubernetes/
├── arr/                  # *arr apps data
├── comfyui/             # ComfyUI storage
├── config/              # Application configs
├── crowdsec/            # Security monitoring
├── frigate/             # Camera monitoring
├── homepage-dashboard/  # Dashboard data
├── jellyfin/            # Media server
├── khoj/                # Search data
├── monitoring/          # Monitoring data
├── nestmtx/            # Matrix server
├── ollama-models/      # AI models
├── ollama-webui/       # UI configurations
├── perplexica/         # AI data
├── plex/               # Media server
├── postgres/           # Database storage
├── prometheus/         # Metrics storage
├── proxitok/           # ProxiTok cache
├── reubah/             # Application data
├── searxng/            # Search engine data
└── TEMP/               # Temporary storage
```

## Storage Architecture

```mermaid
graph TD
    subgraph "Node: vanillax-ai"
        A[Local Storage] --> B[/datapool/kubernetes]
        B --> C[PersistentVolumes]
        C --> D[PersistentVolumeClaims]
    end

    subgraph "Applications"
        D --> E[AI Models]
        D --> F[Media Apps]
        D --> G[Databases]
    end

    subgraph "Volume Binding"
        H[StorageClass] --> I[WaitForFirstConsumer]
        I --> J[Node Affinity]
        J --> C
    end
```

## Node Affinity and PVC Binding

```mermaid
sequenceDiagram
    participant App as Application
    participant K8s as Kubernetes Scheduler
    participant PVC as PersistentVolumeClaim
    participant PV as PersistentVolume
    participant Node as Node Storage

    App->>K8s: Create Pod with PVC
    K8s->>PVC: Check storage requirements
    PVC->>PV: Request binding
    PV->>K8s: Check node affinity
    K8s->>Node: Verify storage availability
    Node->>K8s: Confirm availability
    K8s->>App: Schedule pod on node
    PVC->>PV: Bind volume
    PV->>Node: Mount storage
```

## Storage Classes

### Local Storage
```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: local-storage
provisioner: kubernetes.io/no-provisioner
volumeBindingMode: WaitForFirstConsumer
```

### Node Affinity Configuration
```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: app-data-pv
spec:
  nodeAffinity:
    required:
      nodeSelectorTerms:
      - matchExpressions:
        - key: kubernetes.io/hostname
          operator: In
          values:
          - vanillax-ai
```

## Volume Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Created: Create PVC
    Created --> Pending: Wait for Consumer
    Pending --> Binding: Pod Scheduled
    Binding --> Bound: Volume Mounted
    Bound --> [*]: Pod Running
```

## Storage Management

### Directory Preparation
```bash
# Create base directory
mkdir -p /datapool/kubernetes

# Create application directories
for dir in arr comfyui config frigate jellyfin monitoring ollama-models; do
    mkdir -p /datapool/kubernetes/$dir
done

# Set permissions
chown -R 1000:1000 /datapool/kubernetes/*
```

### Volume Validation
```bash
# Check PV status
kubectl get pv -o custom-columns=NAME:.metadata.name,STATUS:.status.phase,NODE:.spec.nodeAffinity.required.nodeSelectorTerms[0].matchExpressions[0].values[0]

# Verify PVC binding
kubectl get pvc -A -o custom-columns=NAMESPACE:.metadata.namespace,NAME:.metadata.name,STATUS:.status.phase,VOLUME:.spec.volumeName
```

## Troubleshooting

### Common Issues

1. **Pending PVCs**
```mermaid
graph TD
    A[PVC Pending] --> B{Check Status}
    B -->|No PV| C[Verify PV exists]
    B -->|No Node| D[Check Node Affinity]
    B -->|Volume Exists| E[Check Binding Mode]
    C --> F[Create PV]
    D --> G[Update Node Labels]
    E --> H[Wait for Pod Creation]
```

2. **Mount Issues**
```bash
# Check mount points
kubectl describe pod <pod-name> -n <namespace>

# Verify directory permissions
ls -la /datapool/kubernetes/<app-directory>

# Check node capacity
df -h /datapool
```

### Volume Recovery
1. Backup data:
```bash
rsync -av /datapool/kubernetes/<app>/ /backup/<app>/
```

2. Recreate PV/PVC:
```bash
kubectl delete pvc <pvc-name> -n <namespace>
kubectl delete pv <pv-name>
kubectl apply -f storage/
```

## Best Practices

1. **Volume Naming**
   - Use consistent naming: `<app>-<type>-{pv|pvc}`
   - Include node affinity in PV names
   - Label volumes for easy identification

2. **Backup Strategy**
   - Regular snapshots of /datapool
   - Application-specific backup procedures
   - Test restore procedures regularly

3. **Monitoring**
   - Set up alerts for storage capacity
   - Monitor PV/PVC binding status
   - Track volume performance metrics 