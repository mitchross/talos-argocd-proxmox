# K3s Cluster Bootstrap

A production-ready Kubernetes cluster setup using K3s, focusing on security and GitOps practices.

## Prerequisites

```bash
# System dependencies
sudo apt install zfsutils-linux nfs-kernel-server cifs-utils open-iscsi
sudo apt install --reinstall zfs-dkms

# Install 1Password CLI
# Follow instructions at: https://1password.com/downloads/command-line/
```

## 1. Initial Cluster Setup

```bash
# Set environment variables
export SETUP_NODEIP=192.168.10.11
export SETUP_CLUSTERTOKEN=randomtokensecret123456

# Install K3s
curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION="v1.31.4+k3s1" \
  INSTALL_K3S_EXEC="--node-ip $SETUP_NODEIP \
  --disable=flannel,local-storage,metrics-server,servicelb,traefik \
  --flannel-backend='none' \
  --disable-network-policy \
  --disable-cloud-controller \
  --disable-kube-proxy" \
  K3S_TOKEN=$SETUP_CLUSTERTOKEN \
  K3S_KUBECONFIG_MODE=644 sh -s -

# Setup kubeconfig
mkdir -p $HOME/.kube
sudo cp -i /etc/rancher/k3s/k3s.yaml $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config
chmod 600 $HOME/.kube/config
echo "export KUBECONFIG=$HOME/.kube/config" >> $HOME/.bashrc
source $HOME/.bashrc
```

## 2. Network Setup (Cilium)

```bash
# Install Cilium CLI
CILIUM_CLI_VERSION=$(curl -s https://raw.githubusercontent.com/cilium/cilium-cli/main/stable.txt)
CLI_ARCH=amd64
curl -L --fail --remote-name-all https://github.com/cilium/cilium-cli/releases/download/${CILIUM_CLI_VERSION}/cilium-linux-${CLI_ARCH}.tar.gz
sudo tar xzvfC cilium-linux-${CLI_ARCH}.tar.gz /usr/local/bin
rm cilium-linux-${CLI_ARCH}.tar.gz

# Install Cilium
API_SERVER_IP=192.168.10.11
API_SERVER_PORT=6443
cilium install \
  --version 1.16.5 \
  --set k8sServiceHost=${API_SERVER_IP} \
  --set k8sServicePort=${API_SERVER_PORT} \
  --set kubeProxyReplacement=true \
  --helm-set=operator.replicas=1

# Verify installation
cilium status
```

## 3. Secrets Management

### 3.1 Setup 1Password Connect

```bash
# Generate Connect credentials
op connect server create  # Creates 1password-credentials.json

# Store token for reuse
export CONNECT_TOKEN="your-1password-connect-token"

# Create namespaces
kubectl create namespace 1passwordconnect
kubectl create namespace external-secrets

# Create secrets
kubectl create secret generic 1password-credentials \
  --from-file=1password-credentials.json=credentials.base64 \
  --namespace 1passwordconnect

kubectl create secret generic 1password-operator-token \
  --from-literal=token=$CONNECT_TOKEN \
  --namespace 1passwordconnect

kubectl create secret generic 1passwordconnect \
  --from-literal=token=$CONNECT_TOKEN \
  --namespace external-secrets
```

### 3.2 Required 1Password Vault Items

Create these items in your 1Password vault:

1. `cert-manager-proxmox`:
   - Field: `token` (Cloudflare API token)

2. `cloudflared-proxmox`:
   ```json
   {
     "AccountTag": "your-account-tag",
     "TunnelSecret": "your-tunnel-secret",
     "TunnelID": "your-tunnel-id"
   }
   ```

3. `external-secrets`:
   - Field: `token` (same as $CONNECT_TOKEN)

4. `smb-creds`:
   - Field: `username` (SMB username)
   - Field: `password` (SMB password)

## 4. Infrastructure Setup

### 4.1 Bootstrap ArgoCD

ArgoCD is initially installed via CLI, then manages itself through GitOps:

```bash
# Install Gateway API CRDs (required for Cilium)
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.2.0/experimental-install.yaml

# Bootstrap ArgoCD installation
kubectl kustomize --enable-helm infra/controllers/argocd | kubectl apply -f -

# Wait for ArgoCD to be ready
kubectl wait --for=condition=available deployment -l app.kubernetes.io/name=argocd-server -n argocd --timeout=300s

# Set admin password (optional)
kubectl -n argocd patch secret argocd-secret -p '{"stringData": {
    "admin.password": "$2a$12$ltMQCF4cVDVARdelQX/rmeHrF64A8fypy8WkpmmAlScprRSXnyzpi",
    "admin.passwordMtime": "'$(date +%FT%T%Z)'"
}}'

# Verify ArgoCD is running
kubectl get pods -n argocd
```

### 4.2 Core Infrastructure

Now we set up ArgoCD to manage all components (including itself):

```bash
# Apply core infrastructure (including ArgoCD's own configuration)
kubectl apply -k infra/

# Verify applications are created
kubectl get application -A

# Wait for all applications to sync
kubectl get application -A -w

# Note: ArgoCD will now manage its own configuration through GitOps
# Any changes to ArgoCD should be made through the infra/controllers/argocd directory
```

### 4.3 Application Sets

After core infrastructure is ready:

```bash
# Apply application sets
kubectl apply -k sets/

# Verify application sets are created
kubectl get applicationset -A

# Monitor application creation
kubectl get application -A -w
```

### 4.4 Verify Infrastructure

```bash
# Check ArgoCD status
kubectl get pods -n argocd
kubectl get application -A

# Check sync status
argocd app list  # If argocd CLI is installed
# or
kubectl get application -A -o custom-columns=NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status

# Check all applications are healthy
kubectl get application -A --no-headers | awk '$3 != "Healthy" || $2 != "Synced" {print}'
```

## 5. Storage Setup

### 5.1 Overview
This cluster uses a hybrid storage approach:
1. Local storage for application configs and small datasets
2. SMB storage for large media files

### 5.2 Storage Naming Conventions

All storage configurations follow these naming rules:
1. PersistentVolumes end with `-pv` (e.g., `app-storage-pv`)
2. PersistentVolumeClaims end with `-pvc` (e.g., `app-storage-pvc`)
3. Base names match between PV and PVC for clarity
4. All PVs and PVCs must have labels for binding

Example configuration:
```yaml
# PV configuration
apiVersion: v1
kind: PersistentVolume
metadata:
  name: app-storage-pv    # Ends with -pv
  labels:                 # Required labels
    app: myapp
    type: storage
spec:
  # ... rest of PV spec

---
# PVC configuration
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: app-storage-pvc   # Ends with -pvc
  namespace: myapp        # Required namespace
  labels:                 # Matching labels
    app: myapp
    type: storage
spec:
  # ... rest of PVC spec
```

### 5.3 Directory Structure
```plaintext
/datapool/kubernetes/
├── ai/
│   ├── ollama-models/    # Ollama AI models
│   └── comfyui/         # ComfyUI storage
├── media/
│   └── jellyfin/
│       └── config/      # Jellyfin configuration
├── arr/
│   ├── sonarr/config/   # Sonarr configuration
│   ├── radarr/config/   # Radarr configuration
│   ├── lidarr/config/   # Lidarr configuration
│   └── prowlarr/config/ # Prowlarr configuration
├── home/
│   └── frigate/
│       └── config/      # Frigate configuration
└── privacy/
    ├── proxitok/cache/  # ProxiTok cache
    └── searxng/config/  # SearXNG configuration
```

### 5.4 Setup Steps

1. Clean up existing storage:
```bash
chmod +x helper-scripts/cleanup-storage.sh
./helper-scripts/cleanup-storage.sh
```

2. Create local storage directories:
```bash
chmod +x helper-scripts/setup-storage.sh
./helper-scripts/setup-storage.sh
```

3. Validate storage configurations:
```bash
chmod +x helper-scripts/validate-storage.sh
./helper-scripts/validate-storage.sh
```

4. Apply storage configurations through ArgoCD:
```bash
# Verify storage class is applied by ArgoCD
kubectl get sc local-storage

# Verify SMB credentials from external-secrets
kubectl get secret smbcreds -n csi-driver-smb

# Apply application sets
kubectl apply -k sets/
```

### 5.5 Storage Validation

The `validate-storage.sh` script checks:
1. Proper naming conventions (-pv/-pvc suffixes)
2. Required labels for PV/PVC binding
3. Namespace specifications in PVCs
4. Node affinity in PVs
5. Storage class specifications

Run validation before applying changes:
```bash
./helper-scripts/validate-storage.sh
```

## 6. Verification

```bash
# Check core components
kubectl get pods -A
cilium status

# Check ArgoCD
kubectl get application -A
kubectl get pods -n argocd

# Check secrets management
kubectl get pods -n 1passwordconnect
kubectl get externalsecret -A
kubectl get clustersecretstore 1password -n external-secrets

# Check storage
kubectl get pv,pvc -A
kubectl get sc
```

## Troubleshooting

### Secrets Issues
1. Check 1Password Connect:
```bash
kubectl logs -n 1passwordconnect -l app=onepassword-connect
kubectl get secret 1password-credentials -n 1passwordconnect
```

2. Verify External Secrets:
```bash
kubectl get externalsecret -A
kubectl describe clustersecretstore 1password -n external-secrets
```

### Storage Issues
1. Check PV/PVC status:
```bash
kubectl get pv,pvc -A
kubectl describe pv <pv-name>
kubectl describe pvc <pvc-name> -n <namespace>
```

2. Verify SMB credentials:
```bash
kubectl get secret smbcreds -n csi-driver-smb
kubectl describe pod -n <namespace> | grep -A5 Events
```

3. PVC Binding Issues:
```bash
# Common message: "waiting for first consumer to be created before binding"
# This is NORMAL with WaitForFirstConsumer storage class.
# Verify the deployment that uses the PVC exists:
kubectl get deploy -n <namespace>

# Check if pods are being created:
kubectl get pods -n <namespace>

# Check pod events for volume issues:
kubectl describe pod <pod-name> -n <namespace>
```

Note: Storage binding order matters:
1. PVC is created (status: Pending)
2. Pod requesting the PVC is created
3. Kubernetes selects a node for the Pod
4. PVC binds to PV on the selected node
5. Pod starts with the mounted volume

If you see "waiting for first consumer", verify:
- The deployment/statefulset exists
- The PVC name in the pod spec matches
- The storage class name is correct
- Node affinity rules allow scheduling

### ArgoCD Issues

1. DNS/Network Issues:
```bash
# Check if CoreDNS is running
kubectl get pods -n kube-system -l k8s-app=kube-dns

# Verify DNS resolution from within the cluster
kubectl run dnsutils --image=gcr.io/kubernetes-e2e-test-images/dnsutils:1.3 --rm -it -- bash
# Inside the pod:
nslookup github.com
nslookup kubernetes.default.svc.cluster.local

# Check if Cilium is healthy
cilium status
cilium connectivity test

# Verify ArgoCD can reach GitHub
kubectl exec -it -n argocd deploy/argocd-repo-server -- bash
# Inside the pod:
curl -v https://github.com
```

2. Repository Issues:
```bash
# Check ArgoCD repo-server logs
kubectl logs -n argocd deploy/argocd-repo-server

# Force refresh an application
kubectl patch application <app-name> -n argocd --type merge -p='{"metadata": {"annotations": {"argocd.argoproj.io/refresh": "hard"}}}'

# Restart ArgoCD components if needed
kubectl rollout restart deploy -n argocd argocd-repo-server
kubectl rollout restart deploy -n argocd argocd-server