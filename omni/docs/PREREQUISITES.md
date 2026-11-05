# Prerequisites

Have the following in place before you deploy this stack.

## Infrastructure requirements

### Proxmox cluster
- Proxmox VE installed and reachable
- A user account with VM management permissions (root@pam recommended for testing)
- Access to the Proxmox API (typically port 8006)
- Storage configured (local-lvm, ZFS, Ceph, NFS, etc.)
- A network with DHCP or static IP allocation for VMs

### Ubuntu host for Omni
- Ubuntu 20.04+ (or any Docker-capable Linux distribution)
- Docker and Docker Compose installed
- At least 2GB RAM for the Omni server
- Persistent storage for etcd data
- Network connectivity to the Proxmox cluster

## Software requirements

### Docker installation

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

Verify the installation:
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

Ubuntu usually has GPG installed. Verify:
```bash
gpg --version
```

## Domain and DNS

### Domain name
You need a domain name that you control. This starter kit uses Cloudflare for DNS validation. Any DNS provider that Certbot supports works.

Example: `omni.yourdomain.com`

### DNS provider access
- An API token or credentials for automated DNS challenges
- Ability to create DNS records for certificate validation
- A record pointing to your Omni host IP

### Cloudflare setup (recommended)
1. Domain hosted on Cloudflare (free tier works)
2. API Token with `Zone:DNS:Edit` permissions
3. A record: `omni.yourdomain.com` → your Omni host IP

## Authentication provider

Choose one authentication method:

### Option 1: Auth0 (easiest)
- Create a free Auth0 account at [auth0.com](https://auth0.com)
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
Any OpenID Connect compatible provider.

## Network requirements

### Ports required

Omni server:
- `443` - HTTPS API and Web UI
- `8090` - gRPC / Machine API (SideroLink)
- `8100` - Kubernetes proxy
- `8091` - Event sink
- `50180/udp` - WireGuard (SideroLink)

Proxmox provider:
- Outbound HTTPS to Omni API
- Outbound HTTPS to Proxmox API (typically port 8006)

### Firewall considerations
- Omni ports must be reachable from:
  - Your workstation (for Web UI)
  - Talos nodes (for SideroLink communication)
- The Proxmox provider needs access to:
  - Omni API
  - Proxmox API

## Omni account setup

### Create Omni account UUID
Generate a unique UUID for your account:
```bash
uuidgen
```
Save it. You use it as `OMNI_ACCOUNT_UUID`.

### Infrastructure provider key
After you deploy Omni, generate an infrastructure provider key with `omnictl`:

```bash
omnictl infraprovider create proxmox-hp-sff
```

This prints an endpoint and a key. The key is **shown exactly once**. Copy it
straight into your secret manager.

**Warning: use the CLI, not the Omni UI.** UI-generated PGP keys are incompatible
with the CLI's gopenpgp library and fail with `EdDSA verification failure`.

**Warning:** This is an Infrastructure Provider Key, not a service account key.
The provider key lets the provider create machines. A service account key
(`omnictl serviceaccount create`) is for cluster access.

**Warning:** As of Omni v1.10, provider IDs must be valid DNS labels: lowercase
letters, digits, and dashes only. `proxmox-hp-sff` is fine; `Proxmox_HP_SFF` is
rejected.

## Storage considerations

### Etcd data
- Persistent storage required
- Recommended: `/etc/etcd` or similar
- Permissions: `chown 1000:1000`, `chmod 700`

### SSL certificates
- Stored on the host filesystem
- Mounted into the Docker container
- Renewed automatically by Certbot

## Optional: GPU support

If you plan to use NVIDIA GPUs:
- A Proxmox host with GPU passthrough configured
- An NVIDIA GPU (consumer or datacenter)
- IOMMU enabled in BIOS
- See the GPU machine classes in [machine-classes/](../machine-classes/) and the GPU patches in [cluster-template/patches/](../cluster-template/patches/) for Talos-specific requirements

## Pre-flight checklist

Before you continue, verify:

- [ ] Proxmox cluster accessible
- [ ] Docker installed and running
- [ ] Domain name configured
- [ ] DNS provider API token ready
- [ ] Authentication provider chosen and configured
- [ ] Ports 443, 8090, 8091, 8100, 50180/udp available
- [ ] UUID generated for Omni account
- [ ] Storage directories created with correct permissions

## Next steps

Once you meet all prerequisites, continue to:
1. [Deploy Omni](../omni/README.md)
2. [Setup Proxmox Provider](../proxmox-provider/)
