# K3s Cluster Bootstrap

A production-ready Kubernetes cluster setup using K3s, focusing on security and GitOps practices.

## Prerequisites

```shell
# System dependencies
sudo apt install zfsutils-linux nfs-kernel-server cifs-utils open-iscsi
sudo apt install --reinstall zfs-dkms

# Install 1Password CLI
# Follow instructions at: https://1password.com/downloads/command-line/

# Fix kubeconfig permissions (after k3s install)
chmod 600 ~/.kube/config
```

## 1. Initial Cluster Setup

```shell
export SETUP_NODEIP=192.168.10.11
export SETUP_CLUSTERTOKEN=randomtokensecret123456

# Install K3s
curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION="v1.32.0-rc1+k3s1" \
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
echo "export KUBECONFIG=$HOME/.kube/config" >> $HOME/.bashrc
source $HOME/.bashrc
```

# Install Cilium CLI
```
CILIUM_CLI_VERSION=$(curl -s https://raw.githubusercontent.com/cilium/cilium-cli/main/stable.txt)

CLI_ARCH=amd64

curl -L --fail --remote-name-all https://github.com/cilium/cilium-cli/releases/download/${CILIUM_CLI_VERSION}/cilium-linux-${CLI_ARCH}.tar.gz

sudo tar xzvfC cilium-linux-${CLI_ARCH}.tar.gz /usr/local/bin
rm cilium-linux-${CLI_ARCH}.tar.gz
```
# Install Cilium
```
API_SERVER_IP=192.168.10.11
API_SERVER_PORT=6443
cilium install \
  --version 1.16.4 \
  --set k8sServiceHost=${API_SERVER_IP} \
  --set k8sServicePort=${API_SERVER_PORT} \
  --set kubeProxyReplacement=true \
  --helm-set=operator.replicas=1
```

# Verify Cilium installation
```cilium status```

## 2. Secrets Setup (Required before ArgoCD)

```shell
# Generate Connect credentials
op connect server create  # Creates 1password-credentials.json

# Store token for reuse
export CONNECT_TOKEN="your-1password-connect-token"

# Create required secrets
kubectl create namespace 1passwordconnect

#BASE64 the json first!!!
kubectl create secret generic 1password-credentials \
  --from-file=1password-credentials.json=/path/to/1password-credentials.json \
  --namespace 1passwordconnect

  kubectl create secret generic 1password-credentials \
  --from-file=1password-credentials.json=credentials.base64  \
  --namespace 1passwordconnect


kubectl create secret generic 1password-operator-token \
  --from-literal=token=$CONNECT_TOKEN \
  --namespace 1passwordconnect

# Create external-secrets token (same token as 1password-operator-token)
kubectl create namespace external-secrets
kubectl create secret generic 1passwordconnect \
  --from-literal=token=$CONNECT_TOKEN \
  --namespace external-secrets
```

## 3. Required 1Password Vault Items

Create these items in your 1Password vault before proceeding:

1. `cert-manager-proxmox`:
   - Field: `token` (Cloudflare API token)

2. `cloudflared-proxmox`:
   - Field: `tunnel-credentials` (JSON format)
   ```json
   {
     "AccountTag": "your-account-tag",
     "TunnelSecret": "your-tunnel-secret",
     "TunnelID": "your-tunnel-id"
   }
   ```

3. `external-secrets`:
   - Field: `token` (same as $CONNECT_TOKEN)


# Storage Setup

## Overview
This cluster uses a hybrid storage approach:
1. Local storage for application configs and small datasets
2. SMB storage for large media files

## Storage Types

### 1. Local Storage
Used for application configurations and smaller datasets. All stored under `/datapool/kubernetes/`:

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

### 2. SMB Storage
Used for large media files, mounted via SMB CSI driver:
- Jellyfin media: `//192.168.10.8/jellyfin-media`
- Frigate recordings: `//192.168.10.8/frigate`

## Storage Setup Steps

### 1. Prepare Local Storage

```bash
# Clone the repository if you haven't already
git clone https://github.com/yourusername/k3s-argocd-proxmox.git
cd k3s-argocd-proxmox

# Make the script executable
chmod +x helper-scripts/setup-storage.sh

# Run the script to create all necessary directories
sudo ./helper-scripts/setup-storage.sh

# Set up storage access group
sudo groupadd storage-access
sudo usermod -a -G storage-access $USER
sudo chown root:storage-access /datapool/kubernetes
sudo chmod 2775 /datapool/kubernetes
```

### 2. Set up SMB Storage

```bash
# Create SMB credentials secret
kubectl create namespace csi-driver-smb

kubectl create secret generic smbcreds \
  --from-literal username="your-username" \
  --from-literal password="your-password" \
  -n csi-driver-smb
```

## Storage Configuration Examples

### 1. Local Storage Class

```yaml
# local-storage-class.yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: local-storage
provisioner: kubernetes.io/no-provisioner
volumeBindingMode: WaitForFirstConsumer
reclaimPolicy: Retain
```

### 2. Example Configurations

#### Local Storage (e.g., Sonarr Config)
```yaml
# PV
apiVersion: v1
kind: PersistentVolume
metadata:
  name: sonarr-config-pv
  labels:
    app: sonarr
    type: config
spec:
  capacity:
    storage: 10Gi
  accessModes:
    - ReadWriteOnce
  persistentVolumeReclaimPolicy: Retain
  storageClassName: local-storage
  local:
    path: /datapool/kubernetes/arr/sonarr/config
  nodeAffinity:
    required:
      nodeSelectorTerms:
      - matchExpressions:
        - key: kubernetes.io/hostname
          operator: In
          values:
          - vanillax-ai

# PVC
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: sonarr-config
  namespace: arr
  labels:
    app: sonarr
    type: config
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
  storageClassName: local-storage
  selector:
    matchLabels:
      app: sonarr
      type: config
```

#### SMB Storage (e.g., Jellyfin Media)
```yaml
# PV
apiVersion: v1
kind: PersistentVolume
metadata:
  name: jellyfin-media
spec:
  capacity:
    storage: 1Gi  # Minimal size since it's just for mounting
  accessModes:
    - ReadWriteMany
  persistentVolumeReclaimPolicy: Retain
  mountOptions:
    - dir_mode=0777
    - file_mode=0777
    - uid=1000
    - gid=1000
    - cache=strict
    - nosharesock
  csi:
    driver: smb.csi.k8s.io
    volumeHandle: jellyfin-media-volume
    volumeAttributes:
      source: "//192.168.10.8/jellyfin-media"
    nodeStageSecretRef:
      name: smbcreds
      namespace: csi-driver-smb

# PVC
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: jellyfin-media
  namespace: jellyfin
spec:
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 1Gi
  volumeName: jellyfin-media
  storageClassName: ""
```

## Storage Best Practices

1. Local Storage:
   - Use for application configs and small datasets
   - Always include proper labels and selectors
   - Use `ReadWriteOnce` access mode
   - Set node affinity to ensure proper binding

2. SMB Storage:
   - Use for large media files that need sharing
   - Always use `ReadWriteMany` access mode
   - Include proper mount options for permissions
   - Use minimal storage request (1Gi) since it's just for mounting

3. General:
   - Always back up data before making storage changes
   - Use descriptive names for PVs and PVCs
   - Include proper namespace in PVCs
   - Set appropriate permissions on local directories

## 4. Apply Infrastructure


# Install Gateway API CRDs
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.2.0/experimental-install.yaml

# Install Argo CD
kubectl kustomize --enable-helm infra/controllers/argocd | kubectl apply -f -

# Get initial admin password (if needed)
kubectl -n argocd get secret argocd-initial-admin-secret -ojsonpath="{.data.password}" |

or Set it 

#bcrypt the password
 kubectl -n argocd patch secret argocd-secret   -p '{"stringData": {
     "admin.password": "$2a$12$ltMQCF4cVDVARdelQX/rmeHrF64A8fypy8WkpmmAlScprRSXnyzpi",
       "admin.passwordMtime": "'$(date +%FT%T%Z)'"
    }}'

```shell
# Apply all infrastructure components via ArgoCD
kubectl apply -k infra/
```

kubectl apply -k sets

# Apply full infrastructure
kubectl kustomize infra | kubectl apply -f -

## 5. Verify Setup

```shell
# Check 1Password Connect
kubectl get pods -n 1passwordconnect
kubectl get secret 1password-credentials -n 1passwordconnect

# Check External Secrets
kubectl get externalsecret -A
kubectl get clustersecretstore 1password -n external-secrets

# Check specific secrets
kubectl get secret cloudflare-api-token -n cert-manager
kubectl get secret tunnel-credentials -n cloudflared

# Check for errors
kubectl logs -n 1passwordconnect -l app=onepassword-connect
```



# Troubleshooting

If secrets aren't syncing:
1. Verify 1Password Connect is running
2. Check vault items exist with correct field names
3. Check External Secrets operator logs
4. Verify ClusterSecretStore is ready