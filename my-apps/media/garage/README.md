# Garage S3 Storage

Garage is a lightweight, distributed S3-compatible object storage system designed for self-hosting.

## Architecture

- **Replicas**: 3 StatefulSet pods for high availability
- **Storage**: 
  - Meta: 1Gi per pod (LMDB metadata)
  - Data: 10Gi per pod (object storage)
  - StorageClass: `openebs-hostpath`
- **Networking**: Gateway API (HTTPRoute)

## Endpoints

- **S3 API**: `http://s3.local.vanillax.net` (port 3900)
- **Web Interface**: `http://s3-web.local.vanillax.net` (port 3902)
- **Admin API**: `http://garage-admin.local.vanillax.net` (port 3903)

## Post-Deployment Setup

After deployment, you need to configure the Garage cluster layout:

### 1. Generate RPC Secret (First Time Only)

```bash
kubectl exec -n garage garage-0 -- garage node id
# Repeat for garage-1 and garage-2
```

### 2. Configure Cluster Layout

```bash
# Get node IDs
NODE_0=$(kubectl exec -n garage garage-0 -- garage node id)
NODE_1=$(kubectl exec -n garage garage-1 -- garage node id)
NODE_2=$(kubectl exec -n garage garage-2 -- garage node id)

# Assign capacity and zones
kubectl exec -n garage garage-0 -- garage layout assign -z dc1 -c 10G $NODE_0
kubectl exec -n garage garage-0 -- garage layout assign -z dc1 -c 10G $NODE_1
kubectl exec -n garage garage-0 -- garage layout assign -z dc1 -c 10G $NODE_2

# Show the new layout
kubectl exec -n garage garage-0 -- garage layout show

# Apply the layout
kubectl exec -n garage garage-0 -- garage layout apply --version 1

# Check cluster status
kubectl exec -n garage garage-0 -- garage status
```

### 3. Create Keys and Buckets

```bash
# Create a key
kubectl exec -n garage garage-0 -- garage key create my-app-key

# Create a bucket
kubectl exec -n garage garage-0 -- garage bucket create my-bucket

# Allow the key to access the bucket
kubectl exec -n garage garage-0 -- garage bucket allow my-bucket --read --write --key my-app-key

# Get bucket info
kubectl exec -n garage garage-0 -- garage bucket info my-bucket
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
# S3 Endpoint: s3.local.vanillax.net
# DNS-style bucket: %(bucket)s.s3.local.vanillax.net

# Test
s3cmd ls s3://my-bucket/
```

## Configuration Notes

- **Replication Factor**: Set to 3 for data redundancy
- **Compression**: Level 1 enabled for bandwidth efficiency
- **Database Engine**: LMDB (lightweight, embedded)
- **Region**: Custom region "garage"

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
