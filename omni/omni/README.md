# Omni self-hosted deployment

Deploy your own [Sidero Omni](https://github.com/siderolabs/omni) instance to
manage Talos Linux clusters, with full control over data and access.

This is a reference configuration. Every value in `omni.env.example` is a
placeholder. Copy it to `omni.env` and fill in your own domain, IPs, and
credentials.

Budget about an hour. Most of that is waiting for DNS propagation.

---

## Before you start, go get these three things

You cannot finish without all three. Get them now, before you start:

1. A domain name you control, with DNS hosted somewhere that has an API
   (Cloudflare here). You need `omni.yourdomain.com` to be yours.
2. An Auth0 account (free tier is fine). Omni has no built-in login. See
   below.
3. A machine with an SSD or NVMe, a static IP, and Docker installed.

### Words you will hit in this guide

| Term | What it means here |
| --- | --- |
| Talos | A stripped-down Linux built only for running Kubernetes. It has no SSH and no shell. You configure it through an API. |
| Omni | The control plane that manages Talos machines and clusters. This is what you are installing. |
| etcd | The database Omni stores everything in. It runs inside the Omni container. |
| SideroLink | A WireGuard VPN Omni builds to every machine it manages, so they can be anywhere. |
| DNS-01 challenge | A way to prove you own a domain to Let's Encrypt with a DNS record instead of a public web server. Needed because your Omni is probably not internet-facing. |
| Infrastructure provider | An add-on that lets Omni create machines for you (on Proxmox, libvirt, etc.) instead of you building them by hand. |

---

## Overview

Self-hosted Omni is a single container that holds a lot of state:

| Piece | Where it lives | Why it matters |
| --- | --- | --- |
| etcd (embedded) | `ETCD_VOLUME_PATH` | Cluster and machine state. Encrypted at rest with your GPG key. |
| SQLite | `SQLITE_STORAGE_PATH` | Machine logs, audit logs, discovery state. Grows to hundreds of MB. |
| GPG private key | `omni.asc` | Decrypts etcd. **Lose this and your data is gone forever.** |
| TLS cert | Let's Encrypt | Omni is HTTPS-only. Self-signed is not supported. |
| Identity provider | Auth0 / SAML / OIDC | Omni has no local user database. |

That last row surprises people. **Omni cannot run without an external identity
provider.** There is no built-in admin account and no password file. Set this
up before you start. It is the step most likely to block you.

### Version

`OMNI_IMG_TAG` in `omni.env` pins the version (currently `v1.13.2`). Read the
[release notes](https://github.com/siderolabs/omni/releases) before you upgrade.
Omni deprecates flags between minors.

**Keep `omnictl` on the same release as the server.** Mismatched versions fail
with obscure gRPC errors.

---

## Prerequisites

- [Prerequisites](../docs/PREREQUISITES.md)
- Docker Engine and the Compose plugin
- A real domain name you control. Omni writes its advertised URLs into the
  config it hands to every managed machine, so `localhost` will not work.
- A static IP on the host, because the WireGuard endpoint is a literal `ip:port`
- A DNS provider with an API, for the Let's Encrypt DNS-01 challenge
- An identity provider (Auth0 free tier is the least friction)

### Hardware

Hardware needs are modest. A NUC, a small VM, or a Raspberry Pi 5 all work.
Official images ship for both `amd64` and `arm64`.

**Storage is the one thing to get right.** Embedded etcd fsyncs constantly. Run
it on SSD or NVMe. An SD card or USB stick produces `apply entries took too
long` warnings and eventually corrupts the store. This is the most common way to
end up with a broken Omni.

8 GB RAM is comfortable. 4 GB is tight.

### Ports

| Port | Protocol | Purpose |
| --- | --- | --- |
| 443 | TCP | Web UI and API |
| 8090 | TCP | Machine API (Talos machines call in here) |
| 8100 | TCP | Kubernetes API proxy |
| 50180 | UDP | SideroLink WireGuard tunnel |

---

## Setup steps

### 1. SSL certificate

Use Certbot with DNS-01 validation. DNS-01 is required if Omni is not reachable
from the public internet, which is the normal homelab case.

```bash
sudo apt install -y certbot python3-certbot-dns-cloudflare
```

Create `cloudflare.ini` with a token scoped to Zone:DNS:Edit:

```ini
dns_cloudflare_api_token = your_token_here
```

```bash
chmod 600 cloudflare.ini    # certbot refuses world-readable credentials
```

```bash
sudo certbot certonly \
  --dns-cloudflare \
  --dns-cloudflare-credentials /full/path/to/cloudflare.ini \
  --dns-cloudflare-propagation-seconds 60 \
  -d omni.example.com
```

`scripts/setup-ssl.sh` wraps this.

**Set up renewal now.** Omni reads the cert only at startup, so renewal alone is
not enough. You must recreate the container:

```bash
sudo install -m 755 scripts/restart-omni-after-renewal.sh \
  /etc/letsencrypt/renewal-hooks/deploy/restart-omni-after-renewal.sh
sudo certbot renew --dry-run
```

Edit `DOMAIN_NAME` and `COMPOSE_DIR` at the top of that script first.

> **Checkpoint.** Do not continue until both work:
> ```bash
> sudo ls /etc/letsencrypt/live/omni.example.com/   # 4 .pem files
> sudo certbot renew --dry-run                      # "all simulated renewals succeeded"
> ```
> If the dry run fails, fix it now. A cert that cannot renew takes Omni
> down in 90 days.

### 2. GPG encryption key

Omni encrypts etcd at rest. It needs an RSA-4096 primary key with an
encryption subkey and no passphrase. The container starts unattended and
cannot answer a prompt.

Run `scripts/setup-gpg.sh` (interactive), or do it in batch:

```bash
EMAIL="you@example.com"

gpg --batch --passphrase "" --quick-generate-key \
    "Omni (Used for etcd data encryption) <$EMAIL>" rsa4096 cert never

FPR=$(gpg --list-secret-keys --with-colons "$EMAIL" | awk -F: '/^fpr:/ {print $10; exit}')

gpg --batch --passphrase "" --quick-add-key "$FPR" rsa4096 encr never

gpg --batch --yes --export-secret-key --armor "$EMAIL" > omni.asc
chmod 600 omni.asc
```

Verify you have both a `[C]` primary and an `[E]` subkey. Omni will not start
with only the primary:

```bash
gpg -K --with-subkey-fingerprint "$EMAIL"
```

```
sec   rsa4096 2026-08-13 [C]
      BFACCA07358DCA83F2202AFC682C13D03DF85479
uid           [ultimate] Omni (Used for etcd data encryption) <you@example.com>
ssb   rsa4096 2026-08-13 [E]
      D65067BEE68EC468A3C8C6944C09A49804706FEB
```

> ### Back up `omni.asc` right now
>
> Copy it somewhere off this machine, such as a password manager or an encrypted
> USB stick. Without this key your etcd data is permanently unreadable. There is
> no recovery path. It is the one irreplaceable file in the deployment.

> **Checkpoint.** `gpg -K` shows both a `[C]` line and an `ssb ... [E]`
> line, `omni.asc` exists and is `600`, and you have copied it somewhere off
> this machine. If you only see `[C]`, the subkey step failed. Redo it,
> or Omni will fail to start.

### 3. Prepare storage

```bash
sudo install -d -o "$USER" -g "$USER" -m 700 /etc/etcd
sudo install -d -o "$USER" -g "$USER" -m 755 /etc/omni/sqlite
```

Both are required. The SQLite path has been mandatory since Omni v1.4.0.
Omitting it fails at startup with:

```
config value ".storage.sqlite.path" or flag "--sqlite-storage-path": is required but was not set
```

### 4. Configure environment

```bash
cp omni.env.example omni.env
uuidgen                       # → OMNI_ACCOUNT_UUID
chmod 600 omni.env
```

Fill in your domain, IPs, cert paths, and Auth0 details. The comments in
`omni.env.example` annotate every required field.

**Use absolute paths.** A relative bind-mount path makes Docker silently create
an empty directory where a file belongs, and the resulting error does not
point at the cause.

### 5. Auth0 setup

1. Create a free tenant at [auth0.com](https://auth0.com)
2. **Applications → Create Application → Single Page Web Application**
3. Configure:
   - Allowed Callback URLs: `https://omni.example.com:443/oidc/callback`
   - Allowed Logout URLs: `https://omni.example.com:443/`
   - Allowed Web Origins: `https://omni.example.com:443`
4. Copy Domain and Client ID into `omni.env`

The SPA app type needs no client secret. If you find yourself copying a secret,
you picked the wrong app type.

A new tenant has the `google-oauth2` social connection enabled, so
"Continue with Google" works with no extra setup. Google provides the identity
and Auth0 brokers it. This is why nothing Google-specific appears in the config.

> `--auth-auth0-enabled` **cannot be set back to false** once enabled. On a
> fresh install you can choose freely. Afterwards you cannot.

### 6. Deploy

```bash
docker compose up -d
docker compose logs -f omni
```

First startup takes a minute or two. Omni initialises etcd and reconciles the
catalogue of every known Talos version.

A healthy startup prints many `reconcile succeeded` lines. You also see
warnings from the embedded etcd that are **normal and safe to ignore**:

```
Running http and grpc server on single port. This is not recommended for production.
it isn't recommended to use default name, please set a value for --name
etcdserver: failed to register grpc metrics
```

### 7. Verify

```bash
curl -o /dev/null -w '%{http_code}\n' https://omni.example.com/   # expect 200
ss -lntp | grep -E ':(443|8090|8100) '                            # three listeners
sudo ls /etc/etcd/                                                # 'member' dir exists
docker compose logs omni | grep -i '"level":"error"'
```

Then open `https://omni.example.com` and sign in. Your account must match
`INITIAL_USER_EMAILS`, which makes you admin automatically.

> **Checkpoint.** You see the Omni dashboard in your browser, logged in as
> yourself. **This finishes the installation.** Everything after this is
> configuration.
>
> Not there yet? Use the Troubleshooting section below. Its failures cover almost
> everything that goes wrong on a first install.

### 8. Auto-start on reboot

Nothing to do. The compose file sets `restart: unless-stopped`, which survives
reboots. Do **not** add a `@reboot` crontab entry. It races with Docker's own
restart handling.

---

## Updating Omni

For the Pi alongside Technitium and the native ARM64 ProxCenter build, use
[Pi service maintenance](../pi-services/README.md). These Docker services run
outside Talos. Merged Git configuration deploys them over SSH.

1. **Read the release notes.** Flags get deprecated between minors.
2. Back up first. **Downgrading is not supported**, because Omni migrates its
   etcd schema on first start of a new version:
   ```bash
   docker compose stop
   sudo tar czf ~/omni-state-backup-$(date +%F).tgz -C /etc etcd omni/sqlite
   # Keep omni.asc and omni.env in the protected backup as well.
   ```
3. Bump `OMNI_IMG_TAG` in `omni.env`, then:
   ```bash
   docker compose --env-file omni.env pull
   docker compose --env-file omni.env up -d
   ```
4. Watch the logs for deprecation warnings and act on them.
5. Update `omnictl` on your workstation to match.

### Known flag changes

| Change | Version | Action |
| --- | --- | --- |
| `--siderolink-api-advertised-url` → `--machine-api-advertised-url` | v1.10 | Old name still works but warns and is hidden from `--help` |
| `--sqlite-storage-path` became required | v1.4.0 | Omni will not start without it |
| EULA acceptance flags added | v1.7.1 | `--eula-accept-name` / `--eula-accept-email` |
| `imageFactory*` options deprecated | v1.10 | Superseded by `registries.factories.primary` (config-file only) |
| Config patches may no longer set Kubernetes CA / service account keys | v1.10 | Rejected on edit; existing unchanged patches keep working |

---

## Next steps

1. [Set up the Proxmox providers](../proxmox-providers/)
2. Create an infrastructure provider service account (see below)
3. Apply machine classes and provision a cluster

### Creating provider and service-account keys

**Use the CLI, not the Omni UI.** UI-generated PGP keys are incompatible with
the CLI's gopenpgp library and fail with `EdDSA verification failure`.

```bash
omnictl infraprovider create proxmox-hp-sff      # infrastructure provider
omnictl serviceaccount create talos-prod-sa --use-user-role   # cluster access
```

Each prints an endpoint and a key **shown exactly once**. Capture it
immediately and store it in your secret manager.

> As of v1.10, provider IDs must be valid DNS labels: lowercase letters,
> digits, and dashes only. `proxmox-hp-sff` is fine; `Proxmox_HP_SFF` is rejected.

The first `omnictl` command on a new machine triggers a browser auth flow. It
generates a local keypair, prints a URL, and blocks until you approve. The
approval window is short. If you get `rpc error: code = DeadlineExceeded`,
rerun the command for a fresh URL. The signed key caches in `~/.talos/keys/`.

---

## Troubleshooting

**Container exits immediately, complains about a mount**
A path in `omni.env` is relative or wrong, so Docker created a directory where a
file should be. Check `ETCD_ENCRYPTION_KEY`, `TLS_CERT`, `TLS_KEY`.

**`failed to validate config against JSON schema`**
A required flag is missing, and the message names it. Usually
`--sqlite-storage-path` or `--private-key-source`.

**Login redirects back to the login page**
Auth0 callback URLs do not match. They must include the scheme, the host, and
`:443` exactly as Omni advertises them.

**Machines connect then immediately drop**
`SIDEROLINK_WIREGUARD_ADVERTISED_ADDR` is wrong or unreachable. It must be a
literal IP the machines can route to, with UDP 50180 open.

**etcd warnings about slow applies**
Storage is too slow. See the hardware note. This is the SD-card failure mode,
and it worsens over time.

**Certificate errors**
```bash
sudo ls -la /etc/letsencrypt/live/omni.example.com/
sudo openssl x509 -in /etc/letsencrypt/live/omni.example.com/fullchain.pem -noout -dates
```

---

## Backup and recovery

| What | Why |
| --- | --- |
| `omni.asc` | **Irreplaceable.** Decrypts etcd. Keep an off-host copy. |
| `ETCD_VOLUME_PATH` | All cluster and machine state. |
| `omni.env` | Config, including the account UUID. |
| `/etc/letsencrypt` | Cert, account, renewal config. Reissuable, but convenient. |

```bash
docker compose stop
sudo tar czf omni-etcd-backup-$(date +%F).tar.gz -C /etc etcd
docker compose up -d
```

`SQLITE_STORAGE_PATH` holds logs and discovery state. It is large and
regenerable. Skip it unless you want audit history.

---

## Security notes

- `omni.asc` is the master encryption key. Treat it like a root credential.
- Enable MFA in your identity provider.
- Restrict access to Omni's ports with firewall rules.
- Certificates renew through the deploy hook. Verify with `certbot renew --dry-run`.
- Service account keys are shown once and default to a 1-year TTL.

## Licensing

Omni uses the Business Source License (BSL):

- Free for non-production use
- Production use requires a license. Contact [sales@siderolabs.com](mailto:sales@siderolabs.com)
