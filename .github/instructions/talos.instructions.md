---
applies_to:
  - "omni/**"
  - "**/*talos*"
---

# Talos OS Management Instructions

## Overview
Talos OS is an immutable Linux distribution designed for Kubernetes - no shell, no SSH, API-only management. This cluster is managed via **Omni** (Sidero's Talos management platform) with the Proxmox Infrastructure Provider.

## Key Concepts
- **Immutable OS**: No package manager, all changes via configuration
- **API-only**: All management via Omni UI, never SSH
- **Declarative**: Configuration managed in Omni (machine classes, cluster templates)
- **System Extensions**: Drivers and modules loaded at boot time

## Cluster Management via Omni

### Node Operations
- **Provisioning**: Omni + Sidero Proxmox Provider handles VM creation and Talos installation
- **Upgrades**: Managed through Omni UI (Talos version, system extensions)
- **Configuration**: Machine classes and patches in `omni/` directory
- **Kubeconfig**: Download from Omni UI > cluster > "Download Kubeconfig"

### Machine Classes
Defined in `omni/machine-classes/`:
- `control-plane.yaml` - Control plane nodes
- `worker.yaml` - Regular worker nodes
- `gpu-worker.yaml` - GPU worker nodes with NVIDIA extensions

### Cluster Template
`omni/cluster-template/cluster-template.yaml` defines the cluster layout with patches in `omni/cluster-template/patches/`.

## Node Types

### Control Plane Nodes
- Run etcd, kube-apiserver, kube-controller-manager
- Default container runtime: `runc`

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

### From Omni UI
- View node health, logs, and events directly in Omni
- Trigger upgrades and configuration changes

### From CLI (if needed)
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
- **Config changes not applied**: Use Omni UI, not `kubectl edit`
- **GPU not available**: Verify system extensions in machine class, may need upgrade via Omni
- **Network issues**: Check static IP configuration in Omni node patches

## Critical Rules
- Never SSH to nodes - API-only management
- Never use `kubectl edit` for node config - changes are ephemeral
- Use Omni UI for all node lifecycle operations (upgrades, patches, extensions)
