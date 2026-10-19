# Hermes Agent: agent map

Read this before you change Hermes or the LiteLLM, Hindsight, or Langfuse wiring it uses.
Human steps live in [docs/domains/ai-gpu/hermes.md](../../../docs/domains/ai-gpu/hermes.md).

## Which repo owns which change

| Change | Owner | Path |
|---|---|---|
| Deployment, env, volume, route, backup | talos | `my-apps/development/hermes/` |
| Hermes settings (model, memory, plugins, dashboard) | talos | `config/config.yaml`, copied over the volume on every start |
| Plugin set | talos | `scripts/seed.sh` installs each listed plugin once into the volume |
| Image digest | talos | `deployment.yaml` `image:` (official `nousresearch/hermes-agent`) |
| Secret values | 1Password `homelab-prod` | items `hermes` (`dashboard_password`, `dashboard_secret`), `litellm`, `hindsight` |
| Upstream behavior | `NousResearch/hermes-agent` | read the tagged source; do not fork |

## Rules

- Change Hermes through Git. Never edit `config.yaml` in the pod; the next start overwrites it.
- Runtime state stays on the volume: sessions, cron jobs, skills, memories, provider logins.
- The container starts as root. s6-overlay drops the gateway and dashboard to uid 10000; the mover uses the same uid.
- Keep `HERMES_DASHBOARD_PUBLIC_URL` equal to the route hostname, or dashboard auth redirects break.
- The dashboard refuses a non-loopback bind without an auth provider; keep the basic-auth secrets in the ExternalSecret.
- The pod has no cluster ServiceAccount token. Give it a read-only kubeconfig before any unattended cluster job.
