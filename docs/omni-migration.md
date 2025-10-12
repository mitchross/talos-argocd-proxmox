# Migration to Sidero Omni

## Overview
This cluster has migrated from local `talhelper` + `talosctl` management to **Sidero Omni** for centralized Talos cluster management.

**Omni Access**:
- Local: http://192.168.10.15
- Domain: https://omni.vanillax.me

## What Changed

### Before (talhelper workflow)
```bash
# Edit talconfig.yaml locally
vim iac/talos/talconfig.yaml

# Generate configs
talhelper genconfig

# Apply manually
talosctl apply-config --nodes <ip> --file clusterconfig/<node>.yaml
```

### After (Omni workflow)
```bash
# 1. Configure cluster in Omni UI (192.168.10.15 or omni.vanillax.me)
# 2. Download talosconfig from Omni
# 3. Use talosctl with Omni context

export TALOSCONFIG=~/Downloads/talosconfig-omni
talosctl --context omni get members
```

## Setup Steps

### 1. Download Omni-Managed Talosconfig
```bash
# From Omni UI: Cluster → Settings → Download Talosconfig
# Save to: ~/.talos/config-omni

# Set environment variable
export TALOSCONFIG=~/.talos/config-omni

# Verify connection
talosctl --context omni get members
```

### 2. Update Your Shell Profile
Add to `~/.zshrc` or `~/.bashrc`:
```bash
# Omni-managed Talos cluster
export TALOSCONFIG=~/.talos/config-omni
alias talosctl-omni='talosctl --context omni'
```

### 3. Update Kubeconfig
```bash
# Download kubeconfig from Omni or merge with talosctl
talosctl --context omni kubeconfig ~/.kube/config-omni

# Merge with existing config
export KUBECONFIG=~/.kube/config:~/.kube/config-omni
kubectl config view --flatten > ~/.kube/config.merged
mv ~/.kube/config.merged ~/.kube/config
```

## Repository Changes

### Files That Are Now Legacy (Keep for Reference)
These files are no longer used for active cluster management but preserved for documentation:

- `iac/talos/talconfig.yaml` - Configuration now in Omni UI
- `iac/talos/clusterconfig/*.yaml` - Generated configs now from Omni
- `iac/talos/talenv.yaml` - Environment variables now in Omni

### Files Still Used
- `iac/talos/talsecret.sops.yaml` - Import once into Omni
- GitOps manifests in `infrastructure/`, `monitoring/`, `my-apps/` - **No change**
- ArgoCD bootstrap - **No change**

### Commands That Changed

| Old Command (talhelper) | New Command (Omni) |
|------------------------|-------------------|
| `talhelper genconfig` | Configure in Omni UI |
| `talhelper genurl installer` | Omni manages images |
| `talosctl apply-config --file clusterconfig/<node>.yaml` | Omni applies automatically or via UI |
| `talosctl upgrade --image <url>` | Upgrade via Omni UI |

## Node Management with Omni

### Viewing Cluster State
```bash
# List all nodes
talosctl --context omni get members

# Check node health
talosctl --context omni health --nodes <node-ip>

# View node configuration
talosctl --context omni get machineconfig -n <node-ip>
```

### Applying Configuration Changes
1. **Edit in Omni UI**: Cluster → Machine Config → Edit
2. **Apply**: Omni pushes changes automatically
3. **Verify**: `talosctl --context omni get machineconfig`

### Node Upgrades
1. **In Omni UI**: Cluster → Nodes → Select Node → Upgrade
2. **Choose version**: Select Talos version and schematic
3. **Apply**: Omni handles the upgrade process

## GPU Node Configuration in Omni

Your GPU nodes need specific schematic with NVIDIA extensions:

**Schematic ID (from old talconfig.yaml)**:
```
274c5c6e739dbb359c1ad19c304a5c064d23f00baaa18c556bb460ee08483ab2
```

**In Omni UI**:
1. Go to Node → Configuration
2. Set System Extensions:
   - `siderolabs/nonfree-kmod-nvidia-production`
   - `siderolabs/nvidia-container-toolkit-production`
3. Omni generates the schematic automatically

## Troubleshooting

### Can't Connect to Cluster
```bash
# Verify Omni is reachable
curl http://192.168.10.15
# or
curl https://omni.vanillax.me

# Check talosconfig context
talosctl config contexts

# Re-download talosconfig from Omni UI if needed
```

### Configuration Changes Not Applying
- Check Omni UI for sync status
- Verify node is online in Omni dashboard
- Check Omni logs for errors

### Need to Manually Apply Config
```bash
# Download config from Omni UI first, then:
talosctl --context omni apply-config --nodes <ip> --file <downloaded-config>.yaml
```

## Benefits of Omni

✅ **Centralized Management**: Single pane of glass for all Talos nodes  
✅ **Automatic Updates**: Omni can manage upgrades across fleet  
✅ **RBAC**: Team-based access control  
✅ **Audit Logs**: Track all configuration changes  
✅ **Multi-Cluster**: Manage multiple clusters from one UI  
✅ **GitOps Compatible**: Still use ArgoCD for workload management  

## ArgoCD & GitOps (No Changes Required)

The switch to Omni **only affects Talos node management**. Your ArgoCD GitOps workflow remains identical:

```bash
# Bootstrap ArgoCD (same as before)
kustomize build infrastructure/controllers/argocd --enable-helm | kubectl apply -f -
kubectl wait --for condition=established --timeout=60s crd/applications.argoproj.io
kubectl wait --for=condition=Available deployment/argocd-server -n argocd --timeout=300s
kubectl apply -f infrastructure/controllers/argocd/root.yaml
```

## Migration Checklist

- [ ] Omni installed and accessible at 192.168.10.15 or omni.vanillax.me
- [ ] Cluster imported/created in Omni UI
- [ ] Downloaded new talosconfig from Omni
- [ ] Updated `TALOSCONFIG` environment variable
- [ ] Verified `talosctl --context omni get members` works
- [ ] Downloaded/merged kubeconfig
- [ ] Updated shell profile with new aliases
- [ ] Tested node health checks via Omni
- [ ] Updated team documentation
- [ ] Archived old `talhelper` commands from runbooks

## References

- [Sidero Omni Documentation](https://omni.siderolabs.com/docs/)
- [Talos Integration with Omni](https://www.talos.dev/latest/talos-guides/omni/)
- [This Repo's Talos Instructions](.github/instructions/talos.instructions.md) (needs update)
