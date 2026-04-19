# Sidero Omni + Talos on Proxmox Starter Kit

A complete, production-ready starter kit for deploying self-hosted Sidero Omni with the Proxmox infrastructure provider to automatically provision Talos Linux clusters.

## What This Provides

- **Self-hosted Omni deployment** - Run your own Omni instance on-premises
- **Proxmox integration** - Automatically provision Talos VMs in your Proxmox cluster
- **GPU support** (optional) - Configure NVIDIA GPU passthrough for AI/ML workloads
- **Complete examples** - Working configurations you can customize
- **Setup automation** - Scripts to streamline SSL and encryption setup

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Your Infrastructure                   │
│                                                          │
│  ┌──────────────┐         ┌─────────────────────────┐  │
│  │ Omni Server  │◄────────┤ Proxmox Infrastructure  │  │
│  │ (Self-hosted)│         │ Provider (Docker)       │  │
│  │              │         │                         │  │
│  │ - Web UI     │         │ - Watches Omni API     │  │
│  │ - API        │         │ - Creates VMs          │  │
│  │ - SideroLink │         │ - Manages lifecycle    │  │
│  └──────┬───────┘         └──────────┬──────────────┘  │
│         │                            │                  │
│         │         ┌──────────────────▼─────┐            │
│         │         │   Proxmox Cluster      │            │
│         │         │                        │            │
│         └────────►│  ┌──────────────────┐  │            │
│                   │  │ Talos VM Node 1  │  │            │
│                   │  │ Talos VM Node 2  │  │            │
│                   │  │ Talos VM Node 3  │  │            │
│                   │  └──────────────────┘  │            │
│                   └────────────────────────┘            │
└─────────────────────────────────────────────────────────┘
```

## Quick Start

1. **Prerequisites** - See [docs/PREREQUISITES.md](docs/PREREQUISITES.md)
2. **Deploy Omni** - Follow [omni/README.md](omni/README.md)
3. **Setup Provider** - Follow [proxmox-provider/README.md](proxmox-provider/README.md)
4. **Apply Machine Classes** - `omnictl apply -f machine-classes/`
5. **Sync Cluster Template** - `omnictl cluster template sync -v -f cluster-template.yaml`
6. **Create Clusters** - Use Omni UI to provision clusters using your machine classes

## Project Structure

```
.
├── omni/                      # Self-hosted Omni deployment
│   ├── docker-compose.yml
│   ├── omni.env.example
│   └── scripts/               # SSL and GPG setup automation
├── proxmox-provider/          # Proxmox infrastructure provider
│   ├── docker-compose.yml
│   ├── .env.example
│   └── config.yaml.example
├── talos-configs/             # Example Talos configurations
│   └── gpu-worker-patch.yaml  # NVIDIA GPU support
├── examples/                  # Complete deployment examples
│   ├── simple-homelab/        # Minimal 3-node cluster
│   ├── gpu-ml-cluster/        # GPU-enabled for AI/ML
│   └── production-ha/         # HA cluster with Cilium CNI
└── docs/                      # Additional documentation
    ├── ARCHITECTURE.md
    ├── PREREQUISITES.md
    ├── TROUBLESHOOTING.md
    └── CILIUM_CNI.md          # Cilium CNI deployment guide
```

## Key Features

### Automated Provisioning
Define "machine classes" in Omni that specify CPU, RAM, and disk resources. The Proxmox provider watches for new machines and automatically creates VMs matching your specifications.

### GPU Support (Optional)
Include NVIDIA GPU support for AI/ML workloads. See [talos-configs/README.md](talos-configs/README.md) for configuration details.

### Production Ready
- SSL/TLS encryption with Let's Encrypt
- Etcd data encryption with GPG
- Auth0, SAML, or OIDC authentication
- High availability support

## Deployment Examples

Choose the example that best fits your use case:

### 🏠 [Simple Homelab](examples/simple-homelab/)
Perfect for learning and home use:
- **3 nodes** (1 control plane + 2 workers)
- **Minimal resources** (12 cores, 24GB RAM total)
- **Flannel CNI** (default, simple)
- **Quick setup** (~10 minutes)
- **Cost effective** for homelabs

**Best for**: Learning Kubernetes, home automation, media servers, development

### 🤖 [GPU ML Cluster](examples/gpu-ml-cluster/)
Optimized for AI/ML workloads:
- **4 nodes** (1 control plane + 1 regular + 2 GPU workers)
- **NVIDIA GPU support** with proprietary drivers
- **TensorFlow/PyTorch ready**
- **Jupyter notebooks**, LLM inference, Stable Diffusion
- **24 cores, 88GB RAM total**

**Best for**: Machine learning, AI inference, GPU compute, data science

### 🏭 [Production HA with Cilium](examples/production-ha/)
Enterprise-grade cluster:
- **6+ nodes** (3 control plane + 3+ workers)
- **High availability** with redundant control plane
- **Cilium CNI** with eBPF for performance
- **Gateway API** with ALPN and AppProtocol
- **No kube-proxy** (Cilium replacement mode)
- **Hubble observability**

**Best for**: Production workloads, enterprise applications, high-traffic services

## Advanced Networking

### Cilium CNI

For production deployments, we recommend Cilium CNI:
- **10-40% better performance** vs traditional CNIs
- **eBPF-based** load balancing (replaces kube-proxy)
- **Gateway API** support with advanced routing
- **L3-L7 network policies** for security
- **Hubble** for deep network observability
- **Service mesh** capabilities without sidecars

See the complete guide: [docs/CILIUM_CNI.md](docs/CILIUM_CNI.md)

**Quick Install**:
```bash
# Disable kube-proxy in cluster config, then:
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.0.0/standard-install.yaml

cilium install \
    --set cluster.name=talos-prod-cluster \
    --set ipam.mode=kubernetes \
    --set kubeProxyReplacement=true \
    --set securityContext.capabilities.ciliumAgent="{CHOWN,KILL,NET_ADMIN,NET_RAW,IPC_LOCK,SYS_ADMIN,SYS_RESOURCE,DAC_OVERRIDE,FOWNER,SETGID,SETUID}" \
    --set securityContext.capabilities.cleanCiliumState="{NET_ADMIN,SYS_ADMIN,SYS_RESOURCE}" \
    --set cgroup.autoMount.enabled=false \
    --set cgroup.hostRoot=/sys/fs/cgroup \
    --set k8sServiceHost=localhost \
    --set k8sServicePort=7445 \
    --set gatewayAPI.enabled=true \
    --set gatewayAPI.enableAlpn=true \
    --set gatewayAPI.enableAppProtocol=true
```

## Important Notes

⚠️ **Proxmox Provider Status**: The Proxmox infrastructure provider is
currently in **beta**. Expect some limitations and potential bugs. Please
report issues to the [upstream
repository](https://github.com/siderolabs/omni-infra-provider-proxmox).

### Concrete beta limitations (as of Talos 1.13 / Omni 1.7)

These are things that hit me in practice — the generic "it's beta" line
isn't enough to plan around.

- **Single disk per VM.** The provider creates one disk when it
  provisions a VM. Want separate OS + data disks? You'll have to attach
  them manually in Proxmox after the fact, which means they won't be
  recreated if the VM is destroyed and re-provisioned. In practice: plan
  all storage as Longhorn replicas on the single disk, or use external
  storage (NFS to TrueNAS, RustFS S3) for stateful data.
- **No HA local storage.** Because of the single-disk limit, Longhorn can
  replicate across nodes but not across dedicated storage tiers within
  a node. Not a real problem for homelab scale, worth flagging for prod.
- **Extensions must be baked into the Talos image OR declared in the
  cluster template.** You can't "install an extension" at runtime the
  way you would a package. Changing extensions = image rebuild in Omni +
  node replacement. This is especially relevant for NVIDIA driver
  swaps (production → OSS) — see the OSS NVIDIA migration plan in
  `docs/superpowers/plans/`.
- **`machine.install.disk` is mandatory on Talos 1.13.** Without it,
  fresh VMs provision but stay stuck in `UPGRADING` forever (see root
  README). This is a Talos 1.13 LifecycleService change, not a provider
  bug, but it surfaces through the provider first. The patch is already
  in `omni/cluster-template/cluster-template.yaml`.
- **No VM migration on node failure.** If a Proxmox host dies, its VMs
  don't auto-migrate to another host. You'll need Proxmox HA separately
  (cluster-level, not Omni-level) for that.
- **Cloud-init equivalent is… Talos machine config.** If you're used to
  Proxmox cloud-init hooks, ignore them — all node customization goes
  through Omni cluster-template patches, not Proxmox.

## Licensing — what "BSL" actually means for you

Omni uses the **Business Source License** (BSL). Practical impact:

- ✅ **Free for non-production use** — homelabs, dev, staging, learning.
  This repo's cluster falls squarely in this bucket.
- ✅ **Free for production use up to a user/seat limit** set by Sidero
  (check their current terms — they've adjusted this more than once).
- 💰 **Paid license required** for production beyond that limit, or for
  any commercial SaaS offering that incorporates Omni.
- 🕰️ **Converts to MPL-2.0 after 4 years** per commit — old versions
  eventually become fully open source, but the current one isn't.

Talos Linux itself is MPL-2.0 (fully open). The Proxmox provider is also
MPL-2.0. Only Omni the control-plane is BSL-restricted.

If you're running Omni **for a business**, read the actual license at
https://github.com/siderolabs/omni/blob/main/LICENSE before assuming
your use case is covered.

## Use Cases

- **Homelab**: Self-hosted Kubernetes cluster management
- **Edge Computing**: Manage distributed Talos clusters
- **Development**: Rapid cluster provisioning for testing
- **Production**: Enterprise-grade cluster lifecycle management

## License

This starter kit is provided as-is. See the **Licensing** section above
for what BSL means in practice.

- Omni: Business Source License (BSL) — free for non-prod / below seat cap
- Talos Linux: MPL-2.0 (fully open)
- Proxmox provider: MPL-2.0 (fully open)

## Contributing

Found a bug? Have an enhancement? PRs welcome! This is a community-driven starter kit.

## Resources

- [Omni Documentation](https://docs.siderolabs.com/omni/)
- [Talos Documentation](https://docs.siderolabs.com/talos/)
- [Proxmox Provider](https://github.com/siderolabs/omni-infra-provider-proxmox)
- [Sidero Labs Slack](https://slack.dev.talos-systems.io/)

## Credits

Built by the community, for the community. Special thanks to the Sidero Labs team for their support and tooling.
