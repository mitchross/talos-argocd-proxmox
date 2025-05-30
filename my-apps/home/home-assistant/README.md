# Home Assistant Deployment

This directory contains the Kubernetes manifests for deploying Home Assistant on your K3s cluster.

## Features

- **Container Image**: Uses the official Home Assistant container image
- **Persistent Storage**: 10GB persistent volume for configuration and data
- **External Access**: HTTPRoute for external access via gateway
- **Configuration Management**: ConfigMap for managing configuration files
- **Host Network**: Enabled for device discovery and local integrations
- **Health Checks**: Liveness and readiness probes configured

## Access

Once deployed, Home Assistant will be available at:
- **Internal**: `http://home-assistant.home-assistant.svc.cluster.local:8123`
- **External**: `https://home-assistant.vanillax.me` (via HTTPRoute)

## Configuration

The basic configuration includes:
- Default integrations enabled
- Reverse proxy support for K8s ingress
- SQLite database for recorder
- Energy monitoring enabled
- Person integration enabled

Additional configuration can be done through the Home Assistant web UI or by updating the ConfigMap files.

## Initial Setup

1. Navigate to the Home Assistant web interface
2. Complete the initial setup wizard
3. Create your first user account
4. Configure integrations as needed

## Storage

- Configuration data is stored in a 10GB persistent volume
- Database files and logs are persisted across pod restarts
- Additional storage can be allocated by editing the PVC

## Security

- Container runs with privileged access for device integrations
- Trusted proxy configuration allows proper IP forwarding
- Host network access enables local device discovery

## Deployment

This deployment is managed by ArgoCD and uses Kustomize for resource management. 