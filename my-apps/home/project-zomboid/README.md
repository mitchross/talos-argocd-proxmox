# Project Zomboid Dedicated Server (Build 42)

## Connecting

- **Address:** `zomboid.vanillax.me`
- **Port:** `16261`
- **Password:** Stored in 1Password (`project-zomboid` > `server-password`)

From local network, you can also connect via `192.168.10.51:16261`.

## Architecture

- **Image:** `danixu86/project-zomboid-dedicated-server:latest-unstable`
- **Branch:** Build 42 multiplayer (unstable)
- **Service:** LoadBalancer on `192.168.10.51` (UDP 16261-16262, TCP 27015)
- **Storage:** 20Gi Longhorn PVC with daily VolSync backups
- **Memory:** 2-10GB JVM, 12GB container limit

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

## First Boot

First boot takes 5-10 minutes as the server loads all B42 assets and generates the world. The `sed` warnings about missing `.ini` are normal on first boot — the file is created after the JVM starts.

## Server Config

Server config is stored on the PVC at `/home/steam/Zomboid/Server/VanillaX.ini`. Changes to this file persist across restarts.
