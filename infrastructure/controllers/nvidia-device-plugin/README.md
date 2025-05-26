# NVIDIA Device Plugin for Kubernetes with Time Slicing

This directory contains a production-ready deployment of the NVIDIA Device Plugin for Kubernetes with CUDA time slicing support, optimized for Talos Linux.

## 🚀 Features

- **Latest Version**: NVIDIA Device Plugin v0.17.2
- **Time Slicing**: 10x GPU sharing capability
- **Production Ready**: Complete RBAC, monitoring, health checks
- **Security Hardened**: Non-root containers, read-only filesystem
- **Talos Compatible**: Optimized for Talos Linux environments
- **Monitoring**: Prometheus metrics integration

## 📋 Prerequisites

Before deploying, ensure:

1. **Talos Linux** with NVIDIA extensions installed:
   - `nvidia-container-toolkit-production`
   - `nonfree-kmod-nvidia-production`

2. **Kernel modules loaded** (via Talos machine config):
   ```yaml
   machine:
     kernel:
       modules:
         - name: nvidia
         - name: nvidia_uvm
         - name: nvidia_drm
         - name: nvidia_modeset
   ```

3. **Container runtime configured** for NVIDIA:
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

## 🛠️ Deployment

### Quick Deploy
```bash
kubectl apply -k infrastructure/controllers/nvidia-device-plugin/
```

### Verify Deployment
```bash
# Check DaemonSet status
kubectl get daemonset -n gpu-device-plugin

# Check pod status
kubectl get pods -n gpu-device-plugin

# Verify GPU capacity (should show 10x multiplication)
kubectl describe nodes | grep nvidia.com/gpu

# Check device plugin logs
kubectl logs -n gpu-device-plugin -l app.kubernetes.io/name=nvidia-device-plugin
```

## 🧪 Testing

### Basic GPU Test
```bash
# Uncomment nvidia-test-pod.yaml in kustomization.yaml, then:
kubectl apply -k infrastructure/controllers/nvidia-device-plugin/
kubectl logs -n gpu-device-plugin nvidia-test
```

### Time Slicing Test
```bash
# Deploy multiple workloads to test sharing
for i in {1..3}; do
  kubectl run gpu-test-$i \
    --image=nvcr.io/nvidia/cuda:12.4.1-base-ubuntu22.04 \
    --restart=Never --rm -it \
    --overrides='{"spec":{"runtimeClassName":"nvidia","tolerations":[{"key":"nvidia.com/gpu","operator":"Exists","effect":"NoSchedule"}],"nodeSelector":{"feature.node.kubernetes.io/pci-10de.present":"true"}}}' \
    --limits=nvidia.com/gpu=1 \
    -- nvidia-smi
done
```

## 📊 Configuration

### Time Slicing Settings
Edit `config.yaml` to modify time slicing behavior:

```yaml
sharing:
  timeSlicing:
    renameByDefault: false          # Keep nvidia.com/gpu name
    failRequestsGreaterThanOne: true # Prevent resource hogging
    resources:
    - name: nvidia.com/gpu
      replicas: 10                  # Number of shared instances per GPU
```

### Common Configurations

| Replicas | Use Case | Description |
|----------|----------|-------------|
| 2-5 | Development | Light sharing for dev workloads |
| 10 | Production | Balanced sharing for mixed workloads |
| 20+ | CI/CD | High sharing for short-running jobs |

## 🔧 Troubleshooting

### Common Issues

1. **No GPU capacity shown**
   ```bash
   # Check if device plugin pods are running
   kubectl get pods -n gpu-device-plugin
   
   # Check logs for errors
   kubectl logs -n gpu-device-plugin -l app.kubernetes.io/name=nvidia-device-plugin
   ```

2. **Pods stuck in Pending**
   ```bash
   # Check node has NVIDIA GPUs
   kubectl describe node <node-name> | grep nvidia.com/gpu
   
   # Verify node selector matches
   kubectl get nodes --show-labels | grep pci-10de
   ```

3. **Container runtime errors**
   ```bash
   # Check if NVIDIA runtime is configured
   kubectl describe pod <failing-pod>
   
   # Verify runtime class exists
   kubectl get runtimeclass nvidia
   ```

### Debug Commands

```bash
# Check GPU detection on node
kubectl get pcidevices -n <node> | grep NVIDIA

# Verify kernel modules
kubectl exec -it <device-plugin-pod> -- lsmod | grep nvidia

# Test NVIDIA runtime
kubectl run nvidia-debug --image=nvidia/cuda:12.4.1-base-ubuntu22.04 \
  --restart=Never --rm -it \
  --overrides='{"spec":{"runtimeClassName":"nvidia"}}' \
  -- nvidia-smi
```

## 📈 Monitoring

The device plugin exposes Prometheus metrics on port 2112:

- **Endpoint**: `http://<pod-ip>:2112/metrics`
- **Service**: `nvidia-device-plugin-metrics.gpu-device-plugin.svc.cluster.local:2112`
- **Health Check**: `http://<pod-ip>:2112/health`

### Grafana Dashboard

Monitor GPU utilization and time slicing effectiveness:
- Device plugin health and restarts
- GPU allocation vs availability
- Time slicing efficiency metrics

## 🔒 Security

This deployment follows security best practices:

- ✅ Non-root containers (UID 65534)
- ✅ Read-only root filesystem
- ✅ Dropped all capabilities
- ✅ Seccomp profile enabled
- ✅ Resource limits enforced
- ✅ RBAC with minimal permissions

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   GPU Workload  │    │   GPU Workload   │    │   GPU Workload  │
│ (nvidia.com/gpu │    │ (nvidia.com/gpu  │    │ (nvidia.com/gpu │
│      = 1)       │    │      = 1)        │    │      = 1)       │
└─────────┬───────┘    └─────────┬────────┘    └─────────┬───────┘
          │                      │                       │
          └──────────────────────┼───────────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   NVIDIA Device Plugin  │
                    │   (Time Slicing: 10x)   │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │     Physical GPU        │
                    │   (1 GPU → 10 shares)   │
                    └─────────────────────────┘
```

## 📚 References

- [NVIDIA k8s-device-plugin](https://github.com/NVIDIA/k8s-device-plugin)
- [Talos GPU Workloads Guide](https://www.siderolabs.com/blog/ai-workloads-on-talos-linux/)
- [CUDA Time Slicing Documentation](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/gpu-sharing.html) 