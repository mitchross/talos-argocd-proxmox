# Sidero Omni + Talos on Proxmox Starter Kit

A starter kit for deploying self-hosted Sidero Omni with the Proxmox infrastructure provider. It provisions Talos Linux clusters automatically.

## What This Provides

- Self-hosted Omni deployment on your own hardware
- Proxmox integration that provisions Talos VMs in your Proxmox cluster
- Optional NVIDIA GPU passthrough for AI/ML workloads
- Working example configurations you can customize
- Scripts for SSL and encryption setup

## Architecture overview

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

## Quick start

1. **Prerequisites** - See [docs/PREREQUISITES.md](docs/PREREQUISITES.md)
2. **Deploy Omni** - Follow [omni/README.md](omni/README.md)
3. **Setup Providers** - Follow [proxmox-providers/](proxmox-providers/)
4. **Apply Machine Classes** - `omnictl apply -f omni/machine-classes/`
5. **Validate Template** - `omnictl cluster template validate -f omni/cluster-template/cluster-template-prod-v2.yaml`
6. **Preview Provisioning** - `omnictl cluster template sync -f omni/cluster-template/cluster-template-prod-v2.yaml --dry-run`
7. **Provision Cluster** - `omnictl cluster template sync -f omni/cluster-template/cluster-template-prod-v2.yaml`
8. **Watch Provisioning** - `omnictl cluster template status -f omni/cluster-template/cluster-template-prod-v2.yaml --wait 30m`
9. **Label Machines** - `omnictl apply -f omni/machine-labels/machine-labels.yaml`

Run steps 4-8 from the repository root. Template sync creates the control
plane and worker MachineSets. Do not create MachineSets separately.

## Project structure

```
.
├── omni/                      # Self-hosted Omni deployment
│   ├── docker-compose.yml
│   ├── omni.env.example
│   └── scripts/               # SSL and GPG setup automation
├── proxmox-providers/         # Proxmox infrastructure providers (one compose, one service per host)
│   ├── docker-compose.yml
│   ├── .env.example
│   └── config.yaml.example
├── pi-services/               # Other Pi services, incl. booter (PXE for bare-metal workers)
├── machine-classes/           # VM specs (HP SFF control plane/worker, HP micro worker, Threadripper GPU worker)
├── machine-labels/            # Omni UI labels per machine (host, kind)
├── cluster-template/          # Cluster template + machine config patches
└── docs/                      # Additional documentation
    ├── ARCHITECTURE.md
    ├── PREREQUISITES.md
    ├── TROUBLESHOOTING.md
    └── CILIUM_CNI.md          # Cilium CNI deployment guide
```

## Key features

### Automated provisioning
Define "machine classes" in Omni that specify CPU, RAM, and disk resources. The Proxmox provider watches for new machines and creates VMs that match your specifications.

### GPU support (optional)
Add NVIDIA GPU support for AI/ML workloads. See the machine classes in [machine-classes/](machine-classes/) (for example `threadripper-gpu-worker.yaml`) and the patches in [cluster-template/patches/](cluster-template/patches/).

### Production features
- SSL/TLS encryption with Let's Encrypt
- Etcd data encryption with GPG
- Auth0, SAML, or OIDC authentication
- High availability support

## Deployment examples

Pick the topology that fits your use case. Build each from the machine
classes in [machine-classes/](machine-classes/) and the
[cluster-template/](cluster-template/):

### Simple homelab
For learning and home use:
- 3 nodes (1 control plane + 2 workers)
- 12 cores, 24GB RAM total
- Flannel CNI (default)
- About 10 minutes to set up

Best for learning Kubernetes, home automation, media servers, and development.

### GPU ML cluster
For AI/ML workloads:
- 4 nodes (1 control plane + 1 regular + 2 GPU workers)
- NVIDIA GPU support with proprietary drivers
- Runs TensorFlow and PyTorch, Jupyter notebooks, LLM inference, and Stable Diffusion
- 24 cores, 88GB RAM total

Best for machine learning, AI inference, GPU compute, and data science.

### Production HA with Cilium
For production workloads:
- 6+ nodes (3 control plane + 3+ workers)
- Redundant control plane for high availability
- Cilium CNI with eBPF
- Gateway API with ALPN and AppProtocol
- No kube-proxy (Cilium replacement mode)
- Hubble observability

Best for production workloads, enterprise applications, and high-traffic services.

## Advanced networking

### Cilium CNI

For production deployments, use Cilium CNI:
- 10-40% better performance than traditional CNIs
- eBPF-based load balancing that replaces kube-proxy
- Gateway API support with advanced routing
- L3-L7 network policies
- Hubble network observability
- Service mesh capabilities without sidecars

See the complete guide: [docs/CILIUM_CNI.md](docs/CILIUM_CNI.md)

Quick install:
```bash
# Disable kube-proxy in cluster config, then:
kubectl apply --server-side -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.6.1/standard-install.yaml

cilium-cli install \
    --version 1.20.0 \
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

## Important notes

**Warning:** The Proxmox infrastructure provider is
in **beta**. Expect limitations and bugs. Report issues to the [upstream
repository](https://github.com/siderolabs/omni-infra-provider-proxmox).

### Proxmox provider and machine lifecycle

These hit me in practice. The generic "it's beta" line
isn't enough to plan around.

- **Multiple disks per VM are supported.** The provider creates a primary
  disk plus any `additional_disks` you declare in the machine class, and
  provisions them all at VM creation. Extra data disks get recreated
  with the VM, so no manual Proxmox attach is needed (see
  `omni/machine-classes/threadripper-gpu-worker.yaml`). The CPU-only workers
  keep their boot disks off those pools so they do not consume
  Longhorn capacity. For stateful data, plan
  storage as Longhorn replicas or use external storage (NFS to TrueNAS,
  RustFS S3).
- **Manage extensions through the cluster template.** They belong to the
  Talos image, not a runtime package installation. Omni can update extensions
  on an existing machine, and a driver change does not require deleting
  its VM. Plan for the image rollout and check driver compatibility. See
  [Omni extension management](https://docs.siderolabs.com/omni/infrastructure-and-extensions/install-talos-linux-extensions).
- **Omni 1.11 owns install-disk selection.** Legacy `machine.install.disk`
  patches no longer select it. An installed machine keeps its detected system
  disk. Fresh machines default to the smallest eligible disk. With this GPU
  class that selects the 300 GB flash disk. Do not delete or reprovision the GPU VM
  until selection is deterministic for a replacement UUID.
- **No VM migration on node failure.** If a Proxmox host dies, its VMs
  don't auto-migrate to another host. For that you need Proxmox HA separately
  (cluster-level, not Omni-level).
- **Talos machine config replaces cloud-init.** Ignore Proxmox cloud-init hooks.
  All node customization goes through Omni cluster-template patches, not Proxmox.

## Licensing: what "BSL" means for you

Omni uses the **Business Source License** (BSL). In practice:

- Free for non-production use: homelabs, dev, staging, learning.
  This repo's cluster falls in this group.
- Free for production use up to a user or seat limit set by Sidero.
  Check their current terms, because they've adjusted this more than once.
- A paid license is required for production beyond that limit, or for
  any commercial SaaS offering that incorporates Omni.
- Each commit converts to MPL-2.0 after 4 years. Old versions
  eventually become fully open source, but the current one isn't.

Talos Linux itself is MPL-2.0 (fully open). The Proxmox provider is also
MPL-2.0. Only Omni, the control plane, is BSL-restricted.

If you run Omni **for a business**, read the actual license at
https://github.com/siderolabs/omni/blob/main/LICENSE before assuming
your use case is covered.

## Use cases

- Homelab: self-hosted Kubernetes cluster management
- Edge computing: manage distributed Talos clusters
- Development: provision clusters quickly for testing
- Production: cluster lifecycle management

## License

This starter kit is provided as-is. See the Licensing section above
for what BSL means in practice.

- Omni: Business Source License (BSL), free for non-prod or below the seat cap
- Talos Linux: MPL-2.0 (fully open)
- Proxmox provider: MPL-2.0 (fully open)

## Contributing

Found a bug or want an improvement? Open a PR.

## Resources

- [Omni documentation](https://docs.siderolabs.com/omni/)
- [Talos documentation](https://docs.siderolabs.com/talos/)
- [Proxmox Provider](https://github.com/siderolabs/omni-infra-provider-proxmox)
- [Sidero Labs Slack](https://slack.dev.talos-systems.io/)

## Credits

Thanks to the Sidero Labs team for Omni, Talos, and the Proxmox provider.
