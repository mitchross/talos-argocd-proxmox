# Migration to Official Helm Chart

## What Changed

### Before (Manual Manifests)
- Raw Kubernetes manifests (StatefulSet, Services, ConfigMap)
- Manual RPC secret generation
- DNS-based `bootstrap_peers` (not working reliably)
- Manual node connection required

### After (Official Helm Chart)
- Official Garage Helm chart (v0.7.2) from `https://garagehq.deuxfleurs.fr`
- Helm chart handles all Garage-specific configuration
- Automated layout initialization via Kubernetes Job
- Longhorn storage integration
- Gateway API HTTPRoutes for web access

## Files Structure

```
my-apps/media/garage/
├── namespace.yaml              # Namespace definition
├── httproute.yaml              # Gateway API routes (S3 API, Web UI)
├── init-layout-job.yaml        # Automated cluster initialization
├── kustomization.yaml          # Kustomize + Helm integration
├── README.md                   # Updated documentation
└── MIGRATION.md                # This file
```

## Deployment Method

**Kustomize with helmCharts:**
```yaml
helmCharts:
  - name: garage
    repo: https://garagehq.deuxfleurs.fr
    version: 0.7.2
    valuesInline:
      garage:
        replicationMode: "3"
      deployment:
        replicaCount: 3
      persistence:
        meta:
          storageClass: "longhorn"
        data:
          storageClass: "longhorn"
      ingress:
        s3:
          api:
            enabled: false  # Using Gateway API instead
```

## Post-Deployment

The `init-layout-job` automatically:
1. Waits for all 3 pods to be ready
2. Assigns each node to zone "home" with 100G capacity
3. Applies layout version 1
4. Verifies cluster status

## Services Created by Helm Chart

- `garage-s3-api` (port 3900) - S3 API endpoint
- `garage-s3-web` (port 3902) - Web UI for static websites
- `garage` (headless) - Inter-node communication

## HTTPRoute Configuration

Exposes services via Gateway API:
- `s3.vanillax.me` → S3 API
- `*.s3-web.vanillax.me` → Web UI (wildcard for buckets)

## Manual Commands (if needed)

```bash
# Check cluster status
kubectl exec -n garage garage-0 -- ./garage status

# Create admin key
kubectl exec -n garage garage-0 -- ./garage key create admin-key

# Create bucket
kubectl exec -n garage garage-0 -- ./garage bucket create my-bucket

# Grant permissions
kubectl exec -n garage garage-0 -- ./garage bucket allow my-bucket --read --write --key <KEY_ID>
```

## Benefits

✅ **Official Support**: Using maintained Helm chart from Garage project
✅ **Automated Setup**: Init job handles cluster configuration
✅ **GitOps Compliant**: Everything declarative in Git
✅ **Talos Compatible**: No manual configuration needed
✅ **Production Ready**: Proper replication and HA configuration
