# Hermes Agent: agent map

Read this before you change Hermes or the LiteLLM or Hindsight wiring it uses.
Human steps live in [docs/domains/ai-gpu/hermes.md](../../../docs/domains/ai-gpu/hermes.md).

## Which repo owns which change

| Change | Owner | Path |
|---|---|---|
| Deployment, env, volume, route, backup | talos | `my-apps/development/hermes/` |
| Hermes settings (model, providers, memory, plugins, dashboard) | talos | `config/config.yaml`, copied over the volume on every start |
| Plugin set, skill copy, cron job, repo checkout, memory hooks | talos | `scripts/seed.sh` installs plugins once, copies `skills/homelab-ops/SKILL.md`, creates the `homelab-digest` cron job if missing, clones the talos repo into `/opt/data/workspace`, writes `~/.hindsight/*.json` (agent hooks) and `$HERMES_HOME/hindsight/config.json` (Hermes memory plugin) and installs the Claude Code and Codex Hindsight hooks |
| Personality and third-party skills | talos | `config/SOUL.md` copied on every start; `scripts/external-skills.txt` pins skill repos by commit |
| Omni, Talos, Pi | talos | 1Password `hermes-omni-sa` (Operator role) in `externalsecret.yaml`; `config/ssh_config`, `config/known_hosts`, `pi-egress.yaml` |
| Cluster access | talos | `rbac.yaml` (`hermes-viewer` reads, `hermes-operator` does day-to-day fixes), `config/kube-in-cluster.yaml`; `kubectl` ships in the image |
| Image | homelab-images | `images/hermes-dev/` (official Hermes plus `claude`, `codex`, `kubectl`, `omnictl`, `talosctl`, `gh`, `tmux`); talos pins the digest in `deployment.yaml` and `image-prepull.yaml`; bump both together |
| Secret values | 1Password `homelab-prod` | items `hermes` (`dashboard_password`, `dashboard_secret`), `hermes-omni-sa`, `litellm`, `hindsight`, `home-assistant`, `claude-code` (`oauth_token`) |
| Coding agents | talos | `skills/homelab-ops/SKILL.md` runs `claude -p` or `codex exec` in this pod; there is no fallback (Paseo is off, #3072) |
| Gitea push/clone | talos | `GIT_CONFIG_*` env in `deployment.yaml` serves `GITEA_TOKEN` (1Password `gitea/git_token`) for `https://gitea.vanillax.me` |
| Codex and GitHub logins | volume | `codex login --device-auth` and `gh auth login` once from the dashboard terminal; state lives on `hermes-data` |
| Upstream behavior | `NousResearch/hermes-agent` | read the tagged source; do not fork |

## Rules

- Change Hermes through Git. Never edit `config.yaml` in the pod; the next start overwrites it.
- Runtime state stays on the volume: sessions, cron jobs, skills, memories, provider logins.
- The terminal tool runs with `HOME=/opt/data/home` and a login-shell PATH, not the pod env. Tool state lives under `/opt/data`; the seed symlinks it into `/opt/data/home` and writes `.profile` with `/opt/agents/bin`. Test fixes through Hermes's own terminal, never only with `kubectl exec`.
- The container starts as root. s6-overlay drops the gateway and dashboard to uid 10000; the mover uses the same uid.
- Keep `HERMES_DASHBOARD_PUBLIC_URL` equal to the route hostname, or dashboard auth redirects break.
- The dashboard refuses a non-loopback bind without an auth provider; keep the basic-auth secrets in the ExternalSecret.
- `kubectl` in the pod can read everything except secrets (`hermes-viewer`) and do day-to-day fixes (`hermes-operator`): exec, port-forward, delete or evict pods, rollout restart, scale, run a Job, cordon/uncordon, change a Longhorn volume's copy count. It cannot create or edit app resources; config changes still go through Git, and Argo CD reverts any drift.
- Claude Code and Codex come from the `hermes-dev` image, never from `npm install` on the volume. Bump them in homelab-images.
- The Claude token is `CLAUDE_CODE_OAUTH_TOKEN` from 1Password; Codex and `gh` logins are one-time device logins stored on the volume.
- Model policy: Hermes brain = `claude-opus-5-5` at `agent.reasoning_effort: medium` (`config.yaml`; cron digest and Kanban workers on the default profile follow it); coding = `claude-sonnet-5-5 --effort high` for spelled-out fixes, `claude-opus-5-5 --effort high` or `gpt-6.1-sol` at high effort for investigation and design. `ANTHROPIC_MODEL` and `.codex/config.toml` (seed) pin the agents; the skill repeats the flags and reports the model on every hand-off.
- Qwen stays as `providers.litellm` so the picker keeps the free local option; the `gh` login adds GitHub Copilot.
- A cron job edited in the dashboard keeps its edits; the seed only creates `homelab-digest` when the name is absent from `cron/jobs.json`.
