# Hermes Agent: the always-on agent in the cluster

**Purpose:** host Hermes Agent in this cluster, log in, and keep it running.
**Status:** current state. Argo CD syncs [`my-apps/development/hermes`](https://github.com/mitchross/talos-argocd-proxmox/tree/main/my-apps/development/hermes) as `my-apps-hermes`.
**Agent map:** [Hermes CLAUDE.md](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/development/hermes/CLAUDE.md) says which repo owns which change.

## What Hermes is

Hermes is an agent that runs when nobody is at a keyboard. It keeps a gateway process alive for cron jobs and chat platforms, remembers across sessions through Hindsight, and loads skills on demand.
[Paseo](paseo.md) is the workspace where you watch a coding agent work. Hermes is the scheduler, memory, and chat door in front of it.

```mermaid
flowchart LR
    Client[Browser or phone] --> TS[Tailscale via TrueNAS] --> GW[gateway-internal-technitium] --> Dash[Hermes dashboard :9119]
    Dash --> Gateway[Hermes gateway :8642]
    Gateway -->|qwen3.8-27b| LiteLLM --> vLLM
    Gateway --> Hindsight[(Hindsight memory)]
    Gateway --> Langfuse
    Git[my-apps/development/hermes] --> Argo[Argo CD] --> Gateway
    Gateway --> Vol[(hermes-data 10Gi)] --> Kopiur[Kopiur daily backup]
```

## How it is built

| Piece | Where | Notes |
|---|---|---|
| Image | `docker.io/nousresearch/hermes-agent`, pinned by digest in `deployment.yaml` | One container runs the gateway and the dashboard under s6-overlay |
| Pod | `deployment.yaml` | 1 replica, `Recreate`, starts as root, s6 drops to uid 10000 |
| Settings | `config/config.yaml` → ConfigMap → copied to `/opt/data/config.yaml` by `scripts/seed.sh` on every start | Model, memory provider, dashboard URL, plugin list |
| Plugins | `scripts/seed.sh` | Installs `hindsight`, `langfuse`, `homeassistant` into the volume on first start |
| Route | `httproute.yaml` | `gateway-internal-technitium` only; remote clients use Tailscale |
| Login | 1Password `hermes/dashboard_password` → Secret `hermes-secrets` | Username `vanillax` |
| Model | LiteLLM in-cluster, `qwen3.8-27b` | Free local model; traces land in Langfuse |
| Memory | Hindsight in-cluster, bank `hermes` | Key from 1Password `hindsight/tenant_api_key` |
| Volume | `pvc.yaml` | `hermes-data`, Longhorn, restore-before-bind, daily kopiur backup |
| Cluster access | `rbac.yaml`, `config/kube-in-cluster.yaml` | `kubectl` as ServiceAccount `hermes`, read-only (`hermes-viewer`), no secrets |
| Ops skill | `skills/homelab-ops/SKILL.md` | Six read-only checks and the digest format; copied to the volume on every start |
| Daily digest | `scripts/seed.sh` | Cron job `homelab-digest` at 08:00, skill `homelab-ops`, output under `cron/output/` until a chat platform exists |

## 1. Connect

1. Open `https://hermes.vanillax.me`. Away from home, turn on Tailscale first.
2. Sign in with username `vanillax` and the password from 1Password `homelab-prod` → `hermes`.
3. The **Status** page shows the gateway. The **Chat** tab opens a session.

## 2. Ask about the cluster

In the Chat tab, ask in plain words: "is the cluster healthy", "why is wyze-bridge degraded", "which backups failed this week".
Hermes loads the `homelab-ops` skill and runs the read-only `kubectl` checks. It names the Git directory that owns a fix; it cannot change the cluster.

Check the daily digest under **Cron** in the dashboard. Run it by hand with the **Trigger** button.

## 3. Add a chat platform

Add the bot token to 1Password, add it to `externalsecret.yaml`, and restart the pod.

| Platform | Secret keys |
|---|---|
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS` |
| Home Assistant | `HASS_TOKEN` (long-lived token from your HA profile page) |

## 4. Add provider logins

Provider logins are runtime state on the volume. Open the Chat tab and run `hermes auth add openai-codex --type oauth` for Codex. Claude through the Anthropic OAuth needs a Claude Max plan.

## Rollback

Revert the PR. Argo CD recreates the pod from the previous image. The volume keeps sessions and memories.
