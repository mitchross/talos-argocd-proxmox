# Project Zomboid Dedicated Server (Build 42)

## Connecting

- **Address:** `zomboid.vanillax.me`
- **Port:** `16261`
- **Password:** Stored in 1Password (`project-zomboid` > `server-password`)

From local network, you can also connect via `192.168.10.51:16261`.

## Architecture

- **Image:** `indifferentbroccoli/projectzomboid-server-docker:latest`
- **Branch:** Build 42 multiplayer (unstable)
- **Service:** LoadBalancer on `192.168.10.51` (UDP 16261-16262, TCP 27015)
- **Storage:**
  - `zomboid-data` — 20Gi Longhorn PVC with daily VolSync backups (config + world saves)
  - `zomboid-server-files` — 15Gi Longhorn PVC (game installation, no backup — re-downloadable)
- **Memory:** 2-10GB JVM, 12GB container limit
- **Features:** Built-in RCON (rcon-cli), graceful shutdown via RCON, automatic game updates on start, health checks

## Networking

This is a UDP game server — no Gateway API or Cloudflare proxy.

- **Cloudflare:** DNS-only A record (grey cloud) pointing `zomboid.vanillax.me` to public IP
- **Firewalla:** Port forward UDP 16261, 16262 and TCP 27015 to `192.168.10.51`

## Secrets (1Password)

Item `project-zomboid` in `homelab-prod` vault:

| Field | Purpose |
|-------|---------|
| `admin-username` | In-game admin login |
| `admin-password` | In-game admin password |
| `server-password` | Password players need to join |
| `rcon-password` | RCON remote admin password |

## Server Config

Server config is managed via GitOps:
- `vanillax.ini` — main server settings (injected via ConfigMap)
- `vanillax_SandboxVars.lua` — sandbox/gameplay settings (injected via ConfigMap)
- `GENERATE_SETTINGS=false` — prevents the image from overwriting the ini with env var templates

Config files are copied to `/project-zomboid-config/Server/` on each start by an initContainer. The image force-sets `RCONPassword` from the `RCON_PASSWORD` env var.

## First Boot

First boot takes 5-10 minutes as SteamCMD downloads the game and the server generates the world.
