# Garage S3 Storage

Garage is a lightweight, distributed S3-compatible object storage system designed for self-hosting.

## ✅ Deployment Status

**Fully operational and managed by ArgoCD!**

- ✅ 3 Garage pods running
- ✅ Cluster layout initialized (3 nodes, zone: home, 100G capacity each)
- ✅ HTTPRoutes configured for web access
- ✅ Auto-initialization via Kubernetes Job

## Architecture

- **Deployment**: ArgoCD Application → Garage Helm chart from Git
- **Replicas**: 3 StatefulSet pods for high availability  
- **Replication**: Mode 3 (3 copies of data)
- **Storage**: 
  - Meta: 1Gi per pod (LMDB metadata)
  - Data: 10Gi per pod (object storage)
  - StorageClass: `longhorn`
- **Networking**: Gateway API (HTTPRoute) - no Ingress
- **Auto-init**: Kubernetes Job assigns layout after pods are ready

## GitOps Deployment

This application uses **two ArgoCD Applications** working together, both defined in this directory:

### 1. `garage-helm` (Helm Deployment)
- **Defined in**: `garage-app.yaml` (this directory)
- **Purpose**: Deploys Garage Helm chart from Git repository  
- **Manages**: StatefulSet, Service, ConfigMap, PVCs
- **Configuration**: `values.yaml` (this directory)
- **Helm Chart Source**: https://git.deuxfleurs.fr/Deuxfleurs/garage.git

### 2. `my-apps-garage` (Supporting Resources)
- **Auto-discovered**: By ApplicationSet from `my-apps/media/garage/`
- **Purpose**: Manages cluster-specific resources
- **Manages**: Namespace, RBAC, HTTPRoutes, Init Job, and the garage-helm Application
- **Source**: Kustomize manifests in this directory

**Why two apps?**  
The `garage-helm` Application uses ArgoCD's multi-source feature to combine the Helm chart from Garage's Git repo with values from your GitHub repo. The `my-apps-garage` Application (via ApplicationSet) deploys everything including the `garage-helm` Application definition.

### Files in This Directory:
1. **`garage-app.yaml`**: ArgoCD Application for Helm chart deployment
2. **`values.yaml`**: Helm values (3 replicas, Longhorn storage, etc.)
3. **`rbac.yaml`**: ServiceAccount and RBAC for init job
4. **`init-layout-job.yaml`**: Kubernetes Job that automatically configures cluster layout
5. **`httproute.yaml`**: Gateway API routes for S3 API and web interface
6. **`namespace.yaml`**: Garage namespace
7. **`kustomization.yaml`**: Ties all resources together

### How It Works

```
ArgoCD syncs → Helm chart deploys → Pods start → Init Job runs → Cluster ready
```

The init job waits for all 3 pods to be ready, then:
- Collects node IDs from each pod
- Assigns all nodes to zone "home" with 100G capacity
- Applies layout version 1
- Verifies cluster status

**Everything is automatic!** Just commit and push changes to Git.

## Endpoints

- **S3 API**: `http://s3.vanillax.me` (port 3900)
- **Web Interface**: `http://s3-web.vanillax.me` (port 3902)
- **Internal DNS**: `http://garage-s3-api.garage.svc.cluster.local:3900`

## Manual Operations (if needed)

### Check Cluster Status

```bash
kubectl exec -n garage garage-0 -- ./garage status
```

### Create Keys and Buckets

```bash
# Create a key
kubectl exec -n garage garage-0 -- ./garage key create my-app-key

# Note the Key ID and Secret Key from output
KEY_ID="GK..."

# Create a bucket
kubectl exec -n garage garage-0 -- ./garage bucket create my-bucket

# Grant permissions
kubectl exec -n garage garage-0 -- ./garage bucket allow my-bucket --read --write --key $KEY_ID

# Get bucket info
kubectl exec -n garage garage-0 -- ./garage bucket info my-bucket
```

## Migrating from Manual Helm Install

If you previously installed Garage manually with `helm install`, you need to either:

**Option 1: Uninstall and let ArgoCD take over**
```bash
helm uninstall garage -n garage
# ArgoCD will redeploy automatically
```

**Option 2: Adopt existing resources**
```bash
# Label existing resources so ArgoCD can manage them
kubectl label -n garage statefulset/garage app.kubernetes.io/instance=garage-helm
kubectl label -n garage service/garage-s3-api app.kubernetes.io/instance=garage-helm
kubectl label -n garage service/garage-s3-web app.kubernetes.io/instance=garage-helm
```

### 4. Test S3 Access

```bash
# Install s3cmd or aws CLI
pip install s3cmd

# Configure s3cmd
s3cmd --configure

# Use these settings:
# Access Key: [from 'garage key info my-app-key']
# Secret Key: [from 'garage key info my-app-key']
# Default Region: garage
# S3 Endpoint: s3.vanillax.me
# DNS-style bucket: %(bucket)s.s3.vanillax.me

# Test
s3cmd ls s3://my-bucket/
```

## Configuration Notes

- **Replication Factor**: Set to 3 for data redundancy
- **Compression**: Level 1 enabled for bandwidth efficiency
- **Database Engine**: LMDB (lightweight, embedded)
- **Region**: Custom region "garage"
- **Discovery**: Kubernetes service-based (automatic peer detection via `garage-rpc` service)
- **RBAC**: ServiceAccount with role to read endpoints in garage namespace

## Scaling

To add more capacity:

```bash
# Scale StatefulSet
kubectl scale statefulset garage -n garage --replicas=4

# Get new node ID
NODE_3=$(kubectl exec -n garage garage-3 -- garage node id)

# Add to layout
kubectl exec -n garage garage-0 -- garage layout assign -z dc1 -c 10G $NODE_3
kubectl exec -n garage garage-0 -- garage layout apply --version 2
```

## Monitoring

Check cluster health:

```bash
kubectl exec -n garage garage-0 -- garage status
kubectl exec -n garage garage-0 -- garage stats
```

## Backup Strategy

Since Garage replicates data across nodes, ensure:
1. Regular snapshots of PVC volumes
2. Export critical bucket data using `s3cmd sync`
3. Backup metadata directory (`/mnt/meta`)

## Troubleshooting

### Pods not ready
```bash
kubectl logs -n garage garage-0
kubectl describe pod -n garage garage-0
```

### RPC connectivity issues
```bash
kubectl exec -n garage garage-0 -- garage status
# Check that all nodes are connected
```

### Layout not applied
```bash
kubectl exec -n garage garage-0 -- garage layout show
# Ensure layout version is applied
```

## References

- [Garage Documentation](https://garagehq.deuxfleurs.fr/)
- [Garage Cookbook](https://garagehq.deuxfleurs.fr/cookbook/)
- [S3 API Compatibility](https://garagehq.deuxfleurs.fr/documentation/reference-manual/s3-compatibility/)
