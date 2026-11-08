# Hermes Agent: agent map

Read this before you change Hermes or the LiteLLM or Hindsight wiring it uses.
Human steps live in [docs/domains/ai-gpu/hermes.md](../../../docs/domains/ai-gpu/hermes.md).

## Which repo owns which change

| Change | Owner | Path |
|---|---|---|
| Deployment, env, volume, route, backup | talos | `my-apps/development/hermes/` |
| Hermes settings (model, providers, memory, plugins, dashboard) | talos | `config/config.yaml`, copied over the volume on every start |
| Agent build-output cleanup | talos | `scripts/gc-worktrees.sh` runs as the `worktree-gc` sidecar: it deletes `target/` (Cargo's, with `CACHEDIR.TAG`), `node_modules/` and `.next/` one or two levels into each `agent-worktrees` worktree and `/opt/data/workspace` checkout, only when no file inside changed for `IDLE_HOURS`, plus Cargo build dirs on scratch idle for `SCRATCH_IDLE_HOURS`. It never deletes a worktree, a checkout or a commit |
| Caches and Rust intermediates | talos | `pvc-scratch.yaml` (`hermes-scratch`, `/opt/scratch`, no snapshots, `backup-exempt`). The seed's `.profile` points `CARGO_BUILD_BUILD_DIR`, `XDG_CACHE_HOME` and the bun, npm and yarn caches there, so `hermes-data` snapshots and backups hold only state worth restoring |
| Kanban recovery | talos | `scripts/reconcile-kanban.py` runs during seed, before workers start. It blocks crashed ready tasks when the upstream PR guard still holds; the task keeps its PR links and history |
| Usage metrics | talos | `scripts/usage-exporter.py` runs as the `usage-exporter` sidecar: it reads `state.db` read-only and serves `hermes_model_*` totals on `:9464/metrics` (ServiceMonitor `hermes-usage`) for the Grafana "Hermes AI Split" board (`/d/hermes-ai-split`). If a Hermes update changes the `session_model_usage` table, the board's Exporter tile goes DOWN |
| Plugin set, skill copy, cron job, repo checkout, memory hooks | talos | `scripts/seed.sh` installs plugins once, copies `skills/homelab-ops/SKILL.md`, creates the `homelab-digest` cron job if missing, clones the talos repo into `/opt/data/workspace`, writes `~/.hindsight/*.json` (agent hooks) and `$HERMES_HOME/hindsight/config.json` (Hermes memory plugin) and installs the Claude Code and Codex Hindsight hooks |
| Personality, agent rules and third-party skills | talos | `config/SOUL.md` copied on every start; `config/agent-rules.md` installed as `~/.codex/AGENTS.md` and `~/.claude/CLAUDE.md` on every start; `skills/snapshot.json` lists registry skills, `scripts/external-skills.txt` pins the four stale-path/name-collision exceptions by commit (optional 5th column renames a clashing skill); `config.yaml` `skills.trusted_project_dirs` lists repo checkouts whose own skills load |
| Hermes-made skills | talos | `skills/library/<category>/<name>/`; the seed copies a skill only when the volume lacks it, never over a live copy |
| MCP servers | talos | `config.yaml` `mcp_servers`; tokens come from `hermes-secrets` as `${env:NAME}` (Cloudflare: `cloudflared-proxmox/api-token`); `rea` runs `npx -y rea-agents@<pin> mcp` (pin matches the `reverse-engineer-anything` library skill); `craft-anything` runs the release binary the seed installs under `/opt/data/tools/craft-anything-<ver>` (pin matches the `craft-anything` library skill) |
| Omni, Talos, Pi | talos | 1Password `hermes-omni-sa` (Operator role) in `externalsecret.yaml`; `config/ssh_config`, `config/known_hosts`, `pi-egress.yaml` |
| Who can reach the pod | talos | `ingress-policy.yaml`: the gateway and kubelet probes on `9119`, Prometheus on `9464`. The gateway's API server (`8642`) runs inside the pod but is not in the Service; to use it from Open WebUI or n8n, put `API_SERVER_KEY` in 1Password and allow the caller here |
| Cluster access | talos | `rbac.yaml` (`hermes-viewer` reads, `hermes-operator` does day-to-day fixes), `config/kube-in-cluster.yaml`; `kubectl` ships in the image |
| Image | homelab-images | `images/hermes-dev/` (official Hermes plus `claude`, `codex`, `kubectl`, `omnictl`, `talosctl`, `gh`, `tmux`); talos pins the digest in `deployment.yaml` and `image-prepull.yaml`; bump both together |
| Secret values | 1Password `homelab-prod` | items `hermes` (`dashboard_password`, `dashboard_secret`), `hermes-omni-sa`, `litellm`, `hindsight`, `home-assistant`, `claude-code` (`oauth_token`) |
| Coding agents | talos | `skills/homelab-ops/SKILL.md` runs `claude -p` or `codex exec` in this pod; there is no fallback |
| Gitea push/clone | talos | `GIT_CONFIG_*` env in `deployment.yaml` serves `GITEA_TOKEN` (1Password `gitea/git_token`) for `https://gitea.vanillax.me` |
| Codex and GitHub logins | volume | `codex login --device-auth` and `gh auth login` once from the dashboard terminal; state lives on `hermes-data` |
| Upstream behavior | `NousResearch/hermes-agent` | read the tagged source; do not fork |

## Rules

- Change Hermes through Git. Never edit `config.yaml` in the pod; the next start overwrites it.
- Runtime state stays on the volume: sessions, cron jobs, skills, memories, provider logins.
- The terminal tool runs with `HOME=/opt/data/home` and a login-shell PATH, not the pod env. Tool state lives under `/opt/data`; the seed symlinks it into `/opt/data/home` and writes `.profile` with `/opt/agents/bin`. Test fixes through Hermes's own terminal, never only with `kubectl exec`.
- The container starts as root. s6-overlay drops the gateway and dashboard to uid 10000; the mover uses the same uid.
- No pod `fsGroup`: Hermes resets `/opt/data` to `0700` on every login save, which made kubelet re-own the whole volume on the next start. The seed chowns what it writes, non-recursively under `home/`.
- Keep `HERMES_DASHBOARD_PUBLIC_URL` equal to the route hostname, or dashboard auth redirects break.
- The dashboard refuses a non-loopback bind without an auth provider; keep the basic-auth secrets in the ExternalSecret.
- `kubectl` in the pod can read workloads, nodes, storage and CRDs but not Secrets or ConfigMaps (`hermes-viewer`; the one exception is `kube-system/cilium-config`) and do day-to-day fixes (`hermes-operator`): exec, port-forward, delete or evict pods, rollout restart, scale, run a Job, cordon/uncordon, change a Longhorn volume's copy count, start an Argo CD sync or hard refresh (patch `.operation` or the refresh annotation on an Application). Exec works in every namespace, so it can read any Secret mounted in a pod. It cannot create or edit app resources; config changes still go through Git, and Argo CD reverts any drift.
- Claude Code and Codex come from the `hermes-dev` image, never from `npm install` on the volume. Bump them in homelab-images.
- The Claude token is `CLAUDE_CODE_OAUTH_TOKEN` from 1Password; Codex and `gh` logins are one-time device logins stored on the volume.
- Model policy: Hermes brain = `claude-opus-5-5` at `agent.reasoning_effort: medium` (`config.yaml`; the cron digest follows it). Delegated work defaults to Codex `gpt-6.1-sol` on the ChatGPT plan: `delegate_task` routes (`advanced-delegation` plugin: `local`/`fast`/`balanced`/`codex`/`deep`, default `codex`), Kanban cards (`--provider openai-codex --model gpt-6.1-sol`, per card, since workers otherwise run the profile's main model), coding hand-offs (`codex exec`) and `auxiliary.background_review`. Claude Code (`sonnet`/`opus` high) only on request or after Codex failed. Small auxiliary calls use `deepseek-flash`. `compression.threshold_tokens: 200000` keeps the 1M-window brain from replaying ~500k contexts. `ANTHROPIC_MODEL` and `.codex/config.toml` (seed) pin the agents; the skill repeats the flags and reports the model on every hand-off.
- Qwen stays as `providers.litellm` so the picker keeps the free local option; the `gh` login adds GitHub Copilot. Each Qwen model there carries `supports_vision: true`, which is what Hermes reads to send images natively. Don't set an `auxiliary.vision` backend: in `image_input_mode: auto` it forces text-only image handling for every model, Opus included.
- A cron job edited in the dashboard keeps its edits; the seed only creates `homelab-digest` when the name is absent from `cron/jobs.json`.
