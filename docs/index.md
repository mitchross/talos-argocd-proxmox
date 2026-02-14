# Talos ArgoCD Proxmox

Production GitOps Kubernetes cluster running on Talos OS with self-managing ArgoCD.

See the [README](https://github.com/mitchross/talos-argocd-proxmox) for setup instructions.

## Documentation

- [ArgoCD & GitOps Architecture](argocd.md) - Sync waves, app-of-apps pattern, health checks
- [Backup & Restore](backup-restore.md) - Kyverno + VolSync + PVC Plumber automated backups
- [Full Backup Flow](pvc-plumber-full-flow.md) - Complete bare-metal to disaster recovery walkthrough
- [Network Topology](network-topology.md) - Cluster networking and 10G infrastructure
- [Network Security](network-policy.md) - Cilium network policies and LAN isolation
