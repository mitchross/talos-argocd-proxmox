# Hermes Agent: agent map

Read this before you change Hermes or the LiteLLM or Hindsight wiring it uses.
Human steps live in [docs/domains/ai-gpu/hermes.md](../../../docs/domains/ai-gpu/hermes.md).

## Which repo owns which change

| Change | Owner | Path |
|---|---|---|
| Deployment, env, volume, route, backup | talos | `my-apps/development/hermes/` |
| Hermes settings (model, memory, plugins, dashboard) | talos | `config/config.yaml`, copied over the volume on every start |
| Plugin set, skill copy, cron job, repo checkout, memory hooks | talos | `scripts/seed.sh` installs plugins once, copies `skills/homelab-ops/SKILL.md`, creates the `homelab-digest` cron job if missing, clones the talos repo into `/opt/data/workspace`, writes `~/.hindsight/*.json` and installs the Claude Code and Codex Hindsight hooks |
| Cluster access | talos | `rbac.yaml` (read-only ClusterRole `hermes-viewer`), `config/kube-in-cluster.yaml`; `kubectl` ships in the image |
| Image | homelab-images | `images/hermes-dev/` (official Hermes plus `claude`, `codex`, `kubectl`, `gh`, `tmux`); talos pins the digest in `deployment.yaml` |
| Secret values | 1Password `homelab-prod` | items `hermes` (`dashboard_password`, `dashboard_secret`), `litellm`, `hindsight`, `home-assistant`, `paseo` (`password`), `claude-code` (`oauth_token`) |
| Coding agents | talos | `skills/homelab-ops/SKILL.md` runs `claude -p` or `codex exec` in this pod; `config/config.yaml` `mcp_servers.paseo` is the fallback |
| Codex and GitHub logins | volume | `codex login --device-auth` and `gh auth login` once from the dashboard terminal; state lives on `hermes-data` |
| Upstream behavior | `NousResearch/hermes-agent` | read the tagged source; do not fork |

## Rules

- Change Hermes through Git. Never edit `config.yaml` in the pod; the next start overwrites it.
- Runtime state stays on the volume: sessions, cron jobs, skills, memories, provider logins.
- The container starts as root. s6-overlay drops the gateway and dashboard to uid 10000; the mover uses the same uid.
- Keep `HERMES_DASHBOARD_PUBLIC_URL` equal to the route hostname, or dashboard auth redirects break.
- The dashboard refuses a non-loopback bind without an auth provider; keep the basic-auth secrets in the ExternalSecret.
- `kubectl` in the pod is read-only (`hermes-viewer`: get, list, watch; no secrets). Do not add write verbs; fixes go through Git.
- Claude Code and Codex come from the `hermes-dev` image, never from `npm install` on the volume. Bump them in homelab-images.
- The Claude token is `CLAUDE_CODE_OAUTH_TOKEN` from 1Password; Codex and `gh` logins are one-time device logins stored on the volume.
- A cron job edited in the dashboard keeps its edits; the seed only creates `homelab-digest` when the name is absent from `cron/jobs.json`.
