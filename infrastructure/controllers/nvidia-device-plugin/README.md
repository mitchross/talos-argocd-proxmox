# NVIDIA GPUs on Talos 1.10 — Standalone Device Plugin (RTX 3090)

This repository uses a **standalone NVIDIA Device Plugin** deployment (without GPU Operator) to provide GPU time-slicing on Talos Linux. This approach avoids known compatibility issues between the NVIDIA GPU Operator and Talos Linux while still enabling time-slicing functionality.

## 🎯 Configuration Summary

- **GPU**: RTX 3090 (Consumer/Gaming GPU)
- **Time Slicing**: ✅ Enabled via standalone device plugin (4 slices/GPU)
- **Power Limiting**: ✅ Enabled (300W for stability with time-slicing)
- **Talos Version**: 1.10
- **Device Plugin**: Standalone deployment (no GPU Operator)

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

### Quick Deploy
```bash
# Deploy standalone device plugin with time-slicing
kubectl apply -k gpu-device-plugin/

# Wait for device plugin to be ready
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=nvidia-device-plugin -n gpu-device-plugin --timeout=300s
```

### Verify Deployment
```bash
# Check all components are running
kubectl get pods -n gpu-device-plugin

# Verify GPU resources (should show 8 total: 4 slices × 2 RTX 3090s)
kubectl describe nodes | grep nvidia.com/gpu
```

## 🔍 Verification

### Check Device Plugin Status
```bash
# Device plugin pods
kubectl get pods -n gpu-device-plugin -l app.kubernetes.io/name=nvidia-device-plugin

# Device plugin logs
kubectl logs -l app.kubernetes.io/name=nvidia-device-plugin -n gpu-device-plugin
```

### Check Power Management
```bash
# Power limit pods
kubectl get pods -n gpu-device-plugin -l app.kubernetes.io/name=nvidia-powerlimit

# Power limit logs
kubectl logs -l app.kubernetes.io/name=nvidia-powerlimit -n gpu-device-plugin
```

### Verify GPU Resources
```bash
# Check total GPU capacity
kubectl get nodes -o json | jq '.items[].status.capacity | select(."nvidia.com/gpu") | ."nvidia.com/gpu"'

# Check allocatable GPUs
kubectl describe nodes | grep -A 5 "nvidia.com/gpu"
```

## 🧪 Testing Time-Slicing

### Deploy Test Pods
```bash
# Test 4 pods sharing a single physical GPU
kubectl apply -f - << EOF
apiVersion: v1
kind: Pod
metadata:
  name: gpu-test-1
  namespace: gpu-device-plugin
spec:
  restartPolicy: Never
  containers:
  - name: cuda-test
    image: nvcr.io/nvidia/k8s/cuda-sample:vectoradd-cuda11.7.1-ubuntu20.04
    resources:
      limits:
        nvidia.com/gpu: "1"
  runtimeClassName: nvidia
---
apiVersion: v1
kind: Pod
metadata:
  name: gpu-test-2
  namespace: gpu-device-plugin
spec:
  restartPolicy: Never
  containers:
  - name: cuda-test
    image: nvcr.io/nvidia/k8s/cuda-sample:vectoradd-cuda11.7.1-ubuntu20.04
    resources:
      limits:
        nvidia.com/gpu: "1"
  runtimeClassName: nvidia
---
apiVersion: v1
kind: Pod
metadata:
  name: gpu-test-3
  namespace: gpu-device-plugin
spec:
  restartPolicy: Never
  containers:
  - name: cuda-test
    image: nvcr.io/nvidia/k8s/cuda-sample:vectoradd-cuda11.7.1-ubuntu20.04
    resources:
      limits:
        nvidia.com/gpu: "1"
  runtimeClassName: nvidia
---
apiVersion: v1
kind: Pod
metadata:
  name: gpu-test-4
  namespace: gpu-device-plugin
spec:
  restartPolicy: Never
  containers:
  - name: cuda-test
    image: nvcr.io/nvidia/k8s/cuda-sample:vectoradd-cuda11.7.1-ubuntu20.04
    resources:
      limits:
        nvidia.com/gpu: "1"
  runtimeClassName: nvidia
EOF
```

### Check Test Results
```bash
# All 4 pods should be running simultaneously
kubectl get pods -n gpu-device-plugin | grep gpu-test

# Check logs to verify successful execution
kubectl logs gpu-test-1 -n gpu-device-plugin
kubectl logs gpu-test-2 -n gpu-device-plugin
kubectl logs gpu-test-3 -n gpu-device-plugin
kubectl logs gpu-test-4 -n gpu-device-plugin

# Clean up
kubectl delete pods gpu-test-1 gpu-test-2 gpu-test-3 gpu-test-4 -n gpu-device-plugin
```

## ⚡ Power Management for RTX 3090

The RTX 3090 has a default power limit of 350W, which can cause thermal issues in containerized environments. This setup automatically limits power to 300W for optimal stability with time-slicing workloads.

### Power Limit Features
- **Initial Setup**: Sets 300W limit on startup
- **Persistence Mode**: Enables GPU persistence for better performance
- **Monitoring**: Checks every 30 minutes and resets if needed
- **Utilization Tracking**: Shows GPU usage for time-slicing monitoring
- **Auto-Recovery**: Resets limits if they drift

### Manual Power Check
```bash
# Get power limit pod name
POWER_POD=$(kubectl get pods -n gpu-device-plugin -l app.kubernetes.io/name=nvidia-powerlimit -o jsonpath='{.items[0].metadata.name}')

# Check current power limits and utilization
kubectl exec -it $POWER_POD -n gpu-device-plugin -- nvidia-smi --query-gpu=index,name,power.limit,power.draw,utilization.gpu --format=csv
```

## 🔧 Troubleshooting

### Common Issues

1. **No GPU resources available**
   ```bash
   # Check if device plugin is running
   kubectl get pods -n gpu-device-plugin -l app.kubernetes.io/name=nvidia-device-plugin
   
   # Check device plugin logs
   kubectl logs -l app.kubernetes.io/name=nvidia-device-plugin -n gpu-device-plugin
   
   # Verify NVIDIA drivers on nodes
   kubectl get nodes -l feature.node.kubernetes.io/pci-0300_10de.present=true
   ```

2. **Time-slicing not working**
   ```bash
   # Check device plugin configuration
   kubectl get configmap nvidia-device-plugin-config -n gpu-device-plugin -o yaml
   
   # Verify config is loaded in device plugin
   kubectl logs -l app.kubernetes.io/name=nvidia-device-plugin -n gpu-device-plugin | grep -i "time.*slic"
   
   # Check if multiple pods can run on same GPU
   kubectl get pods -n gpu-device-plugin -o wide
   ```

3. **Power limits not applied**
   ```bash
   # Check power limit pod logs
   kubectl logs -l app.kubernetes.io/name=nvidia-powerlimit -n gpu-device-plugin
   
   # Manually verify power settings
   POWER_POD=$(kubectl get pods -n gpu-device-plugin -l app.kubernetes.io/name=nvidia-powerlimit -o jsonpath='{.items[0].metadata.name}')
   kubectl exec -it $POWER_POD -n gpu-device-plugin -- nvidia-smi -q -d POWER
   ```

4. **Pods stuck in Pending**
   ```bash
   # Check GPU capacity vs requests
   kubectl describe nodes | grep -A 10 "Allocated resources"
   
   # Check pod events
   kubectl describe pod <stuck-pod>
   
   # Verify runtime class
   kubectl get runtimeclass nvidia
   ```

### Debug Commands
```bash
# Check all GPU-related resources
kubectl get all -n gpu-device-plugin

# Test NVIDIA runtime manually
kubectl run nvidia-debug --image=nvidia/cuda:12.4.1-base-ubuntu22.04 --restart=Never --rm -it --overrides='{"spec":{"runtimeClassName":"nvidia","containers":[{"name":"nvidia-debug","image":"nvidia/cuda:12.4.1-base-ubuntu22.04","command":["nvidia-smi"]}]}}'

# Check device plugin socket
kubectl exec -it <device-plugin-pod> -n gpu-device-plugin -- ls -la /var/lib/kubelet/device-plugins/
```

## 📊 Expected Results

After successful deployment:
- **GPU Capacity**: Each RTX 3090 shows as `nvidia.com/gpu: 4` (4 time slices)
- **Total Available**: `nvidia.com/gpu: 8` (4 slices × 2 RTX 3090s)
- **Power Limit**: GPUs limited to 300W for stability
- **Resource Sharing**: Multiple pods can request `nvidia.com/gpu: "1"` and run on same physical GPU
- **Thermal Management**: Better stability in containerized environments

## 🗃️ Architecture

```
┌────────────────────────────┐
│     GPU Workloads          │
│   (time-sliced requests)   │
└───────────┬────────────────┘
            │
┌───────────▼────────────────┐
│  NVIDIA Device Plugin      │
│    (standalone)            │
└───────────┬────────────────┘
            │
┌───────────▼────────────────┐
│   Time-Slicing Config      │
│   (4 slices per GPU)       │
└───────────┬────────────────┘
            │
┌───────────▼────────────────┐
│       RTX 3090             │
│     (300W power cap)       │
└────────────────────────────┘
```

## 🔒 Security

This deployment follows security best practices:
- ✅ Non-root containers where possible
- ✅ Read-only root filesystem
- ✅ Dropped capabilities
- ✅ Seccomp profiles
- ✅ Resource limits
- ✅ RBAC with minimal permissions
- ✅ Privileged access only where required (device plugin socket)

## 📚 References

- [NVIDIA k8s-device-plugin](https://github.com/NVIDIA/k8s-device-plugin)
- [Time-Slicing Configuration](https://github.com/NVIDIA/k8s-device-plugin?tab=readme-ov-file#shared-access-to-gpus)
- [Talos GPU Guide](https://www.talos.dev/v1.10/advanced/gpu/)
- [RTX 3090 Specifications](https://www.nvidia.com/en-us/geforce/graphics-cards/30-series/rtx-3090/)
- [Talos GPU Operator Issues](https://github.com/siderolabs/talos/issues/9014)

## ⚠️ Why Not GPU Operator?

This setup uses a standalone device plugin instead of the NVIDIA GPU Operator due to known compatibility issues between the GPU Operator and Talos Linux:

- **Driver Management Conflicts**: GPU Operator expects to manage drivers via DaemonSets, but Talos manages drivers through system extensions
- **Container Runtime Issues**: Different assumptions about containerd configuration
- **File System Limitations**: Talos's immutable OS design conflicts with GPU Operator's driver installation approach

The standalone approach provides the same time-slicing functionality while being fully compatible with Talos Linux architecture.