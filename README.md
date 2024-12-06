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
curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION="v1.31.3-rc2+k3s1" \
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
    This guide uses a simple, straightforward approach to Kubernetes storage that feels like managing regular directories on your computer.

### Benefits of Using ZFS
    While we're using ZFS, these same principles work with any filesystem. The key is making your data easy to find and manage, just like organizing files on your computer.

## 3.1 Prepare Your Storage Location

First, let's set up our storage with the right permissions so both you and Kubernetes can work with the files:

### Step 1: Create the Main Storage Directory
```
sudo mkdir -p /datapool/kubernetes
```

### Step 2: Create a Special Group for Storage Access
```
sudo groupadd storage-access
```
Add yourself to this group:
```
sudo usermod -a -G storage-access yourusername
```

### Step 3: Set Up Permissions

Set up the right permissions:
```
sudo chown root:storage-access /datapool/kubernetes
sudo chmod 2775 /datapool/kubernetes
```
This setup means both you and Kubernetes can read and write files, while keeping your data secure.

### 3 ( Extra )

Create a special group that will have access to the storage
```
sudo groupadd storage-access
```
Add yourself to this group (replace 'yourusername' with your username)
```
sudo usermod -a -G storage-access yourusername
```
Set up the right permissions
```
sudo chown root:storage-access /datapool/kubernetes
sudo chmod 2775 /datapool/kubernetes
```
You'll need to log out and back in for the new group to take effect
Let's understand these permissions (2775):
```
The '2' means new files will automatically belong to the storage-access group
The first '7' gives the owner (root) full access
The second '7' gives your group full access
The '5' lets others see the files exist but not modify them
```
This setup means both you and Kubernetes can read and write files, while keeping your data secure.

## 3.2 Create the Storage Class

Now we'll tell Kubernetes how to manage storage. We're using the built-in local storage system because it's simple and predictable:

### Create a Local Storage Class YAML File
```
local-storage-class.yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
name: local-storage
provisioner: kubernetes.io/no-provisioner  # Manages storage directly
reclaimPolicy: Retain                      # Keeps your data safe
volumeBindingMode: WaitForFirstConsumer    # Assigns storage when needed

Apply this to your cluster:
```

### A PersistentVolume (PV)

```
apiVersion: v1
kind: PersistentVolume
metadata:
name: myapp-data-pv
spec:
capacity:
storage: 100Gi
accessModes:
- ReadWriteOnce
persistentVolumeReclaimPolicy: Retain
storageClassName: local-storage
local:
path: /datapool/kubernetes/myapp/data    # Your actual data location
nodeAffinity:
required:
nodeSelectorTerms:
- matchExpressions:
- key: kubernetes.io/hostname
operator: In
values:
- your-node-name    # Your actual node name
```

### A PersistentVolumeClaim (PVC)

```
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
name: myapp-data-pvc
namespace: myapp
spec:
storageClassName: local-storage
accessModes:
- ReadWriteOnce
resources:
requests:
storage: 100Gi
volumeName: myapp-data-pv    # Links to the PV above
```

## 3.4 How Your Storage Will Look

Your storage will be organized like a well-structured file system:

*   `datapool/kubernetes/`
    *   `ollama/`          # Each app gets its own directory
        *   `models/`               # Store AI models here
        *   `cache/`               # Temporary files here
    *   `nginx/`
        *   `config/`              # Configuration files
        *   `data/`               # Website files
    *   `postgres/`
        *   `data/`               # Database files

This organization means:

*   You can find your files easily
*   Backing up is simple (just copy the folders you need)
*   Your data stays safe even if you rebuild your cluster
*   You can manage files directly from your computer
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
     "admin.password": "$2a$10$KjM2xxxxredactedmry6.rfFF0IJfCWuaD2XJ/2sr6oQGcszf8cO",
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