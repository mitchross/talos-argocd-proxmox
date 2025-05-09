# Proxmox Talos Kubernetes Cluster with Pulumi

This repository contains the necessary infrastructure as code (IaC) to deploy a Talos Linux-based Kubernetes cluster on Proxmox using a hybrid approach with Pulumi and talosctl. The setup is designed to provide a resilient and secure Kubernetes environment that's easy to maintain and scale.

## Features

- **Talos Linux**: Minimalist OS designed specifically for Kubernetes (v1.10.0)
- **Kubernetes**: Latest supported version (v1.32.0)
- **High Availability**: Support for multiple control plane nodes with shared VIP
- **GPU Support**: Configuration for GPU worker nodes with NVIDIA drivers
- **Cilium CNI**: Advanced networking with L2 load balancing capabilities
- **Longhorn Storage**: Integrated persistent storage solution
- **Hybrid Deployment**: Combines talosctl for configuration with Pulumi for orchestration

## Architecture

The deployment consists of:

- **Control Plane Nodes**: 3 nodes with a shared VIP (192.168.10.199)
- **Worker Nodes**: Regular and GPU-enabled compute nodes
- **Container Network Interface**: Cilium (replacing default flannel)
- **Storage**: Longhorn with dedicated volumes
- **Ingress**: Nginx ingress controller with Cilium L2 announcements

## Prerequisites

Before you begin, ensure you have the following:

1. Proxmox VE cluster/standalone server
2. Linux workstation or Mac with administrative access
3. Network access to the Proxmox environment
4. Pulumi account for state management (recommended)
5. Talosctl installed locally
6. Basic understanding of Kubernetes concepts

## Deployment Methods

This repository uses a hybrid approach to deploy your Talos cluster:

### Hybrid Approach (Recommended)

We use talosctl directly to generate and apply the initial configurations, and then use Pulumi to manage the infrastructure. This approach provides:

- Reliable configuration format compatibility
- Infrastructure state management
- Reproducible deployments
- Clear separation of concerns

See the [Pulumi Deployment Guide](iac/pulumi/README.md) for detailed instructions.

### Alternative Methods

The repository also includes:

- **Talhelper Configuration**: The `iac/talos` directory contains configuration for [talhelper](https://github.com/budimanjojo/talhelper), a tool to help create Talos configurations with patches support.
- **Direct Talosctl**: Manual deployment using talosctl commands directly.

## Required Tools

Install the following tools on your workstation:

### Pulumi

```sh
# For macOS
brew install pulumi/tap/pulumi

# For Linux
curl -fsSL https://get.pulumi.com | sh

# Verify installation
pulumi version

# Login to Pulumi Cloud for state management
pulumi login
```

### Talosctl

```sh
# For macOS
brew install siderolabs/tap/talosctl

# For Linux
curl -sL https://talos.dev/install | sh

# Verify installation
talosctl version
```

### Kubectl

```sh
# For macOS
brew install kubectl

# For Linux
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

# Verify installation
kubectl version --client
```

### Talhelper (Optional)

```sh
# Using the installer script
curl https://i.jpillora.com/budimanjojo/talhelper! | sudo bash

# Or with Go
go install github.com/budimanjojo/talhelper@latest

# Verify installation
talhelper version
```

## Quick Start

### 1. Clone Repository and Prepare Config

```sh
# Clone this repository
git clone <repository-url>
cd <repository-directory>

# Create directory for Talos configs
mkdir -p iac/talos-direct
cd iac/talos-direct
```

### 2. Generate Talos Configurations

```sh
# Generate Talos configurations
talosctl gen config proxmox-talos https://192.168.10.199:6443 --kubernetes-version v1.32.0
```

### 3. Apply Configurations

```sh
# Apply to nodes
talosctl apply-config --insecure --nodes 192.168.10.100 --file controlplane.yaml
talosctl apply-config --insecure --nodes 192.168.10.101 --file controlplane.yaml
talosctl apply-config --insecure --nodes 192.168.10.102 --file controlplane.yaml

talosctl apply-config --insecure --nodes 192.168.10.200 --file worker.yaml
talosctl apply-config --insecure --nodes 192.168.10.201 --file worker.yaml
talosctl apply-config --insecure --nodes 192.168.10.203 --file worker.yaml
```

### 4. Bootstrap the Cluster

```sh
# Set talosconfig
export TALOSCONFIG="$(pwd)/talosconfig"

# Bootstrap
talosctl bootstrap --nodes 192.168.10.100

# Verify health
talosctl health --nodes 192.168.10.100

# Get kubeconfig
talosctl kubeconfig --nodes 192.168.10.100 -f ./kubeconfig
export KUBECONFIG="$(pwd)/kubeconfig"
kubectl get nodes
```

### 5. Use Pulumi for Additional Resources

```sh
# Go to Pulumi directory
cd ../../iac/pulumi

# Initialize Pulumi
npm install
pulumi stack init dev

# Deploy additional resources
pulumi up
```

## Post-Deployment Tasks

### Install Cilium CNI

```sh
# Install Cilium CLI
CLI_VERSION=$(curl -s https://raw.githubusercontent.com/cilium/cilium-cli/main/stable.txt)
CLI_ARCH=amd64
curl -L --fail --remote-name-all https://github.com/cilium/cilium-cli/releases/download/${CLI_VERSION}/cilium-linux-${CLI_ARCH}.tar.gz{,.sha256sum}
sha256sum --check cilium-linux-${CLI_ARCH}.tar.gz.sha256sum
sudo tar xzvfC cilium-linux-${CLI_ARCH}.tar.gz /usr/local/bin
rm cilium-linux-${CLI_ARCH}.tar.gz{,.sha256sum}

# Install Cilium
cilium install \
  --helm-set=ipam.mode=kubernetes \
  --helm-set=kubeProxyReplacement=true \
  --helm-set=securityContext.capabilities.ciliumAgent="{CHOWN,KILL,NET_ADMIN,NET_RAW,IPC_LOCK,SYS_ADMIN,SYS_RESOURCE,DAC_OVERRIDE,FOWNER,SETGID,SETUID}" \
  --helm-set=securityContext.capabilities.cleanCiliumState="{NET_ADMIN,SYS_ADMIN,SYS_RESOURCE}" \
  --helm-set=cgroup.autoMount.enabled=false \
  --helm-set=cgroup.hostRoot=/sys/fs/cgroup \
  --helm-set=l2announcements.enabled=true \
  --helm-set=externalIPs.enabled=true
```

### Configure L2 Load Balancer with Cilium

```sh
# Create IP Pool
cat <<EOF | kubectl apply -f -
apiVersion: "cilium.io/v2alpha1"
kind: CiliumLoadBalancerIPPool
metadata:
  name: "cilium-lb-pool"
spec:
  cidrs:
  - cidr: "192.168.10.220/29"
EOF

# Create Announcement Policy
cat <<EOF | kubectl apply -f -
apiVersion: "cilium.io/v2alpha1"
kind: CiliumL2AnnouncementPolicy
metadata:
  name: "cilium-l2-policy"
spec:
  interfaces:
  - ens18
  externalIPs: true
  loadBalancerIPs: true
EOF
```

### Install Longhorn Storage

```sh
# Add Longhorn Helm repository
helm repo add longhorn https://charts.longhorn.io
helm repo update

# Install Longhorn
helm install longhorn longhorn/longhorn \
  --namespace longhorn-system \
  --create-namespace \
  --set defaultSettings.defaultDataPath="/var/lib/longhorn"
```

### Deploy ArgoCD for GitOps (Optional)

```sh
# Create namespace
kubectl create namespace argocd

# Install ArgoCD
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Access ArgoCD UI
kubectl port-forward svc/argocd-server -n argocd 8080:443

# Get initial admin password
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
```

## Common Talosctl Commands

```sh
# Check node health
talosctl health --nodes <node-ip>

# Get running services
talosctl services --nodes <node-ip>

# View logs for a specific service
talosctl logs <service-name> --nodes <node-ip>

# Restart a service
talosctl service restart <service-name> --nodes <node-ip>

# Reboot a node
talosctl reboot --nodes <node-ip>

# Upgrade Talos
talosctl upgrade --nodes <node-ip> --image ghcr.io/siderolabs/installer:<version>

# Reset a node (wipe data)
talosctl reset --nodes <node-ip> --graceful=true
```

## Troubleshooting

### Node not joining the cluster

1. Verify network connectivity:
   ```sh
   talosctl get addresses --nodes <node-ip>
   ```

2. Check node boot logs:
   ```sh
   talosctl logs machined --nodes <node-ip>
   ```

3. Verify machine configuration:
   ```sh
   talosctl get machineconfig --nodes <node-ip>
   ```

### etcd issues

Check etcd health:
```sh
talosctl etcd members --nodes <control-plane-ip>
```

### Talosconfig conflicts

If you have multiple clusters or configurations:
```sh
# Be explicit with the path
export TALOSCONFIG="/absolute/path/to/talosconfig"
```

## References and Resources

- [Talos Linux Documentation](https://www.talos.dev/latest/introduction/what-is-talos/)
- [Suraj Remanan's Guide on Talos Installation on Proxmox](https://surajremanan.com/posts/automating-talos-installation-on-proxmox-with-packer-and-terraform)
- [Talhelper GitHub Repository](https://github.com/budimanjojo/talhelper)
- [Cilium Documentation](https://cilium.io/documentation/)
- [Longhorn Documentation](https://longhorn.io/docs/)
- [ArgoCD Documentation](https://argo-cd.readthedocs.io/en/stable/)

## License

This project is licensed under the [MIT License](LICENSE)