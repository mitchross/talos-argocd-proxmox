# Prerequisites

Before deploying this stack, ensure you have the following in place.

## Infrastructure Requirements

### Proxmox Cluster
- **Proxmox VE** installed and accessible
- **User account** with VM management permissions (root@pam recommended for testing)
- **API access** to Proxmox API (typically port 8006)
- **Storage** configured (local-lvm, ZFS, Ceph, NFS, etc.)
- **Network** with DHCP or static IP allocation for VMs

### Ubuntu Host for Omni
- **Ubuntu 20.04+** (or any Docker-capable Linux distribution)
- **Docker** and **Docker Compose** installed
- **Minimum 2GB RAM** for Omni server
- **Persistent storage** for etcd data
- **Network connectivity** to Proxmox cluster

## Software Requirements

### Docker Installation

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add your user to docker group
sudo usermod -aG docker $USER
newgrp docker

# Install Docker Compose plugin
sudo apt-get update
sudo apt-get install docker-compose-plugin
```

Verify installation:
```bash
docker --version
docker compose version
```

### Certbot (for SSL certificates)

```bash
sudo snap install --classic certbot
sudo ln -s /snap/bin/certbot /usr/bin/certbot
```

### GPG (for etcd encryption)

Usually pre-installed on Ubuntu. Verify:
```bash
gpg --version
```

## Domain and DNS

### Domain Name
You need a domain name that you control. This starter kit uses Cloudflare for DNS validation, but any DNS provider supported by Certbot will work.

**Example**: `omni.yourdomain.com`

### DNS Provider Access
- **API Token** or credentials for automated DNS challenges
- Ability to create DNS records for certificate validation
- A record pointing to your Omni host IP

### Cloudflare Setup (Recommended)
1. Domain hosted on Cloudflare (free tier works)
2. API Token with `Zone:DNS:Edit` permissions
3. A record: `omni.yourdomain.com` → your Omni host IP

## Authentication Provider

Choose one authentication method:

### Option 1: Auth0 (Easiest)
- Create free Auth0 account at [auth0.com](https://auth0.com)
- No credit card required for development tier
- Social login support (GitHub, Google)

### Option 2: SAML Provider
Supported providers:
- EntraID / Azure AD
- Keycloak
- Okta
- Workspace ONE Access
- Unifi Identity Enterprise

### Option 3: OIDC
Any OpenID Connect compatible provider

## Network Requirements

### Ports Required

**Omni Server**:
- `443` - HTTPS API and Web UI
- `8090` - gRPC / Machine API (SideroLink)
- `8100` - Kubernetes proxy
- `8091` - Event sink
- `50180/udp` - WireGuard (SideroLink)

**Proxmox Provider**:
- Outbound HTTPS to Omni API
- Outbound HTTPS to Proxmox API (typically port 8006)

### Firewall Considerations
- Omni ports should be accessible from:
  - Your workstation (for Web UI)
  - Talos nodes (for SideroLink communication)
- Proxmox provider needs access to:
  - Omni API
  - Proxmox API

## Omni Account Setup

### Create Omni Account UUID
Generate a unique UUID for your account:
```bash
uuidgen
```
Save this - you'll use it as `OMNI_ACCOUNT_UUID`.

### Infrastructure Provider Key
After deploying Omni, you'll need to generate an infrastructure provider key through the Omni UI:
1. Navigate to **Infrastructure Providers**
2. Click **Create Provider**
3. Copy the generated key

⚠️ **Important**: This is an **Infrastructure Provider Key**, not a service account key.

## Storage Considerations

### Etcd Data
- Persistent storage required
- Recommended: `/etc/etcd` or similar
- Proper permissions: `chown 1000:1000`, `chmod 700`

### SSL Certificates
- Stored on host filesystem
- Mounted into Docker container
- Automatically renewed by Certbot

## Optional: GPU Support

If you plan to use NVIDIA GPUs:
- **Proxmox** host with GPU passthrough configured
- **NVIDIA GPU** (consumer or datacenter)
- **IOMMU** enabled in BIOS
- See the GPU machine classes in [machine-classes/](../machine-classes/) and the GPU patches in [cluster-template/patches/](../cluster-template/patches/) for Talos-specific requirements

## Pre-Flight Checklist

Before proceeding, verify:

- [ ] Proxmox cluster accessible
- [ ] Docker installed and running
- [ ] Domain name configured
- [ ] DNS provider API token ready
- [ ] Authentication provider chosen and configured
- [ ] Ports 443, 8090, 8091, 8100, 50180/udp available
- [ ] UUID generated for Omni account
- [ ] Storage directories created with correct permissions

## Next Steps

Once all prerequisites are met, proceed to:
1. [Deploy Omni](../omni/README.md)
2. [Setup Proxmox Provider](../proxmox-provider/)
