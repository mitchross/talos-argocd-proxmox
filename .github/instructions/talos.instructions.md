---
applies_to: 
  - "iac/talos/**"
  - "**/*talos*"
---

# Talos OS Management Instructions

## Overview
Talos OS is an immutable Linux distribution designed for Kubernetes - no shell, no SSH, API-only management.

## Key Concepts
- **Immutable OS**: No package manager, all changes via configuration
- **API-only**: All management via `talosctl`, never SSH
- **Declarative**: Configuration defined in `iac/talos/talconfig.yaml`
- **System Extensions**: Drivers and modules loaded at boot time

## Configuration Management

### Talhelper Workflow
```bash
# Generate machine configs from talconfig.yaml
cd iac/talos
talhelper genconfig

# Generate installer URLs for upgrades
talhelper genurl installer -c talconfig.yaml -n "<node-name>"
```

### Applying Changes
```bash
# For configuration changes (non-image changes)
talosctl apply-config --nodes <node-ip> --file iac/talos/clusterconfig/<node>.yaml

# For Talos version or system extension changes (requires reboot)
INSTALLER_URL=$(talhelper genurl installer -c iac/talos/talconfig.yaml -n "<node-name>")
talosctl upgrade --nodes "<node-ip>" --image "$INSTALLER_URL"
```

### Secrets Management
- `talsecret.sops.yaml` contains cluster encryption keys
- Always encrypted with SOPS before committing
- Generated once with `talhelper gensecret > talsecret.sops.yaml`

## Node Types and Configuration

### Control Plane Nodes
- Run etcd, kube-apiserver, kube-controller-manager
- Default container runtime: `runc`
- Label: `node.kubernetes.io/exclude-from-external-load-balancers`

### GPU Worker Nodes  
- NVIDIA system extensions: `nonfree-kmod-nvidia-production`, `nvidia-container-toolkit-production`
- Default container runtime: `nvidia`
- Kernel modules: `nvidia`, `nvidia_uvm`, `nvidia_drm`, `nvidia_modeset`
- Node selector: `feature.node.kubernetes.io/pci-0300_10de.present: "true"`

### Regular Worker Nodes
- Standard system extensions only
- Default container runtime: `runc`
- Longhorn storage mounts configured

## System Extensions
System extensions are loaded at boot time and cannot be changed at runtime.

### Common Extensions
- `siderolabs/amd-ucode`: AMD CPU microcode
- `siderolabs/gasket-driver`: Google Coral TPU support  
- `siderolabs/iscsi-tools`: iSCSI storage support
- `siderolabs/nfsd`: NFS server support
- `siderolabs/qemu-guest-agent`: VM guest tools
- `siderolabs/util-linux-tools`: Additional Linux utilities

### GPU-Specific Extensions
- `siderolabs/nonfree-kmod-nvidia-production`: NVIDIA kernel modules
- `siderolabs/nvidia-container-toolkit-production`: NVIDIA container runtime

## Network Configuration
- Static IP addresses configured per node
- DNS: Cloudflare (1.1.1.1, 1.0.0.1)
- NTP: time.cloudflare.com
- No DHCP - all IPs statically assigned

## Troubleshooting

### Health Checks
```bash
# Check node health
talosctl health --nodes <node-ip>

# Check system services
talosctl services --nodes <node-ip>

# View logs
talosctl logs -n <node-ip> -k  # kernel logs
talosctl logs -n <node-ip> kubelet  # kubelet logs
```

### Common Issues
- **Config changes not applied**: Use `talosctl apply-config`, not `kubectl edit`
- **GPU not available**: Verify system extensions in talconfig.yaml, may need upgrade
- **Network issues**: Check static IP configuration in networkInterfaces

## Critical Rules
- ❌ **Never SSH to nodes** - API-only management
- ❌ **Never use `kubectl edit` for node config** - changes are ephemeral  
- ✅ **Always regenerate configs** when changing talconfig.yaml
- ✅ **Use `upgrade` command** for system extension changes
- ✅ **Encrypt secrets with SOPS** before committing