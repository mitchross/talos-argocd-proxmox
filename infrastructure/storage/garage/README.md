# Garage S3 Storage

Distributed S3-compatible object storage with Web UI.

## Architecture

- **Backend**: 3 Garage instances (StatefulSet) with replication factor 2
- **Storage**: Longhorn PVCs (3Gi meta + 30Gi data per instance = 90Gi total)
- **Web UI**: Management interface at `https://garage.vanillax.me`
- **S3 API**: Internal cluster access at `garage-s3.garage.svc.cluster.local:3900`

## Access

- **Web UI**: https://garage.vanillax.me
- **S3 Endpoint**: `http://garage-s3.garage.svc.cluster.local:3900`
- **S3 Region**: `garage`

## Post-Deployment

### Verify Cluster Status

```bash
kubectl exec -n garage garage-0 -- garage status
```

Expected: 3 connected nodes with configured layout

### Create S3 Bucket

Via Web UI or CLI:
```bash
kubectl exec -n garage garage-0 -- garage bucket create my-bucket
```

### Create Access Keys

Via Web UI or CLI:
```bash
kubectl exec -n garage garage-0 -- garage key create my-app
```

### Test S3 Access

Configure your S3 client:
- **Endpoint**: `http://garage-s3.garage.svc.cluster.local:3900`
- **Region**: `garage`
- **Access Key**: From Web UI
- **Secret Key**: From Web UI

## Troubleshooting

### Init Job Failed

```bash
kubectl logs -n garage job/garage-init
```

### Pods Not Ready

```bash
kubectl get pods -n garage
kubectl describe pod -n garage garage-0
kubectl logs -n garage garage-0
```

### Web UI Can't Connect

```bash
# Check secret synced
kubectl get externalsecret -n garage garage-secrets

# Check deployment logs
kubectl logs -n garage deployment/garage-webui
```

## Secrets

Managed via External Secrets Operator from 1Password item `s3-garage`:
- `rpc_secret`: RPC authentication between Garage pods
- `admin_token`: Admin API authentication for Web UI
