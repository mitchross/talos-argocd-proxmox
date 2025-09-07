# Infrastructure as Code - Terraform + Talos Workflow

Infrastructure provisioning code for Proxmox Talos cluster with automated value extraction.

## 🔧 Tools Required

- [Terraform](https://developer.hashicorp.com/terraform/downloads) - Infrastructure provisioning
- [talhelper](https://budimanjojo.github.io/talhelper/latest/installation/) - Talos configuration management
- [talosctl](https://www.talos.dev/latest/introduction/getting-started/) - Talos cluster management
- [SOPS](https://github.com/getsops/sops) - Secrets encryption
- [age](https://github.com/FiloSottile/age) - Encryption tool for SOPS

### Install with Homebrew
```bash
brew install terraform talhelper talosctl kubectl sops age cilium-cli
```

## 🚀 Quick Start

**TL;DR - For experienced users:**

1. Edit `terraform/talos-cluster/cluster.auto.tfvars` with your node config  
2. Edit `terraform/talos-cluster/credentials.auto.tfvars` with Proxmox secrets
3. Run the [Complete Workflow](#-complete-workflow) commands below

**First time? Follow the detailed [Setup Guide](#%EF%B8%8F-setup-guide) below.**

## ⚙️ Setup Guide

### 1. Proxmox API Setup

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



### 2. Terraform Configuration

The Terraform setup is fully declarative with all node configurations managed in one place.

1. **Navigate to the Terraform directory:**
   ```bash
   cd iac/terraform/talos-cluster/
   ```

2. **Set up credentials:**
   Create a `credentials.auto.tfvars` file (automatically loaded by Terraform). This file is git-ignored and contains your Proxmox secrets:
   ```hcl
   # iac/terraform/talos-cluster/credentials.auto.tfvars
   proxmox_api_url      = "https://<your-proxmox-ip>:8006/api2/json"
   proxmox_node         = "<your-proxmox-node-name>"
   proxmox_api_token    = "<your-api-token-id>=<your-api-token-secret>"
   proxmox_pool         = ""
   proxmox_ssh_password = "<your-proxmox-ssh-password>"
   ```

3. **Configure your cluster nodes:**
   Edit `cluster.auto.tfvars` with your node configurations:
   ```hcl
   nodes = [
    {
      name        = "talos-prod-control-01"
      vmid        = 8000
      role        = "controlplane"
      ip          = "192.168.10.100"
      mac_address = "AC:24:21:A4:B2:97"
    },
    {
      name        = "talos-prod-worker-01"
      vmid        = 8001
      role        = "worker"
      ip          = "192.168.10.111"
      mac_address = "AC:24:21:4C:99:A1"
    },
    {
      name        = "talos-prod-worker-02"
      vmid        = 8002
      role        = "worker"
      ip          = "192.168.10.112"
      mac_address = "AC:24:21:4C:99:A2"
    },
    {
      name        = "talos-prod-gpu-worker-03"
      vmid        = 8003
      role        = "worker-gpu"
      ip          = "192.168.10.113"
      mac_address = "AC:24:21:AD:82:A3"
    }
   ]
   ```

4. **Initialize and apply Terraform:**
   ```bash
   terraform init -upgrade
   terraform plan -out=.tfplan
   terraform apply .tfplan
   ```



### 3. SOPS Setup (Required for talhelper)

talhelper requires encrypted secrets for cluster security:

1. **Generate Age Key (One-time setup):**
   ```bash
   mkdir -p $HOME/.config/sops/age/
   age-keygen -o $HOME/.config/sops/age/keys.txt
   ```

2. **Configure SOPS:**
   Create `.sops.yaml` in the `iac/talos/` directory:
   ```yaml
   ---
   creation_rules:
     - age: >-
         age1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
   Replace the age key with your **public key** from `$HOME/.config/sops/age/keys.txt`.

### 4. Talos Configuration with talhelper


# Generate talenv.yaml from Terraform configuration
in iac folder run `sh ./tfvars-to-talos-env.sh`


```bash
# Navigate to talos directory
cd iac/talos

# Generate and encrypt talhelper secrets
export SOPS_AGE_KEY_FILE=$HOME/.config/sops/age/keys.txt
talhelper gensecret > talsecret.sops.yaml
sops -e -i talsecret.sops.yaml



# Set up environment for SOPS and generate configuration
export SOPS_AGE_KEY_FILE=$HOME/.config/sops/age/keys.txt
talhelper genconfig --env-file talenv.yaml
```



### 5. Bootstrap Talos Cluster

```bash
# Apply configuration to all nodes
# 4. Deploy cluster (first-time deployment requires --insecure flag)

# Then run each command with --insecure flag:
# First, export the generated talosconfig so you can reference it in commands
export TALOSCONFIG="$(pwd)/clusterconfig/talosconfig"

talosctl apply-config --insecure --talosconfig="$TALOSCONFIG" --nodes=192.168.10.100 --file=./clusterconfig/proxmox-talos-prod-cluster-talos-prod-control-01.yaml
talosctl apply-config --insecure --talosconfig="$TALOSCONFIG" --nodes=192.168.10.111 --file=./clusterconfig/proxmox-talos-prod-cluster-talos-prod-worker-01.yaml
talosctl apply-config --insecure --talosconfig="$TALOSCONFIG" --nodes=192.168.10.112 --file=./clusterconfig/proxmox-talos-prod-cluster-talos-prod-worker-02.yaml
talosctl apply-config --insecure --talosconfig="$TALOSCONFIG" --nodes=192.168.10.113 --file=./clusterconfig/proxmox-talos-prod-cluster-talos-prod-gpu-worker-03.yaml

# Set up talosconfig for cluster access (already exported above)
# To avoid overwriting your global talos config (~/.talos/config), keep the `TALOSCONFIG` environment variable in this session.
# 192.168.10.100 is the control plane node you bootstrapped earlier
talosctl kubeconfig --talosconfig="$TALOSCONFIG" -n 192.168.10.100 > ~/.kube/config

# For convenience, you can add this export command to your shell's profile 
# (e.g., ~/.zshrc, ~/.bashrc) to make it permanent for new sessions.

# Bootstrap the cluster (first control plane only)
talhelper gencommand bootstrap
talosctl bootstrap --talosconfig="$TALOSCONFIG" --nodes=192.168.10.100

# Get kubeconfig
talhelper gencommand kubeconfig 

# Verify nodes are up
kubectl get nodes
```

### 6. Install Cilium CNI

**Important:** Take note of the Ethernet device. Devices might be named `ens`, `eth`, or `enp` depending on your system.

```bash
cilium install \
  --version 1.18.1 \
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

--- 

App Deployment 

### Setting Up Lens (Optional but Recommended)

1. Install Lens from https://k8slens.dev/
2. Get the kubeconfig:
   - Run: `kubectl config view --raw > kubeconfig.yaml`
3. When adding to Lens:
   - Replace the server URL with your K3s node IP
   - Example: `server: https://192.168.10.202:6443`
4. Save and connect

### 4. GitOps Setup (Argo CD - Part 1/2)
```bash
# Install Helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# Gateway API CRDs
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.3.0/standard-install.yaml
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.3.0/experimental-install.yaml

# Argo CD Bootstrap
kubectl create namespace argocd
kubectl kustomize --enable-helm infrastructure/controllers/argocd | kubectl apply -f -
kubectl apply -f infrastructure/controllers/argocd/projects.yaml

# Wait for Argo CD
kubectl wait --for=condition=Ready pod -l app.kubernetes.io/name=argocd-server -n argocd --timeout=300s

# Get initial password (change immediately!)
ARGO_PASS=$(kubectl get secret argocd-initial-admin-secret -n argocd -o jsonpath="{.data.password}" | base64 -d)
echo "Initial Argo CD password: $ARGO_PASS"

#Generate a New Password:
Use a bcrypt hash generator tool (such as https://www.browserling.com/tools/bcrypt) to create a new bcrypt hash for the password.
Update the argocd-secret secret with the new bcrypt hash.
kubectl -n argocd patch secret argocd-secret -p '{"stringData": { "admin.password": "$2a$10$rgDBwhzr0ygDfH6scxkdddddx3cd612Cutw1Xu1X3a.kVrRq", "admin.passwordMtime": "'$(date +%FT%T%Z)'" }}'
```

### 5. Monitoring Setup (kube-prometheus-stack with Custom Dashboards)

The monitoring stack uses kube-prometheus-stack Helm chart deployed via Argo CD, providing comprehensive Kubernetes and application monitoring with custom dashboard support.

**Components Included:**
- **Prometheus**: Metrics collection and storage with increased memory (1Gi) for cluster monitoring
- **Grafana**: Visualization with custom dashboard auto-discovery via sidecar
- **AlertManager**: Alert handling and routing
- **Node Exporter**: Node-level metrics collection
- **kube-state-metrics**: Kubernetes object state metrics

**Custom Dashboard Management:**
- Dashboard ConfigMaps are automatically discovered using `grafana_dashboard: "1"` labels
- Stored in `monitoring/kube-prometheus-stack/dashboards/` directory
- Includes pre-configured K3s cluster overview and community dashboards
- Tagged with "custom" for easy identification in Grafana

**Access URLs (after DNS/Gateway setup):**
- **Grafana**: `https://grafana.yourdomain.xyz` (default: `admin` / `admin`)
- **Prometheus**: `https://prometheus.yourdomain.xyz`
- **AlertManager**: `https://alertmanager.yourdomain.xyz`

**Storage (with Longhorn):**
- **Prometheus**: `2Gi` with 7-day retention
- **Grafana**: `1Gi` for dashboards and config
- **AlertManager**: `512Mi` for alert state

**For detailed dashboard management, see [`monitoring/kube-prometheus-stack/dashboards/README.md`](monitoring/kube-prometheus-stack/dashboards/README.md).**

---

To add or remove monitoring components, edit `monitoring/monitoring-components-appset.yaml` and comment/uncomment the desired subfolders. Each component is managed as a separate ArgoCD Application in its own namespace.

## 🔒 Security Setup

### Cloudflare Integration

You'll need to create two secrets for Cloudflare integration:
1. DNS API Token for cert-manager (DNS validation)
2. Tunnel credentials for cloudflared (Tunnel connectivity)

#### 1. DNS API Token 🔑
```bash
# REQUIRED BROWSER STEPS FIRST:
# Navigate to Cloudflare Dashboard:
# 1. Profile > API Tokens
# 2. Create Token
# 3. Use "Edit zone DNS" template
# 4. Configure permissions:
#    - Zone - DNS - Edit
#    - Zone - Zone - Read
# 5. Set zone resources to your domain
# 6. Copy the token and your Cloudflare account email

# Set credentials - NEVER COMMIT THESE!
export CLOUDFLARE_API_TOKEN="your-api-token-here"
export CLOUDFLARE_EMAIL="your-cloudflare-email"
export DOMAIN="yourdomain.com"
export TUNNEL_NAME="k3s-cluster"  # Must match config.yaml
```

#### 2. Cloudflare Tunnel 🌐
```bash
# First-time setup only
# ---------------------
# Install cloudflared
# Linux:
wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared-linux-amd64.deb
# macOS:
brew install cloudflare/cloudflare/cloudflared

# Authenticate (opens browser)
cloudflared tunnel login

# Generate credentials (run from $HOME)
cloudflared tunnel create $TUNNEL_NAME
cloudflared tunnel token --cred-file tunnel-creds.json $TUNNEL_NAME

export DOMAIN="yourdomain.com"
export TUNNEL_NAME="k3s-cluster"  # This should match the name in your config.yaml

# Create namespace for cloudflared
kubectl create namespace cloudflared

# Create Kubernetes secret
kubectl create secret generic tunnel-credentials \
  --namespace=cloudflared \
  --from-file=credentials.json=tunnel-creds.json

# SECURITY: Destroy local credentials ( Optional )
rm -v tunnel-creds.json && echo "Credentials file removed"

# Configure DNS
TUNNEL_ID=$(cloudflared tunnel list | grep $TUNNEL_NAME | awk '{print $1}')
cloudflared tunnel route dns $TUNNEL_ID "*.$DOMAIN"
```

### Certificate Management
```bash
# Create cert-manager secrets
kubectl create namespace cert-manager
kubectl create secret generic cloudflare-api-token -n cert-manager \
  --from-literal=api-token=$CLOUDFLARE_API_TOKEN \
  --from-literal=email=$CLOUDFLARE_EMAIL

# Verify secrets
kubectl get secret cloudflare-api-token -n cert-manager -o jsonpath='{.data.email}' | base64 -d
kubectl get secret cloudflare-api-token -n cert-manager -o jsonpath='{.data.api-token}' | base64 -d
```

## 🛠️ Final Deployment
```bash
# Apply infrastructure components
# Run from root of git repo
kubectl apply -f infrastructure/controllers/argocd/projects.yaml -n argocd
kubectl apply -f infrastructure/infrastructure-components-appset.yaml -n argocd

# Wait for core services (5-30 mins for certs)
kubectl wait --for=condition=Available deployment -l type=infrastructure --all-namespaces --timeout=1800s

# Deploy monitoring stack
kubectl apply -f monitoring/monitoring-components-appset.yaml -n argocd

# Wait for monitoring components to initialize
echo "Waiting for kube-prometheus-stack to become ready... (this may take a few minutes)"
kubectl wait --for=condition=Available deployment -l app.kubernetes.io/name=grafana -n kube-prometheus-stack --timeout=600s
kubectl wait --for=condition=Available deployment -l app.kubernetes.io/name=kube-state-metrics -n kube-prometheus-stack --timeout=600s
kubectl wait --for=condition=Ready statefulset -l app.kubernetes.io/name=prometheus -n kube-prometheus-stack --timeout=600s

# Deploy applications
kubectl apply -f my-apps/myapplications-appset.yaml
```

## 🔍 Verification
```bash
# Cluster status
kubectl get pods -A --sort-by=.metadata.creationTimestamp

# Argo CD status
kubectl get applications -n argocd -o wide

# Monitoring stack status
kubectl get pods -n kube-prometheus-stack

# Certificate checks
kubectl get certificates -A
kubectl describe clusterissuer cloudflare-cluster-issuer

# Network validation
cilium status --verbose
cilium connectivity test --all-flows
```

**Access Endpoints:**
- Argo CD: `https://argocd.$DOMAIN`
- Grafana: `https://grafana.$DOMAIN`
- Prometheus: `https://prometheus.$DOMAIN`
- AlertManager: `https://alertmanager.$DOMAIN`
- ProxiTok: `https://proxitok.$DOMAIN`
- SearXNG: `https://search.$DOMAIN`
- LibReddit: `https://reddit.$DOMAIN`

## 📦 Included Applications

| Category       | Components                          |
|----------------|-------------------------------------|
| **Monitoring** | Prometheus, Grafana, Loki, Promtail |
| **Privacy**    | ProxiTok, SearXNG, LibReddit        |
| **Infra**      | Cilium, Gateway API, Cloudflared    |
| **Storage**    | OpenEBS                             |
| **Security**   | cert-manager, Argo CD Projects      |

## 🤝 Contributing
Contributions welcome! Please:
1. Maintain existing comment structure
2. Keep all warnings/security notes
3. Open issue before major changes

## 📝 License
MIT License - Full text in [LICENSE](LICENSE)

## 🔧 Troubleshooting

**Common Issues:**
```bash
# Certificates not issuing
kubectl logs -n cert-manager -l app=cert-manager

# Tunnel connection failures
cloudflared tunnel info $TUNNEL_NAME
kubectl logs -n cloudflared -l app=cloudflared

# Cilium connectivity issues
cilium status --verbose
cilium hubble ui

# L2 Announcement Problems
ip -o link show | awk -F': ' '{print $2}'  # Verify node interfaces
kubectl describe CiliumL2AnnouncementPolicy -n kube-system
```

**Monitoring Stack Issues:**
```bash
# Check pod status in the kube-prometheus-stack namespace
kubectl get pods -n kube-prometheus-stack

# If pods are stuck, check the Argo CD UI for sync errors.
# Look at the 'kube-prometheus-stack' application.

# Describe a pod to see its events and find out why it's not starting
kubectl describe pod <pod-name> -n kube-prometheus-stack

# Check logs for specific monitoring components
kubectl logs -l app.kubernetes.io/name=grafana -n kube-prometheus-stack
kubectl logs -l app.kubernetes.io/name=prometheus -n kube-prometheus-stack

# Check Grafana sidecar for dashboard loading issues
kubectl logs -l app.kubernetes.io/name=grafana -c grafana-sc-dashboard -n kube-prometheus-stack

# Verify custom dashboard ConfigMaps are labeled correctly
kubectl get configmaps -n kube-prometheus-stack -l grafana_dashboard=1
```

**Multi-Attach Volume Errors (ReadWriteOnce Issues):**
```bash
# PROBLEM: Multiple pods trying to mount the same ReadWriteOnce (RWO) volume
# SYMPTOMS: Pods stuck in Init:0/2 or Pending state with multi-attach errors
# COMMON CAUSE: ArgoCD rolling updates with Replace=true causing resource conflicts

# Check for stuck pods and volume attachment issues
kubectl get pods -A | grep -E "(Init|Pending|ContainerCreating)"
kubectl get volumeattachments
kubectl get pvc -A

# Identify the problematic pod and PVC
kubectl describe pod <stuck-pod-name> -n <namespace>

# IMMEDIATE FIX: Force delete the stuck pod (temporary solution)
kubectl delete pod <stuck-pod-name> -n <namespace> --force --grace-period=0

# PERMANENT SOLUTION: Fix deployment strategies for RWO volumes
# 1. Update ApplicationSet sync options (remove Replace=true)
# 2. Set deployment strategy to 'Recreate' for apps using RWO volumes
# 3. Add RespectIgnoreDifferences=true to prevent unnecessary syncs

# Verify fixes are applied:
# Check ApplicationSet sync options
kubectl get applicationset -n argocd -o yaml | grep -A 10 syncOptions

# Check deployment strategies for RWO volume users
kubectl get deployment grafana -n kube-prometheus-stack -o jsonpath='{.spec.strategy.type}'
kubectl get deployment proxitok-web -n proxitok -o jsonpath='{.spec.strategy.type}'
kubectl get deployment homepage-dashboard -n homepage-dashboard -o jsonpath='{.spec.strategy.type}'
kubectl get deployment redis -n searxng -o jsonpath='{.spec.strategy.type}'

# All should return 'Recreate' for apps using persistent volumes
```

**Key Prevention Strategies:**
- **Use `Recreate` deployment strategy** for any app with ReadWriteOnce volumes
- **Remove `Replace=true`** from ArgoCD ApplicationSet sync options
- **Add `RespectIgnoreDifferences=true`** to prevent unnecessary rolling updates
- **Use `ApplyOutOfSyncOnly=true`** to only update resources that are actually out of sync

**Specific Changes Made to Fix Multi-Attach Errors:**

1. **ApplicationSet Sync Options Updated:**
   ```yaml
   # REMOVED from all ApplicationSets:
   # - Replace=true  # This was causing resource deletion/recreation
   
   # ADDED to all ApplicationSets:
   syncOptions:
     - RespectIgnoreDifferences=true  # Prevents unnecessary syncs
     - ApplyOutOfSyncOnly=true       # Only sync out-of-sync resources
   ```

2. **Deployment Strategy Changes for RWO Volume Apps:**
   ```yaml
   # monitoring/kube-prometheus-stack/values.yaml
   grafana:
     deploymentStrategy:
       type: Recreate  # Added to prevent multi-attach during updates
   
   # my-apps/homepage-dashboard/deployment.yaml
   spec:
     strategy:
       type: Recreate  # Added for RWO volume safety
   
   # my-apps/proxitok/deployment.yaml  
   spec:
     strategy:
       type: Recreate  # Added for cache PVC
   
   # my-apps/searxng/redis.yaml
   spec:
     strategy:
       type: Recreate  # Added for Redis data persistence
   ```



**Why These Changes Work:**
- **`Recreate` vs `RollingUpdate`**: With ReadWriteOnce volumes, `RollingUpdate` tries to start new pods before old ones terminate, causing volume conflicts. `Recreate` ensures complete pod termination first.
- **Removing `Replace=true`**: This ArgoCD option deletes and recreates all resources during sync, triggering unnecessary rolling updates and volume conflicts.
- **`RespectIgnoreDifferences=true`**: Prevents ArgoCD from syncing minor differences that don't affect functionality, reducing unnecessary pod restarts.
- **Sync Wave Ordering**: Monitoring components use sync wave "1" to deploy after infrastructure (wave "-2" and "0"), ensuring proper resource availability.

**Critical L2 Note:**
If LoadBalancer IPs aren't advertising properly:
1. Verify physical interface name matches in CiliumL2AnnouncementPolicy
2. Check interface exists on all nodes: `ip link show dev enp1s0`
3. Ensure Cilium pods are running: `kubectl get pods -n kube-system -l k8s-app=cilium`

**Longhorn Volume Mount Issues:**
```bash
# PROBLEM: Volumes fail to mount with "device busy" or multipath conflicts
# COMMON CAUSE: Linux multipath daemon interfering with Longhorn device management

# Check if multipathd is running (often enabled by default on Ubuntu/Debian)
systemctl status multipathd

# SOLUTION: Disable multipath daemon on all nodes
sudo systemctl disable --now multipathd

# Verify it's stopped
systemctl is-active multipathd  # Should return "inactive"

# After disabling multipathd, restart kubelet to clear any cached device state
sudo systemctl restart k3s  # For K3s
# OR
sudo systemctl restart kubelet  # For standard Kubernetes

# Check Longhorn volume status after restart
kubectl get volumes -n longhorn-system
kubectl get pods -n longhorn-system

# Reference: https://longhorn.io/kb/troubleshooting-volume-with-multipath/
```