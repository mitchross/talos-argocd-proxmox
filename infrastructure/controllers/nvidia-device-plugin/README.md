# NVIDIA GPUs on Talos 1.10 — Operator‑Managed Device Plugin (RTX 3090)

This repository uses the NVIDIA GPU Operator to install and manage the NVIDIA Device Plugin. This directory now provides the `RuntimeClass`, optional monitoring `Service`, and a power‑limit DaemonSet for **RTX 3090** on **Talos Linux 1.10**. The standalone Device Plugin DaemonSet is intentionally not applied here to avoid conflicts with the Operator‑managed plugin.

## 🎯 Configuration Summary

- **GPU**: RTX 3090 (Consumer/Gaming GPU)
- **Time Slicing**: ✅ Enabled via GPU Operator (default 10 slices/GPU)
- **Power Limiting**: ✅ Enabled (280W for stability)
- **Talos Version**: 1.10
- **Device Plugin**: Installed and managed by GPU Operator

## 📋 Prerequisites for Talos 1.10

Before deploying, ensure your Talos configuration includes:

### 1. NVIDIA Extensions
```yaml
machine:
  install:
    extensions:
      - image: ghcr.io/siderolabs/nvidia-container-toolkit:535.154.05-v1.14.6
      - image: ghcr.io/siderolabs/nonfree-kmod-nvidia:535.154.05-v1.7.6
```

### 2. Kernel Modules
```yaml
machine:
  kernel:
    modules:
      - name: nvidia
      - name: nvidia_uvm
      - name: nvidia_drm
      - name: nvidia_modeset
```

### 3. Container Runtime Configuration
```yaml
machine:
  files:
    - op: create
      content: |
        [plugins]
          [plugins."io.containerd.cri.v1.runtime"]
            [plugins."io.containerd.cri.v1.runtime".containerd]
              default_runtime_name = "nvidia"
      path: /etc/cri/conf.d/20-customization.part
```

## 🚀 Deployment

### Quick Deploy (recommended order)
```bash
# 1) Node Feature Discovery
kustomize build infrastructure/controllers/node-feature-discovery | kubectl apply -f -

# 2) GPU Operator (manages device plugin and time-slicing)
kustomize build infrastructure/controllers/nvidia-gpu-operator | kubectl apply -f -

# 3) RuntimeClass + power limit (from this folder)
kubectl apply -k infrastructure/controllers/nvidia-device-plugin
```

## 🔍 Verification

### Check Deployment Status
```bash
# GPU Operator components
kubectl get pods -n gpu-operator

# Device Plugin DaemonSet (created by the operator)
kubectl get daemonset -A | grep nvidia-device-plugin

# Verify GPU capacity (should show 1 per RTX 3090)
kubectl describe nodes | grep nvidia.com/gpu
```

### Check Device Plugin Logs
```bash
kubectl logs -n gpu-operator -l app.kubernetes.io/name=nvidia-device-plugin
```

### Check Power Limit Logs
```bash
kubectl logs -n gpu-device-plugin -l app.kubernetes.io/name=nvidia-powerlimit
```

## 🧪 Testing

### Basic GPU Test
```bash
# Use the test pod provided with the GPU Operator setup
kubectl apply -f infrastructure/controllers/nvidia-gpu-operator/test-pod.yaml
kubectl logs -n gpu-operator cuda-vectoradd -f
```

### Manual Test
```bash
kubectl run gpu-test --image=nvcr.io/nvidia/cuda:12.4.1-base-ubuntu22.04 --restart=Never --rm -it --overrides='{"spec":{"runtimeClassName":"nvidia","tolerations":[{"key":"nvidia.com/gpu","operator":"Exists","effect":"NoSchedule"}],"nodeSelector":{"feature.node.kubernetes.io/pci-0300_10de.present":"true"},"containers":[{"name":"gpu-test","image":"nvcr.io/nvidia/cuda:12.4.1-base-ubuntu22.04","resources":{"limits":{"nvidia.com/gpu":"1"}},"command":["nvidia-smi"]}]}}'
```

## ⚡ Power Management for RTX 3090

The RTX 3090 has a default power limit of 350W, which can cause thermal issues in containerized environments. This setup automatically limits power to 280W for optimal stability.

### Power Limit Features
- **Initial Setup**: Sets 280W limit on startup
- **Monitoring**: Checks every 30 minutes and resets if needed
- **Logging**: Detailed logs for troubleshooting
- **Auto-Recovery**: Resets limits if they drift

### Manual Power Check
```bash
# Check current power limits
kubectl run power-check --image=nvcr.io/nvidia/cuda:12.4.1-base-ubuntu22.04 --restart=Never --rm -it --overrides='{"spec":{"runtimeClassName":"nvidia","tolerations":[{"key":"nvidia.com/gpu","operator":"Exists","effect":"NoSchedule"}],"nodeSelector":{"feature.node.kubernetes.io/pci-0300_10de.present":"true"},"containers":[{"name":"power-check","image":"nvcr.io/nvidia/cuda:12.4.1-base-ubuntu22.04","command":["nvidia-smi","--query-gpu=index,name,power.limit,power.draw","--format=csv"]}]}}'
```

## 🔧 Troubleshooting

### Common Issues

1. **No GPU detected**
   ```bash
   # Check if NVIDIA drivers are loaded
   kubectl exec -it <device-plugin-pod> -- lsmod | grep nvidia
   
   # Verify PCI device detection
   kubectl get nodes --show-labels | grep pci-10de
   ```

2. **Power limits not applied**
   ```bash
   # Check power limit pod logs
   kubectl logs -n gpu-device-plugin -l name=nvidia-powerlimit
   
   # Manually verify
   kubectl exec -it <power-pod> -- nvidia-smi -q -d POWER
   ```

3. **Pods stuck in Pending**
   ```bash
   # Check GPU capacity
   kubectl describe node <gpu-node> | grep nvidia.com/gpu
   
   # Check pod events
   kubectl describe pod <stuck-pod>
   ```

### Debug Commands
```bash
# Check GPU nodes
kubectl get nodes -l feature.node.kubernetes.io/pci-0300_10de.present=true

# Check runtime class
kubectl get runtimeclass nvidia

# Test NVIDIA runtime
kubectl run nvidia-debug --image=nvidia/cuda:12.4.1-base-ubuntu22.04 --restart=Never --rm -it --overrides='{"spec":{"runtimeClassName":"nvidia","containers":[{"name":"nvidia-debug","image":"nvidia/cuda:12.4.1-base-ubuntu22.04","command":["nvidia-smi"]}]}}'
```

## 📊 Expected Results

After successful deployment:
- **GPU Capacity**: With time-slicing set to 10, each RTX 3090 shows as `nvidia.com/gpu: 10`
- **Power Limit**: GPUs limited to 280W
- **Resource Sharing**: Pods request slices: `nvidia.com/gpu: "1"` = one slice, `"2"` = two slices
- **Stability**: Better thermal management in Talos environment

## 🏗️ Architecture

```
┌────────────────────────┐
│     GPU Workloads      │
│   (time-sliced reqs)   │
└──────────┬─────────────┘
           │
┌──────────▼─────────────┐
│  NVIDIA Device Plugin  │
│ (managed by Operator)  │
└──────────┬─────────────┘
           │
┌──────────▼─────────────┐
│     NVIDIA GPU Op.     │
│  (time-slicing config) │
└──────────┬─────────────┘
           │
┌──────────▼─────────────┐
│       RTX 3090         │
│     (280W power cap)   │
└────────────────────────┘
```

## 🔐 Security

This deployment follows security best practices:
- ✅ Non-root containers where possible
- ✅ Read-only root filesystem
- ✅ Dropped capabilities
- ✅ Seccomp profiles
- ✅ Resource limits
- ✅ RBAC with minimal permissions

## 📚 References

- [NVIDIA k8s-device-plugin](https://github.com/NVIDIA/k8s-device-plugin)
- [NVIDIA GPU Operator](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/)
- [Talos GPU Guide](https://www.talos.dev/v1.10/advanced/gpu/)
- [RTX 3090 Specifications](https://www.nvidia.com/en-us/geforce/graphics-cards/30-series/rtx-3090/)
- [Talos 1.10 Release Notes](https://github.com/siderolabs/talos/releases/tag/v1.10.0)