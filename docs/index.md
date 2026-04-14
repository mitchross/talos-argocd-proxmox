# Talos ArgoCD Proxmox

Production GitOps Kubernetes cluster running on Talos OS with self-managing ArgoCD.

See the [README](https://github.com/mitchross/talos-argocd-proxmox) for setup instructions.

## Documentation

- [ArgoCD & GitOps Architecture](argocd.md) - Sync waves, app-of-apps pattern, health checks
- [Backup & Restore](backup-restore.md) - Kyverno + VolSync + PVC Plumber automated backups
- [Homelab Storage Reference](homelab-storage-reference.md) - Recommended end-to-end storage patterns for single Proxmox hosts and 3-node homelabs
- [Conditional Restore Ecosystem Research](conditional-restore-ecosystem-research.md) - What public docs, blogs, and homelab operators actually do today for PVC restore workflows
- [CNPG Disaster Recovery](cnpg-disaster-recovery.md) - Manual Postgres recovery workflow, ArgoCD race handling, and lineage bump rules
- [AI-Guided CNPG Recovery Prompt](cnpg-disaster-recovery.md#llm-recovery-prompt-templates) - Copy/paste prompts for LLM-assisted recovery
- [Full Backup Flow](pvc-plumber-full-flow.md) - Complete bare-metal to disaster recovery walkthrough
- [VPA Resource Optimization](vpa-resource-optimization.md) - Using VPA and Kyverno auto-generate policy to right-size pod resources
- [Network Topology](network-topology.md) - Cluster networking and 10G infrastructure
- [Network Security](network-policy.md) - Cilium network policies and LAN isolation
