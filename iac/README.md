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

# Update vars/local.pkrvars.hcl with your settings

# Initialize and validate packer
packer init -upgrade .
packer validate -var-file="vars/local.pkrvars.hcl" .

# Build the template
packer build -var-file="vars/local.pkrvars.hcl" .
```

### 3. Terraform - Provisioning Infrastructure

```bash
# Navigate to terraform directory
cd iac/terraform/c0depool-talos-cluster/

# Set up credentials
cp example.credentails.auto.tfvars credentails.auto.tfvars
# Update the file credentails.auto.tfvars

# Update locals.tf with your configuration

# Initialize Terraform
terraform init

# Create execution plan
terraform plan \
  -var 'proxmox_api_url=https://192.168.10.11:8006/api2/json' \
  -var 'proxmox_node=proxmox-threadripper' \
  -var 'proxmox_api_token_id=root@pam!iac' \
  -var 'proxmox_api_token_secret=ddxxxxb-0cd8-4xxxf-9xxxdb-6asssxx' \
  -out .tfplan

# Apply the plan
terraform apply \
  -var 'proxmox_api_url=https://192.168.10.xx:8006/api2/json' \
  -var 'proxmox_node=proxmox-threadripper' \
  -var 'proxmox_api_token_id=root@pam!iac' \
  -var 'proxmox_api_token_secret=c30xxxxedb-xxxd8-4c0f-9xxxb-6axxxx1c3ae'
```

**Important:** Take note of the MAC addresses outputted, copy and update in the following step.

### 4. Talos Configuration with talhelper

```bash
# Navigate to talos directory
cd iac/talos

# Generate talhelper secret
talhelper gensecret > talsecret.sops.yaml

# Create age key for encryption
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
export SOPS_AGE_KEY_FILE=/Users/<YOURHOME>/.config/sops/age/keys.txt
talhelper genconfig
```

### 5. Bootstrap Talos Cluster

In Proxmox, go to each VM and get the temporary IP. 
**Note:** The IP WON'T be what you set Talos to be configured for, so make sure you grab it from the console!

```bash
cd iac/talos

# For master node(s)
talosctl apply-config --insecure --nodes <master-node ip> --file clusterconfig/<master-config>.yaml

# For worker(s)
talosctl apply-config --insecure --nodes <worker-node ip> --file clusterconfig/<worker-config>.yaml

# Set up talosconfig
mkdir -p $HOME/.talos
cp clusterconfig/talosconfig $HOME/.talos/config

# Run the bootstrap command
# Note: The bootstrap operation should only be called ONCE on a SINGLE control plane/master node
# (use any one if you have multiple master nodes)
talosctl bootstrap -n <master-node ip>
```

### 6. Access the Kubernetes Cluster

```bash
# Get kubeconfig
mkdir -p $HOME/.kube
talosctl -n <master-node ip> kubeconfig $HOME/.kube/config

# Verify nodes are up
kubectl get nodes
```

### 7. Upgrade Talos (when needed)

```bash
talosctl upgrade --image factory.talos.dev/installer/<image schematic ID>:<talos version> --preserve --nodes "<list of master and worker nodes, comma separated>"

# Verify extensions for each node
talosctl get extensions --nodes <node IP>
```

### 8. Install Cilium CNI

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
  --helm-set=devices=ens+
```