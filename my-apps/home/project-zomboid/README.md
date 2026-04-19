# Project Zomboid Dedicated Server (Build 42 unstable)

Self-hosted Zomboid multiplayer server for the homelab. UDP game traffic
(no HTTPRoute / Cloudflare tunnel — games don't speak HTTP), runs on a
standard worker node with Longhorn storage.

## Connecting

- **Address:** `zomboid.vanillax.me`
- **Port:** `16261` (UDP, the primary game port)
- **Password:** 1Password → `project-zomboid` → `server-password`
- **LAN alternative:** `192.168.10.51:16261`

## Architecture

```
 Internet
    │ (DNS: zomboid.vanillax.me → public IP, grey cloud — Cloudflare DNS-only)
    │
 Firewalla Gold
    │  forwards UDP 16261–16262, TCP 27015 → 192.168.10.51
    ▼
 Cilium LoadBalancer IP: 192.168.10.51
    │  (L2Announcements, advertised from the cluster)
    ▼
 Service: project-zomboid   (UDP 16261/16262 + TCP 27015)
    ▼
 Pod: project-zomboid       (single replica, Recreate, 180s grace for save)
    ├── init: steamcmd-update   → emptyDir steam-cache (SteamCMD pre-warm, see gotchas)
    ├── init: copy-config       → copies vanillax.ini + SandboxVars.lua into zomboid-data
    └── main: indifferentbroccoli/projectzomboid-server-docker:latest
          ├── /home/steam/steamcmd ← steam-cache (emptyDir, 1Gi)
          ├── /project-zomboid     ← zomboid-server-files PVC (60Gi, game install)
          └── /project-zomboid-config ← zomboid-data PVC (20Gi, **world saves + config — backup this**)
```

- **Image:** `indifferentbroccoli/projectzomboid-server-docker:latest` (do **not** pin to a digest — Steam pushes updates and pinned digests wedge SteamCMD).
- **Branch:** `SERVER_BRANCH=unstable` (Build 42 multiplayer).
- **Replicas:** 1. `Recreate` strategy (RWO PVCs — RollingUpdate deadlocks; see root `CLAUDE.md`).
- **Grace period:** 180s — the `preStop` hook needs time to `save` + `quit` cleanly over RCON before SIGKILL.

## Storage — why two PVCs

Zomboid's working directory mixes two kinds of data that have very
different backup needs:

| PVC                     | Size | Mount                          | Contains                                   | Backup? |
|-------------------------|------|--------------------------------|--------------------------------------------|---------|
| `zomboid-data`          | 20Gi | `/project-zomboid-config`       | `Server/*.ini`, `Server/*.lua`, world saves, player DB, logs | ✅ `backup: "daily"` label — VolSync snapshots via Kyverno |
| `zomboid-server-files`  | 60Gi | `/project-zomboid`              | SteamCMD game install (~7GB + staging), workshop mods       | ❌ re-downloaded from Steam on demand |

The 60Gi install PVC is deliberately **not** backed up — it's pure Steam
output. If it vanishes, `UPDATE_ON_START=true` re-downloads it on next
boot. Backing it up would waste 60Gi of VolSync storage for data that's
trivially reproducible.

The 20Gi data PVC is the **only** thing that matters for DR: world saves,
player inventories, admin config. The `backup: "daily"` label tells
Kyverno to generate VolSync `ReplicationSource` + friends automatically.

> ⚠️ **Never wipe `zomboid-data` without explicit confirmation** — that's
> irreversible loss of world saves. If you need a clean start, rename /
> snapshot first.

## Config — GitOps, not env templating

```
configmap.yaml (Kustomize-generated from two files):
├── vanillax.ini              ← server settings (name, ports, PvP, etc.)
└── vanillax_SandboxVars.lua  ← sandbox/gameplay settings

deployment.yaml initContainer `copy-config`:
└── copies both into /project-zomboid-config/Server/ inside zomboid-data PVC
```

- `GENERATE_SETTINGS=false` — critical. The image *will* overwrite
  `vanillax.ini` with env-var-driven templates if this isn't set.
- `RCONPassword` in the ini is force-overwritten by the image from the
  `RCON_PASSWORD` env var on every start (so rotating the secret in
  1Password just works).
- The ini/lua files are **plain files** in this dir, rendered into a
  ConfigMap by Kustomize at apply time — edit them directly and
  ArgoCD re-syncs.

## Secrets (1Password)

Item `project-zomboid` in the `homelab-prod` vault:

| Field             | Purpose                                 |
|-------------------|-----------------------------------------|
| `admin-username`  | In-game admin login                     |
| `admin-password`  | In-game admin password                  |
| `server-password` | Password players need to join           |
| `rcon-password`   | RCON remote admin password              |

Wired in via `externalsecret.yaml` → Secret `zomboid-secrets` →
`secretKeyRef` in the Deployment env.

## Mods & workshop items

Hardcoded in the Deployment env (see `deployment.yaml`, lines
`MODS` / `WORKSHOP_ITEMS`). To add/remove:

1. Edit `deployment.yaml` — both the `MODS` and `WORKSHOP_ITEMS` lists must be consistent.
2. Commit → ArgoCD syncs → Deployment rolls.
3. First boot after the change runs SteamCMD for ~5–10 min to pull the
   new workshop items. Players will be disconnected.

> ⚠️ **Known bad:** `ArcheryNexus` (workshop IDs `3653092321` / `3617854007`)
> was incompatible with Build 42 unstable as of 2026-04-09. If reports of
> "server crashes mid-session" start coming in after adding a new mod,
> check the server log for Lua errors first — that's where mod incompat
> shows up.

## Networking

UDP game server, no HTTP/TLS termination:

- **Cloudflare:** DNS-only A record (**grey cloud**) pointing
  `zomboid.vanillax.me` → public IP. The orange cloud proxies only HTTP;
  UDP game traffic needs the grey cloud to pass through.
- **Firewalla:** port-forward `UDP 16261`, `UDP 16262`, `TCP 27015` →
  `192.168.10.51`.
- **Service type:** `LoadBalancer` with Cilium L2Announcements giving it
  `192.168.10.51` on the LAN. No Gateway API / HTTPRoute involved.

## First boot — what to expect and how to watch

```bash
# Tail the server log
kubectl logs -n project-zomboid deploy/project-zomboid -f

# You'll see in order:
# 1. SteamCMD pre-warm in the init container (~30s)
# 2. "Update" phase — downloads the Build 42 unstable branch (~5–7 min on a fresh server-files PVC)
# 3. Workshop items download (~1–3 min)
# 4. World generation — JVM starts, Zomboid logs "GENERATE" / "MAP GEN" progress.
#    Fresh world gen takes ~2–5 min depending on map size.
# 5. "server is listening on port 16261" — ready.

# Check RCON is up (from inside the pod)
kubectl exec -n project-zomboid deploy/project-zomboid -- rcon-cli -c /home/steam/server/rcon.yml players
```

- `startupProbe` allows up to **10 minutes** before K8s kills the pod
  (`initialDelaySeconds=30 + periodSeconds=10 × failureThreshold=60`).
  A cold start on a fresh PVC fits comfortably; a world-gen hiccup past
  that will restart the pod — watch logs, don't just let it loop.
- `readinessProbe` uses `rcon-cli players` every 15s — once RCON returns
  cleanly, the Service routes traffic.
- `livenessProbe` just `pgrep`s the JVM every 30s.

### JVM memory

```
MEMORY_XMS_GB = 8    (initial heap)
MEMORY_XMX_GB = 16   (max heap)
container limit = 20Gi
```

Leaves ~4Gi of container headroom outside the JVM for SteamCMD, logs,
and native libs. Bump `MEMORY_XMX_GB` first if players report stutters
after a few hours — GC pressure on long-running Zomboid servers is the
usual culprit.

## Files

| File                     | Purpose                                                    |
|--------------------------|------------------------------------------------------------|
| `namespace.yaml`         | `project-zomboid` namespace                                |
| `pvc.yaml`               | Two PVCs (see above) — `zomboid-data` has `backup: "daily"` |
| `deployment.yaml`        | Single pod, two init containers, graceful-shutdown `preStop` |
| `service.yaml`           | LoadBalancer, UDP + TCP ports                              |
| `pdb.yaml`               | PodDisruptionBudget — don't evict this unceremoniously     |
| `externalsecret.yaml`    | Pulls `project-zomboid` item from 1Password                |
| `vanillax.ini`           | Server config (ini form)                                   |
| `vanillax_SandboxVars.lua` | Sandbox/gameplay tuning                                  |
| `kustomization.yaml`     | Generates the ConfigMap from the two config files          |

## Gotchas (keep these, they bite)

- **SteamCMD self-update bug:** requires the `steamcmd-update`
  initContainer to pre-warm SteamCMD into `/steam-cache` (an emptyDir)
  before the main container sees it. Without this, SteamCMD errors with
  `0x6`, `0x20006`, or `Missing configuration` on the validation pass.
- **`rcon-cli` path:** `/usr/bin/rcon-cli` — **not**
  `/home/steam/server/rcon-cli`. The config file at
  `/home/steam/server/rcon.yml` is correct though.
- **`server-files` PVC needs ≥60Gi.** Install is ~7GB, staging doubles
  that, then workshop items on top. 15Gi (old README) is too small.
- **Do NOT pin the image to a digest.** SteamCMD breaks when Steam
  pushes a version update; an untagged `latest` lets the container
  re-pull an up-to-date SteamCMD wrapper on reboot.
- **`GENERATE_SETTINGS=false` is load-bearing.** Otherwise the image
  clobbers your ini on every start.

## Backups & recovery

Daily VolSync backup of `zomboid-data` is handled automatically by
Kyverno (the `backup: "daily"` label triggers it). On cluster rebuild or
namespace recreate:

1. PVC Plumber checks if a backup exists for the PVC claim.
2. Kyverno injects `dataSourceRef` pointing at the VolSync
   `ReplicationDestination`.
3. The new PVC restores from backup before the pod starts.
4. World saves and config come back intact. `server-files` PVC is empty,
   `UPDATE_ON_START=true` re-downloads Zomboid from Steam (~10 min).

See `docs/pvc-plumber-full-flow.md` for the full flow.
