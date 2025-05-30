# ComfyUI on Kubernetes (Talos)

This directory contains Kubernetes manifests to deploy ComfyUI with GPU support on Talos Linux.

## Files Structure

- `namespace.yaml` - ComfyUI namespace
- `pvc.yaml` - Persistent Volume Claim for models and outputs (100GB)
- `configmap.yaml` - Configuration for model paths
- `deployment.yaml` - Main ComfyUI deployment with GPU support
- `service.yaml` - ClusterIP and NodePort services
- `httproute.yaml` - HTTPRoute configuration for Gateway API
- `kustomization.yaml` - Kustomize configuration
- `setup-comfyui.sh` - Automated setup script
- `comfyui-manifests.yaml` - Single file with all manifests (for reference)

## Prerequisites for Talos

1. **GPU Support**: Ensure your Talos cluster has GPU support enabled
2. **Node Labels**: Label your GPU nodes with:
   ```bash
   kubectl label nodes <your-gpu-node> accelerator=nvidia-gpu
   ```
3. **Storage**: Configure appropriate storage class (default: `local-path`)
4. **Gateway API**: Ensure Gateway API is installed and configured in your cluster

## Quick Deployment

### Option 1: Using the Setup Script (Recommended)

```bash
# Make the script executable
chmod +x setup-comfyui.sh

# Run the complete setup
./setup-comfyui.sh
```

### Option 2: Manual Deployment

```bash
# Apply all manifests using kustomize
kubectl apply -k .

# Or apply individual files
kubectl apply -f namespace.yaml
kubectl apply -f pvc.yaml
kubectl apply -f configmap.yaml
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl apply -f httproute.yaml
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

### Pre-downloaded Models
- **SDXL Base 1.0** - Main diffusion model
- **SDXL VAE** - Variational autoencoder
- **ControlNet Models** - Canny and OpenPose
- **RealESRGAN 4x** - Upscaling model

### Default Workflow
- Basic SDXL generation workflow
- Located at: `/opt/ComfyUI/user/default/workflows/basic_sdxl.json`

## Resource Requirements

- **CPU**: 2-4 cores
- **Memory**: 8-16 GB
- **GPU**: 1x NVIDIA GPU
- **Storage**: 100GB for models and outputs

## Access Methods

### 1. NodePort (Direct Access)
```bash
# Access via node IP on port 30188
http://<NODE_IP>:30188
```

### 2. Port Forward (Local Development)
```bash
kubectl port-forward -n comfyui service/comfyui-service 8188:8188
# Access at: http://localhost:8188
```

### 3. HTTPRoute (Domain Access)
Update `httproute.yaml` with your domain and gateway configuration:
```yaml
hostnames:
- comfyui.your-domain.com
parentRefs:
- name: your-gateway-name
  namespace: gateway-system
```
Then access via: `http://comfyui.your-domain.com`

## Configuration

### Gateway Configuration
Update the HTTPRoute in `httproute.yaml`:
```yaml
spec:
  parentRefs:
  - name: your-gateway-name
    namespace: gateway-system
  hostnames:
  - comfyui.your-domain.com
```

### Storage Class
Default uses `local-path`. Update in `pvc.yaml`:
```yaml
storageClassName: your-storage-class
```

### Resource Limits
Adjust in `deployment.yaml`:
```yaml
resources:
  requests:
    memory: "8Gi"
    cpu: "2"
    nvidia.com/gpu: 1
  limits:
    memory: "16Gi"
    cpu: "4"
    nvidia.com/gpu: 1
```

### Node Selection
Update node selector in `deployment.yaml`:
```yaml
nodeSelector:
  accelerator: nvidia-gpu
```

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
2. **Storage issues**: Verify storage class and PVC status
3. **Model download issues**: Check pod logs for download progress
4. **GPU not detected**: Ensure NVIDIA device plugin is running
5. **HTTPRoute not working**: Check Gateway API installation and gateway configuration

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

## Notes

- First startup takes time for model downloads
- ComfyUI Manager provides easy model and node management
- Models persist in the PVC across pod restarts
- The setup script handles initial configuration and model downloads
- HTTPRoute requires Gateway API to be installed in your cluster 