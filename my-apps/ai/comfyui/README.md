````markdown
# ComfyUI on Kubernetes (Talos) with ArgoCD

This directory contains Kubernetes manifests to deploy ComfyUI with GPU support on Talos Linux via ArgoCD. The setup leverages the built-in, automated setup process of the `yanwk/comfyui-boot` container image and matches the Docker reference implementation.

## File Structure

- `namespace.yaml` - ComfyUI namespace
- `pvc.yaml` - Multiple Persistent Volume Claims for organized storage
- `deployment.yaml` - Main ComfyUI deployment with GPU support
- `service.yaml` - ClusterIP service with named port for HTTPRoute
- `httproute.yaml` - HTTPRoute configuration for Gateway API
- `externalsecret.yaml` - External secret for Hugging Face integration
- `kustomization.yaml` - Kustomize configuration
- `README.md` - This documentation

## Storage Organization

Based on the Docker reference implementation, storage is organized as follows:

- `comfyui-storage` (50Gi) - Main application data at `/root`
- `comfyui-models` (200Gi) - Models storage at `/root/ComfyUI/models`
- `comfyui-hf-cache` (100Gi) - Hugging Face cache at `/root/.cache/huggingface/hub`
- `comfyui-torch-cache` (50Gi) - PyTorch cache at `/root/.cache/torch/hub`
- `comfyui-input` (20Gi) - Input files at `/root/ComfyUI/input`
- `comfyui-output` (100Gi) - Generated outputs at `/root/ComfyUI/output`
- `comfyui-workflows` (5Gi) - Workflows at `/root/ComfyUI/user/default/workflows`

## Prerequisites for Talos

1.  **GPU Support**: Ensure your Talos cluster has GPU support enabled.
2.  **Node Labels**: Label your GPU nodes with:
   ```bash
   kubectl label nodes <your-gpu-node> feature.node.kubernetes.io/pci-0300_10de.present="true"
   ```
3.  **Storage**: Longhorn configured for persistent storage.
4.  **Gateway API**: Ensure Gateway API is installed and configured in your cluster.
5.  **ArgoCD**: This setup assumes deployment via ArgoCD.

## Deployment Workflow

### Automated Setup via Container Image
This deployment is fully automated and relies on the `entrypoint.sh` script within the `yanwk/comfyui-boot` image.

1.  **Persistent Volume**: The `deployment.yaml` mounts a Persistent Volume to the `/root` directory inside the container.
2.  **First-Time Setup**: On the very first run, the image's entrypoint script will automatically clone the ComfyUI repository, download a comprehensive set of custom nodes, and download default models into the `/root` directory on your persistent storage.
3.  **Completion Marker**: Once the setup is complete, the script creates a `.download-complete` file in the `/root` directory.
4.  **Subsequent Runs**: On all subsequent starts, the script sees the `.download-complete` file and skips straight to launching the ComfyUI server.

This means the large download only happens once. All data persists across pod restarts and image upgrades. There are no manual setup steps required.

### Manual Deployment (Alternative)
If you need to deploy manually without ArgoCD:
```bash
# Apply all manifests using kustomize
kubectl apply -k .
```
The container's entrypoint will handle the setup automatically upon pod creation.

## Features

### Container Image
- Uses `yanwk/comfyui-boot:cu129-megapak` - an all-in-one image optimized for GPU workloads.
- Includes ComfyUI, Python 3.12, CUDA 12.9, and all necessary dependencies.
- Optimized for RTX 40 series and newer GPUs with fast loading and PyTorch cross-attention.

### CLI Arguments
The deployment uses optimized CLI arguments:
- `--fast` - Optimized for RTX 40 series and newer GPUs
- `--use-pytorch-cross-attention` - Disable xFormers, recommended for Blackwell GPUs
- `--listen 0.0.0.0 --port 8188` - Network configuration for Kubernetes

### Hugging Face Integration
- Automatic token injection via ExternalSecret from 1Password
- Cached models and transformers stored in dedicated volumes
- Environment variable `HF_HOME` properly configured

### Fully Automated Setup
- The container's internal entrypoint handles all downloads and setup.
- All assets are stored on a persistent volume, so they survive pod restarts and image upgrades.

### Pre-installed & Downloaded Components
The image's setup script automatically provides:
- **ComfyUI Manager** - For easy node and model management from the UI.
- **A wide range of essential Custom Nodes** for image generation, video, control, and more.
- **Default Models**, including checkpoints, VAEs, upscale models, and embeddings to get started immediately. 