# ComfyUI on Kubernetes (Talos) with ArgoCD

This directory contains Kubernetes manifests to deploy ComfyUI with GPU support on Talos Linux via ArgoCD.

## Files Structure

- `namespace.yaml` - ComfyUI namespace
- `pvc.yaml` - Persistent Volume Claim for models and outputs (180GB, Longhorn single replica)
- `configmap.yaml` - Configuration for model paths
- `deployment.yaml` - Main ComfyUI deployment with GPU support
- `service.yaml` - ClusterIP and NodePort services
- `httproute.yaml` - HTTPRoute configuration for Gateway API
- `kustomization.yaml` - Kustomize configuration
- `setup-comfyui.sh` - Post-deployment setup script for models and workflows
- `README.md` - This documentation

## Prerequisites for Talos

1. **GPU Support**: Ensure your Talos cluster has GPU support enabled
2. **Node Labels**: Label your GPU nodes with:
   ```bash
   kubectl label nodes <your-gpu-node> accelerator=nvidia-gpu
   ```
3. **Storage**: Longhorn configured (single replica for space efficiency)
4. **Gateway API**: Ensure Gateway API is installed and configured in your cluster
5. **ArgoCD**: This setup assumes deployment via ArgoCD

## Deployment Workflow

### 1. ArgoCD Deployment
ArgoCD will automatically deploy the manifests. Ensure your ArgoCD application points to this directory.

### 2. Post-Deployment Setup (Models & Workflows)
After ArgoCD deploys ComfyUI, run the setup script to install models and custom nodes:

```bash
# Navigate to the ComfyUI directory
cd my-apps/ai/comfyui

# Make the script executable
chmod +x setup-comfyui.sh

# Run post-deployment setup
./setup-comfyui.sh
```

### 3. Manual Deployment (Alternative)
If you need to deploy manually without ArgoCD:

```bash
# Apply all manifests using kustomize
kubectl apply -k .

# Then run the setup script
./setup-comfyui.sh
```

## Features

### Container Image
- Uses `yanwk/comfyui-boot:latest` - optimized for GPU workloads
- Includes ComfyUI with CUDA support

### Pre-installed Components (via setup script)
- **ComfyUI Manager** - Easy node and model management
- **Essential Custom Nodes**:
  - ComfyUI ControlNet Auxiliary
  - ComfyUI Essentials
  - Custom Scripts
  - RGThree Comfy
  - Flux-specific nodes (FluxTrainer, GGUF)
  - WAS Node Suite & Efficiency Nodes

### Pre-downloaded Models (via setup script)
- **Flux Dev BF16 & FP8** - Latest 12B parameter models for exceptional quality
- **CyberRealistic Pony v11** - Popular photorealistic model
- **SDXL Base 1.0** - Stable foundation model
- **Flux & SDXL VAEs** - High-quality decoders
- **Flux ControlNet** - Canny and Depth control
- **Traditional ControlNet** - Canny and OpenPose
- **RealESRGAN Upscalers** - General and Anime variants
- **CyberRealistic Embeddings** - Optimized prompt tokens

### Pre-configured Workflows
- **Flux Dev Workflow** - High-quality photorealistic generation
- **CyberRealistic Pony Workflow** - Versatile realistic content

## Resource Requirements

- **CPU**: 2-8 cores
- **Memory**: 8-32 GB
- **GPU**: 1x NVIDIA GPU (optimized for 24GB VRAM)
- **Storage**: 180GB Longhorn (single replica for efficiency)

## Access Methods

### 1. HTTPRoute (Primary - Domain Access)
- URL: `https://comfyui.vanillax.me`
- Uses Gateway API with `gateway-internal`

### 2. NodePort (Direct Access)
```bash
# Access via node IP on port 30188
http://<NODE_IP>:30188
```

### 3. Port Forward (Local Development)
```bash
kubectl port-forward -n comfyui service/comfyui-service 8188:8188
# Access at: http://localhost:8188
```

## Configuration

### Storage (Longhorn)
- Single replica for space efficiency
- 180GB capacity for models and outputs
- Persistent across pod restarts

### Resource Limits
Optimized for 24GB GPU systems:
```yaml
resources:
  requests:
    memory: "8Gi"
    cpu: "2"
    nvidia.com/gpu: 1
  limits:
    memory: "32Gi"
    cpu: "8"
    nvidia.com/gpu: 1
```

### Gateway Configuration
HTTPRoute configured for:
- Gateway: `gateway-internal` in `gateway` namespace
- Domain: `comfyui.vanillax.me`

## Monitoring

Check deployment status:
```bash
kubectl get pods -n comfyui
kubectl logs -n comfyui deployment/comfyui
kubectl describe pod -n comfyui <pod-name>
kubectl get httproute -n comfyui
```

## Troubleshooting

1. **Pod not starting**: Check GPU node labels and availability
2. **Storage issues**: Verify Longhorn status and PVC binding
3. **Model download issues**: Check pod logs during setup script execution
4. **GPU not detected**: Ensure NVIDIA device plugin is running
5. **HTTPRoute not working**: Check Gateway API installation and gateway configuration
6. **ArgoCD sync issues**: Verify kustomization.yaml and resource files

## Customization

### Adding Models
Connect to the pod and download additional models:
```bash
POD_NAME=$(kubectl get pods -n comfyui -l app=comfyui -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n comfyui $POD_NAME -- bash
```

### Installing Custom Nodes
Use ComfyUI Manager web interface or install manually:
```bash
kubectl exec -n comfyui $POD_NAME -- bash -c "cd /opt/ComfyUI/custom_nodes && git clone <repo-url>"
```

### Updating Models via Script
Re-run the setup script to add new models:
```bash
./setup-comfyui.sh
```

## ArgoCD Integration

### Application Configuration
Ensure your ArgoCD application configuration includes:
```yaml
spec:
  source:
    path: my-apps/ai/comfyui
    repoURL: <your-repo>
    targetRevision: HEAD
  destination:
    namespace: comfyui
    server: https://kubernetes.default.svc
```

### Sync Strategy
- **Automatic Sync**: Recommended for seamless updates
- **Manual Sync**: For controlled deployments

## Notes

- **First startup**: Takes time for model downloads (~50GB+)
- **ComfyUI Manager**: Provides easy model and node management via web UI
- **Model persistence**: All models persist in Longhorn storage across restarts
- **Setup script**: Only handles post-deployment configuration, not manifest deployment
- **ArgoCD friendly**: All manifests are properly structured for GitOps workflows 