# Hermes Agent: agent map

Read this before you change Hermes or the LiteLLM or Hindsight wiring it uses.
Human steps live in [docs/domains/ai-gpu/hermes.md](../../../docs/domains/ai-gpu/hermes.md).

## Which repo owns which change

| Change | Owner | Path |
|---|---|---|
| Deployment, env, volume, route, backup | talos | `my-apps/development/hermes/` |
| Hermes settings (model, memory, plugins, dashboard) | talos | `config/config.yaml`, copied over the volume on every start |
| Plugin set, skill copy, cron job | talos | `scripts/seed.sh` installs plugins once, copies `skills/homelab-ops/SKILL.md`, creates the `homelab-digest` cron job if missing |
| Cluster access | talos | `rbac.yaml` (read-only ClusterRole `hermes-viewer`), `config/kube-in-cluster.yaml`, kubectl from the `kubectl` init container |
| Image digest | talos | `deployment.yaml` `image:` (official `nousresearch/hermes-agent`) |
| Secret values | 1Password `homelab-prod` | items `hermes` (`dashboard_password`, `dashboard_secret`), `litellm`, `hindsight`, `home-assistant`, `paseo` (`password`) |
| Coding hand-off | talos | `config/config.yaml` `mcp_servers.paseo` → Paseo's `/mcp/agents` endpoint; Claude Code and Codex run in the Paseo pod, not here |
| Upstream behavior | `NousResearch/hermes-agent` | read the tagged source; do not fork |

## Rules

- Change Hermes through Git. Never edit `config.yaml` in the pod; the next start overwrites it.
- Runtime state stays on the volume: sessions, cron jobs, skills, memories, provider logins.
- The container starts as root. s6-overlay drops the gateway and dashboard to uid 10000; the mover uses the same uid.
- Keep `HERMES_DASHBOARD_PUBLIC_URL` equal to the route hostname, or dashboard auth redirects break.
- The dashboard refuses a non-loopback bind without an auth provider; keep the basic-auth secrets in the ExternalSecret.
- `kubectl` in the pod is read-only (`hermes-viewer`: get, list, watch; no secrets). Do not add write verbs; fixes go through Git.
- Keep Claude Code and Codex out of this image. Paseo owns the coding agents, their logins and the repo checkout; Hermes reaches them through the Paseo MCP server.
- A cron job edited in the dashboard keeps its edits; the seed only creates `homelab-digest` when the name is absent from `cron/jobs.json`.
