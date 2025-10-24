# Garage S3 Storage Design

**Date**: 2025-10-24
**Status**: Approved for Implementation
**Location**: `infrastructure/storage/garage/`

## Overview

Deploy Garage distributed S3-compatible object storage with Web UI for internal cluster storage needs. Garage provides geo-distributed, self-hosted S3 storage with replication factor 2 across 3 instances.

## Architecture

### Components

1. **Garage Backend**: StatefulSet with 3 replicas, S3 and Admin APIs
2. **Garage Web UI**: Web-based management interface
3. **Auto-initialization**: PostSync Job for cluster layout configuration

### Directory Structure

```
infrastructure/storage/garage/
├── backend/
│   ├── externalsecret.yaml    # 1Password: rpc_secret, admin_token
│   ├── configmap.yaml         # garage.toml configuration
│   ├── statefulset.yaml       # 3 replicas, Longhorn PVCs
│   ├── service-s3.yaml        # Port 3900 (S3 API)
│   ├── service-admin.yaml     # Port 3903 (Admin API)
│   ├── service-internal.yaml  # Headless for kubernetes_discovery
│   └── init-job.yaml          # PostSync hook (sync wave 1)
├── webui/
│   ├── deployment.yaml        # Web UI frontend (sync wave 2)
│   ├── service.yaml           # Port 3909 (named port)
│   └── httproute.yaml         # garage.vanillax.me
├── namespace.yaml
├── kustomization.yaml         # Lists all resources
└── README.md                  # Usage guide
```

## Storage Configuration

### PVC Sizing (per instance)
- **Metadata**: 3Gi (Longhorn, ReadWriteOnce)
- **Data**: 30Gi (Longhorn, ReadWriteOnce)
- **Total capacity**: 90Gi across 3 instances

### Replication
- **Replication Factor**: 2
- **Minimum instances**: 2
- **Failure tolerance**: 1 instance can fail
- **Data redundancy**: Each object stored on 2 instances

## Network Architecture

### Services

| Service | Port | Type | Purpose | Exposure |
|---------|------|------|---------|----------|
| `garage-s3` | 3900 | ClusterIP | S3 API | Internal only |
| `garage-admin` | 3903 | ClusterIP | Admin/Web API | Internal only |
| `garage-internal` | 3901 | Headless | RPC/Discovery | Internal only |
| `garage-webui` | 3909 | ClusterIP | Web UI | HTTPRoute |

### External Access

- **Web UI**: `https://garage.vanillax.me` (gateway-internal)
- **S3 API**: Internal cluster access only via `garage-s3.garage.svc.cluster.local:3900`

### Connection Flow

```
User → https://garage.vanillax.me
     → HTTPRoute (gateway-internal)
     → garage-webui Service (3909)
     → garage-webui Pod
     → garage-admin Service (3903)
     → Garage StatefulSet Pods

Apps → garage-s3.garage.svc.cluster.local:3900
     → garage-s3 Service
     → Garage StatefulSet Pods
```

## Configuration

### Garage Backend (garage.toml)

Key settings:
- `replication_factor = 2`
- `db_engine = "lmdb"`
- `metadata_dir = "/mnt/meta"`
- `data_dir = "/mnt/data"`
- `[kubernetes_discovery]` enabled for pod auto-discovery
- `[admin]` API on port 3903 with token from 1Password

### Web UI Environment Variables

- `API_BASE_URL`: `http://garage-admin.garage.svc.cluster.local:3903`
- `S3_ENDPOINT_URL`: `http://garage-s3.garage.svc.cluster.local:3900`
- `S3_REGION`: `garage`
- `API_ADMIN_KEY`: From ExternalSecret (1Password)

## Secrets Management

### 1Password Item: `s3-garage`

Two fields required:
1. **`rpc_secret`**: 32-byte hex string for RPC authentication between pods
   - Generate: `openssl rand -hex 32`
2. **`admin_token`**: 64+ character secure token for Admin API
   - Generate: `openssl rand -base64 48`

### ExternalSecret

Syncs from ClusterSecretStore `1password`:
- `rpc-secret` → Used in garage.toml
- `admin-token` → Used by Web UI and garage.toml admin section

## Deployment Flow

### ArgoCD Sync Waves

**Wave 0** (Default):
1. Namespace creation
2. ExternalSecret syncs from 1Password
3. ConfigMap with garage.toml
4. StatefulSet deploys (3 pods: garage-0, garage-1, garage-2)
5. Services created (s3, admin, internal)
6. Pods use kubernetes_discovery to find each other via headless service

**Wave 1** (PostSync Hook):
1. Init Job waits for all 3 pods to be ready
2. Connects each node to the cluster
3. Configures cluster layout with capacity and replication factor
4. Applies the layout
5. Cluster operational

**Wave 2** (Applications):
1. Web UI Deployment starts
2. Web UI Service with named port created
3. HTTPRoute configured for garage.vanillax.me
4. Web UI connects to Admin API

### ApplicationSet Discovery

- **Pattern**: `infrastructure/storage/*`
- **Application name**: `garage`
- **Namespace**: `garage` (auto-created)
- **Sync policy**: Automated with prune + selfHeal
- **Sync wave**: 1 (infrastructure tier)

## Post-Deployment Tasks

### 1. Verify Cluster Status

```bash
kubectl exec -n garage garage-0 -- garage status
```

Expected output: 3 connected nodes with configured layout

### 2. Access Web UI

Navigate to `https://garage.vanillax.me`
- Admin token automatically configured from 1Password
- Should see cluster status, buckets, and keys

### 3. Create First S3 Bucket

Via Web UI or CLI:
```bash
kubectl exec -n garage garage-0 -- garage bucket create my-bucket
```

### 4. Create Access Keys

Via Web UI or CLI:
```bash
kubectl exec -n garage garage-0 -- garage key create my-app-key
```

### 5. Test S3 Access

From application pods:
- **Endpoint**: `http://garage-s3.garage.svc.cluster.local:3900`
- **Region**: `garage`
- **Access Key**: From Web UI
- **Secret Key**: From Web UI

## Validation Checklist

Pre-deployment:
- [ ] 1Password item `s3-garage` created with `rpc_secret` and `admin_token`
- [ ] DNS record for `garage.vanillax.me` points to gateway (if needed)
- [ ] Longhorn storage class available and healthy

Post-deployment:
- [ ] All 3 Garage pods running and ready
- [ ] Init job completed successfully (check logs)
- [ ] `garage status` shows 3 connected nodes
- [ ] Cluster layout applied with replication factor 2
- [ ] Web UI accessible at `https://garage.vanillax.me`
- [ ] Can create buckets via Web UI
- [ ] Can create access keys via Web UI
- [ ] S3 API responds to requests from cluster

## Backup Strategy

**Longhorn PVC Backups**:
- Leverage Longhorn's built-in snapshot and backup features
- Both meta and data PVCs will be backed up
- Backs up raw data volumes (6 PVCs total: 3 meta + 3 data)

**Future Enhancement**:
- Garage supports S3-to-S3 replication
- Could replicate to external S3/Garage cluster for disaster recovery
- Document this approach if needed later

## Troubleshooting

### Init Job Fails

Check logs:
```bash
kubectl logs -n garage job/garage-init
```

Common issues:
- Pods not ready yet (job will retry)
- RPC secret mismatch
- Network connectivity between pods

### Web UI Can't Connect

Check:
1. ExternalSecret synced: `kubectl get externalsecret -n garage`
2. Secret created: `kubectl get secret garage-secrets -n garage`
3. Deployment logs: `kubectl logs -n garage deployment/garage-webui`
4. Admin API accessible: `kubectl exec -n garage garage-0 -- curl localhost:3903/health`

### Pods Not Discovering Each Other

Check:
1. Headless service exists: `kubectl get svc garage-internal -n garage`
2. StatefulSet DNS working: `kubectl exec -n garage garage-0 -- nslookup garage-internal.garage.svc.cluster.local`
3. RPC connectivity: `kubectl exec -n garage garage-0 -- garage node connect <node-id>`

## Dependencies

- **Longhorn**: Storage class for PVCs
- **External Secrets Operator**: 1Password integration
- **Gateway API**: HTTPRoute for Web UI
- **ArgoCD**: ApplicationSet discovery and sync

## Future Enhancements

1. **External S3 Access**: Add HTTPRoute for S3 API if needed
2. **S3 Web Hosting**: Enable port 3902 for static website hosting
3. **Monitoring**: Add ServiceMonitor for Prometheus metrics
4. **Horizontal Scaling**: Add more Garage instances (requires layout reconfiguration)
5. **Backup Replication**: Configure S3-to-S3 replication to external cluster

## References

- Garage Documentation: https://garagehq.deuxfleurs.fr/
- Garage Web UI: https://github.com/khairul169/garage-webui
- Docker Image: `dxflrs/garage:v2.1.0`
- Web UI Image: `khairul169/garage-webui:latest`
- Kubernetes Cookbook: https://garagehq.deuxfleurs.fr/documentation/cookbook/kubernetes/
