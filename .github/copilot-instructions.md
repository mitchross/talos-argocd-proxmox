# GitHub Copilot Instructions for k3s-argocd-proxmox

## Project Overview

This is a **production-grade GitOps Kubernetes cluster** running on Talos OS with self-managing ArgoCD. The key differentiator is that ArgoCD manages its own configuration and automatically discovers applications through directory structure - no manual Application manifests needed.

**Tech Stack**: Talos OS + K3s + ArgoCD + Cilium + Gateway API + Longhorn + 1Password + GPU support

## How This Project Works

### The GitOps Self-Management Pattern
```
Manual Bootstrap → ArgoCD → Root App → ApplicationSets → Auto-discovered Apps
```

1. **Bootstrap once**: Apply ArgoCD manifests manually
2. **Root app triggers**: Points ArgoCD to scan `infrastructure/controllers/argocd/apps/`
3. **ApplicationSets discover**: Three ApplicationSets scan for directories and auto-create Applications
4. **Everything else is automatic**: Add directory + `kustomization.yaml` = deployed app

### Critical Understanding: Directory = Application
```
my-apps/ai/ollama/          → ArgoCD Application "ollama"
infrastructure/storage/longhorn/ → ArgoCD Application "longhorn"  
monitoring/prometheus-stack/    → ArgoCD Application "prometheus-stack"
```

## Essential Commands for This Project

### Talos Cluster Management
```bash
# Node health check
talosctl health --nodes <node-ip>

# Apply config changes (for Talos settings)
talosctl apply-config --nodes <node-ip> --file iac/talos/clusterconfig/<node>.yaml

# Upgrade nodes (for Talos version/extensions changes)
INSTALLER_URL=$(talhelper genurl installer -c iac/talos/talconfig.yaml -n "<node-name>")
talosctl upgrade --nodes "<node-ip>" --image "$INSTALLER_URL"
```

### ArgoCD Bootstrap (Critical Sequence)
```bash
# EXACT order - race conditions exist
kustomize build infrastructure/controllers/argocd --enable-helm | kubectl apply -f -
kubectl wait --for condition=established --timeout=60s crd/applications.argoproj.io
kubectl wait --for=condition=Available deployment/argocd-server -n argocd --timeout=300s
kubectl apply -f infrastructure/controllers/argocd/root.yaml
```

### Emergency ArgoCD Reset
```bash
# Remove finalizers and reset all applications
kubectl get applications -n argocd -o name | xargs -I{} kubectl patch {} -n argocd --type json -p '[{"op": "remove","path": "/metadata/finalizers"}]'
kubectl delete applications --all -n argocd
```

## Quick Development Patterns

### Adding New Applications (The Easy Way)
1. **Pick category**: `my-apps/ai/`, `my-apps/media/`, etc.
2. **Create directory**: `my-apps/category/app-name/`
3. **Add basic files**: `namespace.yaml`, `kustomization.yaml`, deployment files
4. **Git commit**: ArgoCD discovers and deploys automatically

**That's it!** No ArgoCD Application manifests needed.

### Web-Accessible Apps Pattern
For apps that need web access, your Service MUST have a named port:
```yaml
# service.yaml
spec:
  ports:
    - name: http        # CRITICAL - HTTPRoute fails silently without this
      port: 8080
```

Then add `httproute.yaml` pointing to Gateway API (not Ingress).

### GPU Apps Pattern
Reference `my-apps/ai/comfyui/` for complete GPU workload:
- `nodeSelector: feature.node.kubernetes.io/pci-0300_10de.present: "true"`
- `runtimeClassName: nvidia`
- `tolerations` for GPU nodes
- `nvidia.com/gpu: "1"` in resources

### Helm + Kustomize Pattern
See `infrastructure/controllers/1passwordconnect/kustomization.yaml`:
```yaml
helmCharts:
  - name: connect
    repo: https://...
    valuesFile: values.yaml
    includeCRDs: true
```
Then patch with Kustomize as needed.

## Project Structure Categories

- **`infrastructure/`**: Core cluster services (Cilium, Longhorn, cert-manager)
- **`monitoring/`**: Observability stack (Prometheus, Grafana, Loki)  
- **`my-apps/`**: User applications organized by function:
  - `ai/`: GPU workloads (ollama, comfyui, khoj)
  - `home/`: Home automation (frigate, home-assistant)
  - `media/`: Media services (immich, jellyfin, plex)
  - `development/`: Dev tools (gitea, kafka, temporal)

## Debugging Common Issues

### ArgoCD Issues
```bash
# Check application sync status
kubectl get applications -n argocd

# Check ApplicationSet discovery
kubectl get applicationsets -n argocd
kubectl describe applicationset <name> -n argocd
```

### Talos Node Issues  
```bash
# Essential health check
talosctl health --nodes <node-ip>

# View system logs
talosctl logs -n <node-ip> -k
```

### GPU Workload Issues
```bash
# Verify GPU nodes are labeled
kubectl get nodes -l feature.node.kubernetes.io/pci-0300_10de.present=true

# Check GPU Operator status
kubectl get pods -n gpu-operator
```

## Key Reference Files

- **GitOps Core**: `infrastructure/controllers/argocd/root.yaml` + `infrastructure/controllers/argocd/apps/*-appset.yaml`
- **Talos Config**: `iac/talos/talconfig.yaml` (complete node definitions)  
- **GPU Example**: `my-apps/ai/comfyui/` (complete GPU app pattern)
- **Helm Pattern**: `infrastructure/controllers/1passwordconnect/kustomization.yaml`
- **Web Access**: `my-apps/home/frigate/httproute.yaml` + service with named ports
- **Technical Standards**: `.github/instructions/standards.instructions.md` (detailed patterns)

## Critical Rules

- ✅ **Directory structure = Application discovery** (no manual ArgoCD Applications)
- ✅ **Named Service ports required** for HTTPRoute (`name: http`)
- ✅ **Gateway API only** (no Ingress Controllers)
- ✅ **GitOps workflow for all changes** (no `kubectl edit` on Talos)
- ✅ **Three application categories** (`infrastructure/`, `monitoring/`, `my-apps/`)

## Never Do This

- ❌ Create manual ArgoCD `Application` resources (use directory discovery)
- ❌ Use `kubectl edit` on Talos (changes are ephemeral)
- ❌ Create Services without named ports for HTTPRoute
- ❌ Mix Ingress and Gateway API (this cluster uses Gateway API only)
- ❌ Bypass GitOps workflow for configuration changes