---
applies_to:
  - "my-apps/ai/**"
  - "**/*gpu*"
  - "**/*nvidia*"
---

# GPU Workload Instructions

## Overview
This cluster supports NVIDIA GPU workloads using Talos system extensions and the NVIDIA GPU Operator.

## GPU Node Configuration
GPU nodes are identified by:
- Node label: `feature.node.kubernetes.io/pci-0300_10de.present: "true"`
- Node type label: `node-type: gpu-worker`
- NVIDIA system extensions in Talos configuration

## GPU Workload Pattern

### Required Deployment Configuration
```yaml
spec:
  template:
    spec:
      # GPU node selection
      nodeSelector:
        feature.node.kubernetes.io/pci-0300_10de.present: "true"
      
      # NVIDIA container runtime
      runtimeClassName: nvidia
      
      # Priority for GPU workloads
      priorityClassName: gpu-workload-preemptible
      
      # Tolerations for GPU nodes
      tolerations:
      - key: nvidia.com/gpu
        operator: Exists
        effect: NoSchedule
      - key: "gpu"
        operator: "Equal"
        value: "true"
        effect: "NoSchedule"
      
      containers:
      - name: app
        resources:
          requests:
            nvidia.com/gpu: "1"
          limits:
            nvidia.com/gpu: "1"
```

## Storage Patterns for AI Workloads

### Model Storage
AI applications typically need persistent storage for models:
```yaml
# pvc.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: app-models
spec:
  accessModes: ["ReadWriteOnce"]
  resources:
    requests:
      storage: 100Gi
  storageClassName: longhorn

# deployment.yaml volumeMounts
volumeMounts:
- name: models
  mountPath: /models  # or /root for some containers
```

### Common Mount Points
- `/models`: Model storage (Ollama, ComfyUI)
- `/root`: Application data and models (ComfyUI)
- `/data`: General application data
- `/output`: Generated content storage

## Probes for AI Workloads
AI containers often have long startup times due to model loading:

```yaml
readinessProbe:
  httpGet:
    path: /
    port: 8080
  initialDelaySeconds: 300  # Increased for model loading
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 6

livenessProbe:
  httpGet:
    path: /
    port: 8080  
  initialDelaySeconds: 1500  # Very long for large model downloads
  periodSeconds: 30
  timeoutSeconds: 10
  failureThreshold: 3
```

## Resource Requirements

### Memory Considerations
- GPU workloads are memory-intensive
- Request sufficient system RAM alongside GPU memory
- Example for large models:
```yaml
resources:
  requests:
    memory: "8Gi"
    cpu: "2"
    nvidia.com/gpu: "1"
  limits:
    memory: "24Gi"
    cpu: "8"
    nvidia.com/gpu: "1"
```

### GPU Sharing
- Current setup: 1 GPU per workload (no sharing)
- For GPU sharing, consider NVIDIA MPS or time-slicing
- Monitor GPU utilization with DCGM exporter

## AI Application Examples

### ComfyUI (Stable Diffusion)
- Image: `yanwk/comfyui-boot:cu126-megapak-*`
- Port: 8188
- Mount: `/root` for models and outputs
- Very long startup times for model downloads

### Ollama (LLM)
- Image: `ollama/ollama:latest`
- Port: 11434
- Mount: `/root/.ollama` for models
- API-based interaction

### Khoj (AI Assistant)
- Image: `ghcr.io/khoj-ai/khoj:latest`
- Port: 42110
- Mount: `/root/.khoj` for data

## Web Access for AI Apps
AI applications typically expose web interfaces:

```yaml
# service.yaml
spec:
  ports:
    - name: http  # REQUIRED for HTTPRoute
      port: 8080
      targetPort: 8080

# httproute.yaml
spec:
  parentRefs:
    - name: gateway-internal
      namespace: gateway
  hostnames:
  - "myapp.vanillax.me"
```

## Monitoring GPU Usage
- GPU metrics via DCGM exporter
- Grafana dashboards for GPU utilization
- Prometheus alerts for GPU issues

## Troubleshooting GPU Workloads

### Common Issues
```bash
# Check GPU node labels
kubectl get nodes -l feature.node.kubernetes.io/pci-0300_10de.present=true

# Verify GPU Operator pods
kubectl get pods -n gpu-operator

# Check NVIDIA device plugin
kubectl get pods -n kube-system -l app=nvidia-device-plugin-daemonset

# Verify GPU allocation on node
kubectl describe node <gpu-node-name> | grep -A 10 "Allocated resources"
```

### GPU Not Available
1. Verify Talos system extensions for NVIDIA
2. Check GPU Operator installation
3. Confirm node labels are present
4. Validate container runtime configuration

## Best Practices
- ✅ Always specify GPU resource requests and limits
- ✅ Use appropriate probe timeouts for model loading
- ✅ Mount persistent storage for models
- ✅ Monitor GPU utilization
- ❌ Don't assume fast startup times
- ❌ Don't share GPUs without proper configuration