# 🚀 Bootstrap Guide - Omni & Sidero Proxmox Provider

> Quick start guide for bootstrapping your Kubernetes cluster using Omni and Sidero Proxmox Provider

This guide covers the streamlined bootstrap process when using **Omni** (Sidero's Talos management platform) and the **Sidero Proxmox Provider** instead of manual Talos configuration.

## Prerequisites

Before starting this bootstrap process, ensure you have:

1. **Omni deployed and accessible** - See [Omni Setup Guide](omni/omni/README.md)
2. **Sidero Proxmox Provider configured** - See Proxmox provider documentation
3. **Cluster created in Omni** - Your Talos cluster should be provisioned and healthy in Omni
4. **kubectl access** - Download kubeconfig from Omni UI
5. **Local tools installed**:
   - `kubectl`
   - `kustomize`
   - `cilium` CLI (optional, for verification)
   - `1password` CLI (`op`)

## Bootstrap Process

Once your cluster is provisioned and running via Omni, follow these steps to install the GitOps stack:

### Step 1: Install Cilium CNI

Omni provisions Talos clusters without a CNI pre-installed. Install Cilium manually to get the cluster functional:

```bash
cilium install \
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

**Why these settings?**
- `kubeProxyReplacement=true` - Cilium replaces kube-proxy for better performance
- `gatewayAPI.*` - Enables Kubernetes Gateway API support for modern ingress
- `cgroup.autoMount.enabled=false` - Required for Talos OS
- `k8sServiceHost/Port` - Direct API server access

> **Note:** After ArgoCD is deployed, it will take over Cilium management using **Sync Wave 0** to ensure it's always deployed first, before Longhorn and other components. This prevents race conditions.

### Step 2: Install Gateway API CRDs

Install both standard and experimental Gateway API resources:

```bash

# Apply standard Gateway API CRDs
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.4.0/standard-install.yaml

# Apply experimental features with server-side apply
kubectl apply --server-side -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.4.0/experimental-install.yaml

```

**Verify Cilium is running:**
```bash
cilium status
kubectl get pods -n kube-system -l k8s-app=cilium
```

### Step 3: Pre-Seed 1Password Secrets

This cluster uses [1Password Connect](https://developer.1password.com/docs/connect) and [External Secrets Operator](https://external-secrets.io/) for secret management.

**Create namespaces:**
```bash
kubectl create namespace 1passwordconnect
kubectl create namespace external-secrets
```

**Sign in to 1Password and create secrets:**
```bash
# Authenticate with 1Password
eval $(op signin)

# Export credentials from 1Password
export OP_CREDENTIALS=$(op read op://homelabproxmox/1passwordconnect/1password-credentials.json | base64 | tr -d '\n')
export OP_CONNECT_TOKEN=$(op read 'op://homelabproxmox/1password-operator-token/credential')

# Create Kubernetes secrets for 1Password Connect
kubectl create secret generic 1password-credentials \
  --namespace 1passwordconnect \
  --from-literal=1password-credentials.json="$OP_CREDENTIALS"

kubectl create secret generic 1password-operator-token \
  --namespace 1passwordconnect \
  --from-literal=token="$OP_CONNECT_TOKEN"

kubectl create secret generic 1passwordconnect \
  --namespace external-secrets \
  --from-literal=token="$OP_CONNECT_TOKEN"
```

### Step 4: Bootstrap ArgoCD

Deploy ArgoCD and enable GitOps self-management.

**Option A: Use the Bootstrap Script (Recommended)**

```bash
# Run the bootstrap script
./scripts/bootstrap-argocd.sh
```

This script:
- Creates the ArgoCD namespace
- Installs ArgoCD using Helm (works around kustomize/helm compatibility issues)
- Waits for CRDs and server to be ready
- Applies the root Application to enable self-management
- Shows you how to access the UI and get the admin password

**Option B: Manual Steps**

If you prefer to run commands manually:

```bash
# 1. Create namespace
kubectl apply -f infrastructure/controllers/argocd/ns.yaml

# 2. Install ArgoCD with Helm
helm upgrade --install argocd argo-cd \
  --repo https://argoproj.github.io/argo-helm \
  --version 9.1.3 \
  --namespace argocd \
  --values infrastructure/controllers/argocd/values.yaml \
  --wait \
  --timeout 10m

# 3. Wait for CRDs to be established
kubectl wait --for condition=established --timeout=60s crd/applications.argoproj.io

# 4. Wait for ArgoCD server to be available
kubectl wait --for=condition=Available deployment/argocd-server -n argocd --timeout=300s

# 5. Apply HTTPRoute (if using Gateway API ingress)
kubectl apply -f infrastructure/controllers/argocd/http-route.yaml

# 6. Apply root Application to enable self-management
kubectl apply -f infrastructure/controllers/argocd/root.yaml
```

### Step 5: Verify ArgoCD Deployment

Once ArgoCD is deployed, verify it's working:

```bash
# Check ArgoCD pods are running
kubectl get pods -n argocd

# Check applications are being created
kubectl get applications -n argocd

# View sync waves in action
kubectl get applications -n argocd -o custom-columns=NAME:.metadata.name,WAVE:.metadata.annotations.argocd\\.argoproj\\.io/sync-wave,STATUS:.status.sync.status
```

### Step 6: Access ArgoCD UI (Optional)

1. **Port-forward to ArgoCD UI:**
   ```bash
   kubectl port-forward svc/argocd-server -n argocd 8080:443
   ```

2. **Access ArgoCD:**
   - Open browser to `https://localhost:8080`
   - Login with credentials from ArgoCD secret:
     ```bash
     kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
     ```

3. **Refresh Applications:**
   - Click on the `root` application
   - Click "Refresh" button
   - Watch as ApplicationSets discover and sync all applications

## What Happens Next?

ArgoCD now manages everything from Git using **Sync Waves** to prevent race conditions:

### Deployment Order (Sync Waves)

ArgoCD deploys applications in a specific order to avoid race conditions and SSD thrashing:

| Wave | Component | Purpose | Why This Order? |
|------|-----------|---------|-----------------|
| **0** | **Cilium** | CNI networking | Foundation - everything depends on networking |
| **0** | **1Password Connect** | Secret backend | Required by External Secrets Operator |
| **0** | **External Secrets Operator** | Secret management CRDs | Longhorn needs ExternalSecret CRD for backup credentials |
| **1** | **Longhorn** | Storage layer | Needs networking + secret CRDs; other apps need storage |
| **1** | **Garage** | S3-compatible object storage | Needs storage layer |
| **2** | **Infrastructure** | Core services (cert-manager, GPU operators, databases, etc.) | Depends on networking and storage being ready |
| **3** | **Monitoring** | Prometheus, Grafana, alerts | Monitors the infrastructure |
| **4** | **My-Apps** | User applications | Runs on top of everything else |

**Why Sync Waves Matter:**
- **Prevents race conditions** - Cilium won't be reinstalled while Longhorn is deploying
- **Eliminates SSD thrashing** - Longhorn waits for Cilium + secrets to be fully healthy
- **Ensures stability** - Each layer is healthy before the next begins
- **Proper dependencies** - Apps that need PVCs deploy after Longhorn is ready
- **Secret management** - ExternalSecret CRDs exist before resources try to use them

**What You'll See:**
1. **Wave 0**: Cilium, 1Password Connect, and External Secrets Operator deploy in parallel
2. **Wave 1**: Longhorn and Garage deploy after networking + secrets are ready
3. **Wave 2**: Infrastructure components deploy in parallel
4. **Wave 3**: Monitoring stack deploys
5. **Wave 4**: Your applications deploy last

### Automated GitOps Management

Once sync waves complete:

1. **ArgoCD Self-Management** - ArgoCD manages its own configuration and upgrades
2. **ApplicationSet Discovery** - Scans repository for applications in:
   - `infrastructure/*` - Core cluster components
   - `monitoring/*` - Prometheus, Grafana, etc.
   - `my-apps/*/*` - Your applications
3. **Automatic Sync** - All applications sync from Git automatically
4. **Self-Healing** - ArgoCD maintains desired state from Git

## Verification

Check that everything is running correctly:

```bash
# View all ArgoCD applications
kubectl get applications -n argocd

# Check application sync status
kubectl get applications -n argocd -o wide

# View all pods across namespaces
kubectl get pods -A

# Verify External Secrets are working
kubectl get externalsecret -A

# Check Cilium status
cilium status
```

## Cluster Access

**Download kubeconfig from Omni:**
1. Open Omni UI
2. Navigate to your cluster
3. Click "Download Kubeconfig"
4. Save to `~/.kube/config` or set `KUBECONFIG` environment variable

**Manage nodes via Omni:**
- All node management (upgrades, configuration, patches) is done through Omni UI
- No need for `talosctl` or manual configuration
- Omni handles Talos upgrades and system extensions

## Troubleshooting

### ArgoCD Won't Start

```bash
# Check ArgoCD pods
kubectl get pods -n argocd

# View ArgoCD server logs
kubectl logs -n argocd -l app.kubernetes.io/name=argocd-server

# Check for CRD installation
kubectl get crd applications.argoproj.io
```

### Applications Not Syncing

```bash
# Check ApplicationSets
kubectl get applicationsets -n argocd

# View ApplicationSet status
kubectl describe applicationset infrastructure -n argocd

# Force refresh of root application
kubectl delete application root -n argocd
kubectl apply -f infrastructure/controllers/argocd/root.yaml
```

### Cilium Issues

```bash
# Check Cilium status
cilium status

# View Cilium agent logs
kubectl logs -n kube-system -l k8s-app=cilium

# Verify connectivity
cilium connectivity test
```

### 1Password Secrets Not Working

```bash
# Check External Secrets Operator
kubectl get pods -n external-secrets

# View ExternalSecret status
kubectl get externalsecret -A
kubectl describe externalsecret <name> -n <namespace>

# Verify 1Password Connect is running
kubectl get pods -n 1passwordconnect
```

## Differences from Manual Talos Bootstrap

If you previously used manual Talos configuration with `talhelper`:

| Manual Talos | Omni + Sidero Provider |
|-------------|------------------------|
| `talhelper genconfig` | Cluster provisioned in Omni UI |
| `talosctl bootstrap` | Omni handles bootstrap automatically |
| `talosctl apply-config` | Configuration managed in Omni |
| Manual ISO creation | Provider handles machine provisioning |
| `talosctl upgrade` | Upgrades managed in Omni UI |
| SOPS-encrypted secrets | Configuration stored in Omni |

**Benefits of Omni:**
- Web UI for cluster management
- Automated Talos upgrades
- Infrastructure provider integration (Proxmox, AWS, etc.)
- Built-in monitoring and metrics
- No need for local `talosctl` configuration
- Machine lifecycle management
- Cluster templates and machine classes

## Next Steps

After bootstrap is complete:

1. **Configure DNS** - Point your domain to cluster ingress
2. **Review Applications** - Check all apps in ArgoCD UI are synced
3. **Setup Monitoring** - Access Grafana dashboards
4. **Configure Backups** - Verify Longhorn backup configuration
5. **Deploy Your Apps** - Add applications to `my-apps/` directory

## Additional Documentation

- [Omni Setup Guide](omni/omni/README.md) - Deploy your own Omni instance
- [Main README](README.md) - Full cluster documentation
- [ArgoCD Configuration](docs/argocd.md) - GitOps patterns explained
- [Network Configuration](docs/network.md) - Cilium and Gateway API setup
- [Storage Configuration](docs/storage.md) - Longhorn and persistent volumes

## Support

For issues:
- **Talos/Omni**: Check [Talos documentation](https://www.talos.dev) and [Omni docs](https://omni.siderolabs.com/docs)
- **ArgoCD**: See [ArgoCD documentation](https://argo-cd.readthedocs.io/)
- **Cilium**: Visit [Cilium documentation](https://docs.cilium.io/)
