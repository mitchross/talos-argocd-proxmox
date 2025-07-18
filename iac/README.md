# K3S-ARGOCD-PROXMOX

Infrastructure provisioning code for proxmox talos 

## Prerequisites

Before you begin, install the following tools:

```bash
# Brew Install
brew install terraform talosctl talhelper kubectl sops age cilium-cli
```

## Setup Guide

### 1. Proxmox Setup

Generate an API token for Proxmox root user:

1. Login to Proxmox web console using root user
2. Navigate to Datacenter → Permissions → API Tokens → Add
3. Select root as the user, give a name for the token ID and click Add
4. Copy the token once displayed
5. **Important:** Uncheck privilege separation

You should get credentials in this format:
```
root@pam!iac
cxxxxxcfedb-0ddd8-4c0f-932b-6adxxxxxxxxxc3ae
```

### 2. Packer - Creating Talos VM Template

```bash
# Navigate to packer directory
cd iac/packer/talos-packer/

# Update vars/local.pkrvars.hcl with your common settings and Proxmox credentials.

# Initialize and validate packer.
# Note: We now specify both the common 'local' vars and the build-specific vars.
packer init -upgrade .

# Validate the desired template by specifying the appropriate var files.
packer validate -var-file="vars/local.pkrvars.hcl" -var-file="vars/non-gpu.pkrvars.hcl" .
packer validate -var-file="vars/local.pkrvars.hcl" -var-file="vars/gpu.pkrvars.hcl" .

# Build the desired template by specifying the appropriate var files.
packer build -var-file="vars/local.pkrvars.hcl" -var-file="vars/non-gpu.pkrvars.hcl" .
# Or for the GPU-enabled template:
packer build -var-file="vars/local.pkrvars.hcl" -var-file="vars/gpu.pkrvars.hcl" .
```

### 3. Terraform - Provisioning Infrastructure

The Terraform setup is fully declarative with all node configurations managed in one place.

1.  **Navigate to the Terraform directory:**
    ```bash
    cd iac/terraform/talos-cluster/
    ```

2.  **Set up credentials:**
    Create a `credentials.auto.tfvars` file (automatically loaded by Terraform). This file is git-ignored and contains your Proxmox secrets:
    ```hcl
    # iac/terraform/talos-cluster/credentials.auto.tfvars
    proxmox_api_url      = "https://<your-proxmox-ip>:8006/api2/json"
    proxmox_node         = "<your-proxmox-node-name>"
    proxmox_api_token    = "<your-api-token-id>=<your-api-token-secret>"
    proxmox_pool         = ""
    proxmox_ssh_password = "<your-proxmox-ssh-password>"
    ```
    
    **Example:**
    ```hcl
    proxmox_api_url      = "https://192.168.10.11:8006/api2/json"
    proxmox_node         = "proxmox-threadripper"
    proxmox_api_token    = "root@pam!iac=c30cfedb-0cd8-4c0f-932b-6aded8a1c3ae"
    proxmox_pool         = ""
    proxmox_ssh_password = "your-ssh-password"
    ```

3.  **Configure your cluster nodes:**
    Node configurations are defined in `variables.tf` in the `nodes` variable. This is the single source of truth for your cluster infrastructure.
    - Review and adjust IPs, MAC addresses, cores, memory, and disk sizes as needed
    - **Important**: Ensure MAC addresses match the `hardwareAddr` selectors in `iac/talos/talconfig.yaml`
    - VM IDs and roles are pre-configured for a 3-master + 3-worker cluster

4.  **Initialize and apply Terraform:**
    ```bash
    # Initialize Terraform (only needed once)
    terraform init -upgrade

    # Plan and apply changes
    terraform plan -out=.tfplan
    terraform apply .tfplan
    ```

    **For targeted deployments** (e.g., recreating a single VM):
    ```bash
    # Target specific resources
    terraform plan -target='proxmox_virtual_environment_vm.vm["talos-master-00"]' -out=.tfplan
    terraform apply .tfplan
    ```

### 4. Talos Configuration with talhelper

```bash
# Navigate to talos directory
cd iac/talos

# Generate talhelper secret
talhelper gensecret > talsecret.sops.yaml

# Create age key for encryption ( only run once ) 
mkdir -p $HOME/.config/sops/age/
age-keygen -o $HOME/.config/sops/age/keys.txt
```

In the `iac/talos` directory, create a `.sops.yaml` with below content:

```yaml
---
creation_rules:
  - age: >-
      <age-public-key> ## get this in the keys.txt file from previous step
```

Then encrypt the secrets file:

```bash
cd iac/talos
sops -e -i talsecret.sops.yaml

# Generate Talos configuration
export SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt
talhelper genconfig
```

### 5. Bootstrap Talos Cluster

1.  **Apply configuration to each node.**
    Run the following commands one by one. The `--insecure` flag is required for the initial setup as the nodes don't yet trust the cluster's CA.

    ```bash
    # Control Plane Nodes
    talosctl apply-config --insecure --nodes 192.168.10.100 --file clusterconfig/proxmox-talos-cluster-talos-cluster-control-00.yaml
    talosctl apply-config --insecure --nodes 192.168.10.101 --file clusterconfig/proxmox-talos-cluster-talos-cluster-control-01.yaml
    talosctl apply-config --insecure --nodes 192.168.10.102 --file clusterconfig/proxmox-talos-cluster-talos-cluster-control-02.yaml

    # Worker Nodes
    talosctl apply-config --insecure --nodes 192.168.10.200 --file clusterconfig/proxmox-talos-cluster-talos-cluster-gpu-worker-00.yaml
    talosctl apply-config --insecure --nodes 192.168.10.201 --file clusterconfig/proxmox-talos-cluster-talos-cluster-worker-01.yaml
    talosctl apply-config --insecure --nodes 192.168.10.203 --file clusterconfig/proxmox-talos-cluster-talos-cluster-worker-02.yaml
    ```

2.  **Set up talosconfig for cluster access.**
    ```bash
    mkdir -p ~/.talos
    cp clusterconfig/talosconfig ~/.talos/config
    ```

3.  **Bootstrap the cluster.**
    This command only needs to be run on a *single* control plane node, and only once.
    ```bash
    talosctl bootstrap -n 192.168.10.100
    ```

### 6. Access the Kubernetes Cluster

```bash
# Get kubeconfig
mkdir -p ~/.kube
talosctl kubeconfig -n 192.168.10.100 ~/.kube/config

# Verify nodes are up
kubectl get nodes
```

### 7. Upgrade Talos (when needed)

```bash
talosctl upgrade --image ghcr.io/siderolabs/installer:v1.10.4 --nodes "192.168.10.100,192.168.10.101,192.168.10.102,192.168.10.200,192.168.10.201,192.168.10.203"

# Verify extensions for each node
talosctl get extensions --nodes 192.168.10.100
```### 8. Upgrade Kubernetes (when needed)

Upgrading the Kubernetes version is a separate step from upgrading Talos itself. Run the following command against a single control plane node to initiate the rolling upgrade of Kubernetes components across the entire cluster.

**Note:** You must use a Kubernetes version compatible with your Talos installation. See the [Talos support matrix](https://www.talos.dev/latest/kubernetes-support-matrix/) for details.

```bash
talosctl upgrade-k8s --to <supported-k8s-version> --nodes 192.168.10.100
```

### 9. Install Cilium CNI

**IMPORTANT:** Take note of the Ethernet device. Devices might be named `ens`, `eth`, or `enp` depending on your system.

```bash
cilium install \
  --helm-set=ipam.mode=kubernetes \
  --helm-set=kubeProxyReplacement=true \
  --helm-set=securityContext.capabilities.ciliumAgent="{CHOWN,KILL,NET_ADMIN,NET_RAW,IPC_LOCK,SYS_ADMIN,SYS_RESOURCE,DAC_OVERRIDE,FOWNER,SETGID,SETUID}" \
  --helm-set=securityContext.capabilities.cleanCiliumState="{NET_ADMIN,SYS_ADMIN,SYS_RESOURCE}" \
  --helm-set=cgroup.autoMount.enabled=false \
  --helm-set=cgroup.hostRoot=/sys/fs/cgroup \
  --helm-set=l2announcements.enabled=true \
  --helm-set=externalIPs.enabled=true \
  --set gatewayAPI.enabled=true \
  --helm-set=devices=e+ \
  --helm-set=operator.replicas=1
```

