# Omni Self-Hosted Deployment

This guide walks through deploying your own Omni instance on-premises.

## Overview

Omni is Sidero's SaaS platform for managing Talos Linux clusters. This deployment runs it on your own infrastructure with full control over data and access.

### Latest Version: v1.3.2 (November 2025)

The latest Omni release includes important stability improvements:
- ✅ **Better extension handling** - More reliable system extension management
- ✅ **Improved state management** - Reduced stale data issues
- ✅ **UI fixes** - Exposed services sidebar and scrollbar issues resolved
- ✅ **Enhanced MachineSet handling** - Better cluster reference management

**Recommended for new deployments**. Check [release notes](https://github.com/siderolabs/omni/releases) for the latest version.

## Prerequisites

Before starting, ensure you have completed:
- [Prerequisites](../docs/PREREQUISITES.md)
- Docker and Docker Compose installed
- Domain name with DNS configured
- Authentication provider configured

## Setup Steps

### 1. SSL Certificate Setup

We'll use Certbot with DNS validation to obtain a valid SSL certificate. Self-signed certificates are **not supported**.

#### Install Certbot with Cloudflare Plugin

```bash
sudo snap install --classic certbot
sudo ln -s /snap/bin/certbot /usr/bin/certbot
sudo snap set certbot trust-plugin-with-root=ok
sudo snap install certbot-dns-cloudflare
```

#### Create Cloudflare Credentials

Create a file at `~/omni/cloudflare.ini`:

```ini
dns_cloudflare_api_token = YOUR_CLOUDFLARE_API_TOKEN
```

Secure the file:
```bash
chmod 600 ~/omni/cloudflare.ini
```

#### Generate Certificate

Replace `omni.yourdomain.com` with your actual domain:

```bash
sudo certbot certonly \
  --dns-cloudflare \
  --dns-cloudflare-credentials ~/omni/cloudflare.ini \
  -d omni.yourdomain.com
```

Certificates will be stored in `/etc/letsencrypt/live/omni.yourdomain.com/`:
- `fullchain.pem` - Certificate
- `privkey.pem` - Private key

### 2. GPG Encryption Key Setup

Omni encrypts etcd data using GPG. Create a dedicated key:

#### Generate Primary Key

```bash
gpg --quick-generate-key \
  "Omni (Used for etcd data encryption) <your-email@example.com>" \
  rsa4096 \
  cert \
  never
```

Press **Enter** when prompted for a passphrase (no passphrase needed).

#### List Your Keys

```bash
gpg --list-secret-keys
```

Output will look like:
```
sec   rsa4096 YYYY-MM-DD [C]
      C750E169750F763F5D323DD9D878A13E01536F44
uid           [ultimate] Omni (Used for etcd data encryption) <your-email@example.com>
```

Copy the key fingerprint (long hex string).

#### Add Encryption Subkey

Replace `YOUR_KEY_FINGERPRINT` with the fingerprint from above:

```bash
gpg --quick-add-key YOUR_KEY_FINGERPRINT rsa4096 encr never
```

#### Verify Subkey

```bash
gpg -K --with-subkey-fingerprint
```

You should see both the primary key and an encryption subkey.

#### Export the Key

Replace with your email:

```bash
gpg --export-secret-key --armor your-email@example.com > omni.asc
```

### 3. Prepare Etcd Storage

Create and configure the etcd data directory:

```bash
sudo mkdir -p /etc/etcd
sudo chown -R 1000:1000 /etc/etcd
sudo chmod -R 700 /etc/etcd
```

**Optional**: If starting fresh, clear any existing etcd data:
```bash
sudo rm -rf /etc/etcd/*
```

### 4. Configure Environment Variables

Copy the example environment file:

```bash
cd omni/
cp omni.env.example omni.env
```

Create a symlink for Docker Compose auto-loading:

```bash
ln -s omni.env .env
```

**Why?** Docker Compose automatically loads `.env` for variable substitution in `docker-compose.yml`. The symlink allows you to keep the descriptive `omni.env` filename while enabling clean `docker compose up` commands without `--env-file` flags.

Edit `omni.env` with your values:

```bash
# Required: Omni Configuration
OMNI_ACCOUNT_UUID=your-uuid-here              # Generate with: uuidgen
NAME=omni-prod                                 # Deployment name
OMNI_IMG_TAG=v1.3.2                           # Omni version (latest stable - note the 'v' prefix)

# Required: Domain and Network
OMNI_DOMAIN_NAME=omni.yourdomain.com          # Your domain
BIND_ADDR=0.0.0.0:443                         # HTTPS bind address
MACHINE_API_BIND_ADDR=0.0.0.0:8090            # Machine API (SideroLink)
K8S_PROXY_BIND_ADDR=0.0.0.0:8100              # K8s proxy
EVENT_SINK_PORT=8091                          # Event sink

# Required: Advertised URLs (use your domain)
ADVERTISED_API_URL=https://omni.yourdomain.com
ADVERTISED_K8S_PROXY_URL=https://omni.yourdomain.com:8100/
SIDEROLINK_ADVERTISED_API_URL=https://omni.yourdomain.com:8090/
SIDEROLINK_WIREGUARD_ADVERTISED_ADDR=10.10.1.100:50180  # Your Omni host WireGuard IP

# Required: SSL Certificates
TLS_CERT=/etc/letsencrypt/live/omni.yourdomain.com/fullchain.pem
TLS_KEY=/etc/letsencrypt/live/omni.yourdomain.com/privkey.pem

# Required: Encryption
ETCD_VOLUME_PATH=/etc/etcd
ETCD_ENCRYPTION_KEY=/path/to/omni.asc         # Path to exported GPG key

# Required: Initial Admin
INITIAL_USER_EMAILS=admin@yourdomain.com      # Your admin email

# Authentication: Choose ONE method below

# Option A: Auth0
AUTH=--auth-auth0-enabled=true --auth-auth0-domain=YOUR_AUTH0_DOMAIN --auth-auth0-client-id=YOUR_AUTH0_CLIENT_ID

# Option B: SAML (example for Okta)
# AUTH=--auth-saml-enabled=true --auth-saml-url=https://your-org.okta.com/app/xxx/sso/saml

# Option C: OIDC
# AUTH=--auth-oidc-enabled=true --auth-oidc-issuer=https://your-oidc-provider.com --auth-oidc-client-id=YOUR_CLIENT_ID
```

### 5. Auth0 Setup (if using Auth0)

1. Create account at [auth0.com](https://auth0.com)
2. Create a new **Single Page Application**
3. Configure:
   - **Allowed Callback URLs**: `https://omni.yourdomain.com:443/oidc/callback`
   - **Allowed Logout URLs**: `https://omni.yourdomain.com:443/`
   - **Allowed Web Origins**: `https://omni.yourdomain.com:443`
4. Enable social connections (GitHub, Google, etc.)
5. Copy **Domain** and **Client ID** to `omni.env`

### 6. Deploy Omni

Start the container:

```bash
docker compose up -d
```

Check logs:
```bash
docker compose logs -f omni
```

Look for successful startup messages. The service should bind to configured ports.

### 7. Access Omni UI

Navigate to: `https://omni.yourdomain.com`

You should see the Omni login page. Sign in using your configured authentication provider.

### 8. Verify Deployment

Check that all services are healthy:

```bash
# Check container status
docker compose ps

# Check logs for errors
docker compose logs omni | grep -i error

# Verify ports are listening
sudo netstat -tulpn | grep -E '443|8090|8100|8091|50180'
```

## Auto-Start on Reboot

Add to your crontab to start Omni automatically on system reboot:

```bash
crontab -e
```

Add this line:
```
@reboot cd /path/to/omni && docker compose --env-file omni.env up -d
```

## Updating Omni

To update to a new version:

```bash
# Stop current version
docker compose down

# Update OMNI_IMG_TAG in omni.env
nano omni.env

# Pull new image and start
docker compose --env-file omni.env pull
docker compose --env-file omni.env up -d
```

## Troubleshooting

### Certificate Issues

If you get certificate errors:
- Verify DNS A record points to your host
- Check certificate files exist: `ls -la /etc/letsencrypt/live/omni.yourdomain.com/`
- Verify certificate is valid: `openssl x509 -in /etc/letsencrypt/live/omni.yourdomain.com/fullchain.pem -text -noout`

### Container Won't Start

Check logs for specific errors:
```bash
docker compose logs omni
```

Common issues:
- Port conflicts (something already using 443, 8090, etc.)
- Incorrect file paths in volumes
- Permission issues on etcd directory

### Can't Access UI

1. Verify container is running: `docker compose ps`
2. Check port binding: `sudo netstat -tulpn | grep 443`
3. Check firewall rules: `sudo ufw status` (if using UFW)
4. Verify DNS resolution: `nslookup omni.yourdomain.com`

### Authentication Fails

- Double-check Auth0/SAML/OIDC configuration
- Verify callback URLs match exactly
- Check that initial admin email matches your auth provider email

## Next Steps

Once Omni is deployed and accessible:
1. [Setup Proxmox Provider](../proxmox-provider/README.md)
2. Generate infrastructure provider key in Omni UI
3. Create machine classes
4. Provision your first cluster

## Backup and Recovery

### Backup Etcd Data

```bash
sudo tar -czf omni-etcd-backup-$(date +%Y%m%d).tar.gz /etc/etcd/
```

### Backup GPG Key

Keep your `omni.asc` file secure and backed up. Without it, you cannot decrypt etcd data.

## Security Notes

- Keep `omni.asc` secure - it's the master encryption key
- Rotate certificates before expiry (Let's Encrypt certs are valid 90 days)
- Use strong authentication (enable MFA in Auth0/SAML provider)
- Restrict network access to Omni ports using firewall rules
- Regular backups of etcd data

## Licensing

Omni uses the Business Source License (BSL):
- **Free** for non-production use
- **Production** use requires a license - contact [sales@siderolabs.com](mailto:sales@siderolabs.com)
