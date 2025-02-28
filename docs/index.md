# K3s ArgoCD Proxmox Cluster

A GitOps-driven Kubernetes cluster using K3s, ArgoCD, and Cilium, with integrated Cloudflare Tunnel for secure external access.

## Overview

This project demonstrates a single-node K3s cluster setup, optimized for home lab and small production environments. While K3s supports multi-node clusters, this setup uses a single node to simplify storage management and reduce complexity.

### Why Single Node?
- Fixed storage location for applications (no need for distributed storage)
- Simplified backup and restore procedures
- Perfect for home lab and small production workloads
- Can be expanded with worker nodes for compute-only scaling

### Current Hardware Stack
```
🧠 Compute
├── AMD Threadripper 2950X (16c/32t)
├── 128GB ECC DDR4 RAM
├── 2× NVIDIA RTX 3090 24GB
└── Google Coral TPU

💾 Storage
├── 4TB ZFS RAID-Z2
├── NVMe OS Drive
└── Local Path Storage for K8s

🌐 Network
├── 2.5Gb Networking
├── Firewalla Gold
└── Internal DNS Resolution
```

## Three-Tier Architecture

This cluster follows a clean three-tier architecture:

1. **📚 Infrastructure Tier** - Core system components deployed first (sync wave -2)
   - Network components (Cilium, Gateway API)
   - ArgoCD and GitOps controllers
   - Cert-manager and security components

2. **📊 Monitoring Tier** - Observability stack deployed second (sync wave 0)
   - Prometheus and Grafana
   - Loki for logs
   - Uptime monitors

3. **🚀 Applications Tier** - User workloads deployed last (sync wave 1)
   - Media applications
   - AI workloads
   - User services

## Quick Links

- [ArgoCD Setup Guide](argocd.md#installation)
- [Network Configuration](network.md)
- [Storage Setup](storage.md)
- [Security Configuration](secrets.md)
- [GPU Setup](gpu.md)
- [External Services](external-services.md)

## Features

- 🚀 Single node K3s cluster with worker node scaling options
- ⚓ GitOps with ArgoCD and simplified three-tier ApplicationSets
- 🔒 Secure access through Cloudflare Zero Trust
- 🔐 Secrets management with 1Password integration
- 🌐 Split DNS for internal/external access
- 💾 Local path storage with node affinity
- 🎮 GPU support for AI/ML workloads

## Getting Started

Visit our [ArgoCD Setup Guide](argocd.md#installation) to begin installation. 