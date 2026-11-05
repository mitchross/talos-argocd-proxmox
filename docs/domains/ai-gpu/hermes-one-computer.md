# Run Hermes without a cluster

**Purpose:** set up Hermes Agent with OpenRouter for models and Hindsight for long-term memory.
**Status:** guide. It copies the useful parts of [this cluster's Hermes](hermes.md) without Kubernetes.
**Scope:** one OpenRouter key and one computer. You need no GPU, LiteLLM or 1Password.
**Have a cluster?** Use [Run Hermes on another cluster](hermes-other-clusters.md) instead.

## Pick a path

| | Path A: your own computer | Path B: a spare PC with Docker |
|---|---|---|
| Good for | Trying Hermes. Chat when you sit at the computer. | An always-on agent: cron jobs, chat bots, use from any device. |
| Runs on | Linux, macOS (Apple Silicon), Windows, WSL2 | Any Linux box with Docker: old PC, mini PC, NAS, Pi 5 (amd64 or arm64) |
| Memory | Hindsight inside Hermes (`local_embedded`) | Hindsight in its own container (`local_external`) |
| You talk to it from | The same computer | Hermes Desktop or a browser on your laptop |

Both paths need an [OpenRouter](https://openrouter.ai) account with some credit and an API key.
Copy model ids from [openrouter.ai/models](https://openrouter.ai/models).

| This cluster | Without a cluster |
|---|---|
| Hermes in a Kubernetes pod | Hermes installed in `~/.hermes`, or one Docker container |
| Claude, Codex and local GPUs through LiteLLM | OpenRouter only |
| Hindsight server in the cluster | Hindsight embedded, or one Docker container |
| Config and skills seeded from Git | Set once with `hermes` commands |

## Path A: your own computer

### A1. Install Hermes

On Linux, macOS or WSL2, run:

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
```

On Windows or macOS, you can install the desktop package from the
[Hermes website](https://hermes-agent.nousresearch.com/) instead.
Other platforms: [Installation](https://hermes-agent.nousresearch.com/docs/getting-started/installation).

**Expected result:** `hermes --version` prints a version.

### A2. Connect OpenRouter

1. Run `hermes model`.
2. Pick **OpenRouter** and paste your API key.
3. Pick your main model. This model does the real work, so pick a strong one.

Hermes saves the key in `~/.hermes/.env`. Never put keys in `config.yaml`.

**Expected result:** `hermes chat -q "say hi"` answers.

### A3. Turn on memory with Hindsight

Hindsight remembers facts across chats, for example your name, your projects and past decisions.

1. Run `hermes plugins install hindsight`. Answer **yes** to "Use 'hindsight' as the memory provider now?".
2. Run `hermes memory setup` and pick **hindsight**.
3. Pick mode `local_embedded`. Memory stays on your computer and costs nothing extra.
4. Set the LLM provider to `openrouter` and pick a cheap, fast model.
   Hindsight uses this model only to pull facts out of chats.
   Embeddings and reranking run locally, so you need no other key.

On a small or slow computer, pick mode `cloud` instead.
Get a key at [ui.hindsight.vectorize.io](https://ui.hindsight.vectorize.io).

**Expected result:** `hermes memory status` shows `hindsight` as active.

Next: [Set up both paths](#set-up-both-paths).

## Path B: a spare PC with Docker

You run two containers on the spare PC: Hermes and Hindsight.
You then connect to Hermes from your laptop.

### B1. Make the folder and secrets

On the spare PC, run:

```bash
mkdir -p ~/hermes/data/hindsight && cd ~/hermes
openssl rand -base64 32   # dashboard password
openssl rand -base64 32   # session secret
```

Save this as `~/hermes/.env` and fill in your values:

```bash
OPENROUTER_API_KEY=<your OpenRouter key>
HINDSIGHT_MODEL=<cheap OpenRouter model id>
DASHBOARD_PASSWORD=<first secret>
DASHBOARD_SECRET=<second secret>
SERVER_IP=<spare PC IP, for example 192.168.1.50>
```

Docker Compose reads this file. Keep it out of Git.

### B2. Write the compose file

Save this as `~/hermes/compose.yaml`:

```yaml
services:
  hermes:
    image: nousresearch/hermes-agent:latest   # pin a version tag once it works
    command: ["gateway", "run"]
    restart: unless-stopped
    depends_on: [hindsight]
    ports:
      - "9119:9119"   # dashboard; Hermes Desktop connects here
    environment:
      HERMES_UID: "1000"   # your user id (`id -u`), so you can edit files in ./data
      HERMES_GID: "1000"   # your group id (`id -g`)
      HERMES_DASHBOARD: "1"
      HERMES_DASHBOARD_PUBLIC_URL: http://${SERVER_IP}:9119
      HERMES_DASHBOARD_BASIC_AUTH_USERNAME: admin
      HERMES_DASHBOARD_BASIC_AUTH_PASSWORD: ${DASHBOARD_PASSWORD}
      HERMES_DASHBOARD_BASIC_AUTH_SECRET: ${DASHBOARD_SECRET}
      HERMES_GATEWAY_BOOTSTRAP_STATE: running
      OPENROUTER_API_KEY: ${OPENROUTER_API_KEY}
    volumes:
      - ./data:/opt/data

  hindsight:
    image: ghcr.io/vectorize-io/hindsight:latest   # pin a version tag once it works
    restart: unless-stopped
    shm_size: 1g
    stop_grace_period: 75s
    ports:
      - "9999:9999"   # Hindsight web UI, optional
    environment:
      HINDSIGHT_API_LLM_PROVIDER: openrouter
      HINDSIGHT_API_LLM_API_KEY: ${OPENROUTER_API_KEY}
      HINDSIGHT_API_LLM_MODEL: ${HINDSIGHT_MODEL}
    volumes:
      - hindsight-data:/home/hindsight/.pg0

volumes:
  hindsight-data:
```

Inside Docker, Hermes reaches Hindsight at `http://hindsight:8888`.
Port 8888 stays closed to your network.

### B3. Point Hermes at Hindsight

Save this as `~/hermes/data/hindsight/config.json`:

```json
{
  "mode": "local_external",
  "api_url": "http://hindsight:8888",
  "bank_id": "hermes",
  "recall_budget": "mid"
}
```

Hindsight reads this file. It ignores a `memory.hindsight` section in `config.yaml`.

### B4. Start it

```bash
docker compose up -d
docker compose exec -u hermes hermes hermes plugins install hindsight
docker compose exec -u hermes hermes hermes model
```

1. Answer **yes** when the plugin install asks to use Hindsight as the memory provider.
2. In `hermes model`, pick **OpenRouter** and your main model. Paste the key if it asks.

**Expected result:** `docker compose exec -u hermes hermes hermes memory status` shows `hindsight` as active.

### B5. Connect from your laptop

1. Install Hermes Desktop on your laptop from the [Hermes website](https://hermes-agent.nousresearch.com/).
2. Open **Settings → Gateways → Add → Remote gateway**.
3. Enter `http://<spare PC IP>:9119`, user `admin` and the dashboard password.

A browser at `http://<spare PC IP>:9119` works too.

!!! warning "Keep it off the internet"
    Hermes can run commands on the spare PC. Do not forward port 9119 on your router.
    To reach it away from home, use a VPN such as Tailscale.

## Set up both paths

On Path B, put `docker compose exec -u hermes hermes` in front of each `hermes` command below.

### 1. Add skills

Skills are Markdown how-to files. Hermes loads a skill when a task matches it.
This cluster pins its skill list in
[`external-skills.txt`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/development/hermes/scripts/external-skills.txt).

Install skills one at a time with `owner/repo/path`:

```bash
hermes skills install mattpocock/skills/skills/engineering/tdd --category matt-pocock --yes
hermes skills install mattpocock/skills/skills/engineering/diagnosing-bugs --category matt-pocock --yes
hermes skills install mattpocock/skills/skills/productivity/grill-me --category matt-pocock --yes
hermes skills install backnotprop/pstack/skills/unslop --category pstack --yes
hermes skills install DietrichGebert/ponytail/skills/ponytail --category ponytail --yes
```

!!! warning "Start small"
    Every installed skill adds its name and description to every message.
    On OpenRouter you pay for that text on every turn.
    Start with 10–20 skills. Turn off the ones you do not use with `hermes skills config`.

Skip the homelab skills (`homelab-ops`, `homelab-triage` and similar). They only work with this cluster.

**Expected result:** `hermes skills list` shows the new skills.

### 2. Route subagents to cheap and strong models

Hermes can hand work to subagents. The `advanced-delegation` plugin gives each subagent a named route.
Easy work goes to a cheap model, and hard work goes to a strong one.
With OpenRouter, one key covers every route.

1. Run `hermes plugins install advanced-delegation --enable`.
2. Run `hermes delegation config`, pick the model map mode, and add three routes with provider `openrouter`:

```yaml
delegation:
  backend: model_map
  backends:
    model_map:
      default: balanced
      options:
        - name: fast
          description: "Cheap and quick. Lookups, summaries, first-pass triage."
          provider: openrouter
          model: <cheap-model-id>
        - name: balanced
          description: "Everyday work. Research, reading code, normal edits. Use when unsure."
          provider: openrouter
          model: <mid-model-id>
        - name: deep
          description: "Slow and careful. Hard debugging and design."
          provider: openrouter
          model: <strong-model-id>
          reasoning_effort: high
```

Hermes shows the main agent only the names and descriptions.

**Expected result:** `hermes delegation config --show` lists the three routes.

### 3. Save money on helper calls

Hermes makes small helper calls, for example to name chats. By default they use your main model.
Point them at the cheap model:

```bash
hermes config set auxiliary.title_generation.provider openrouter
hermes config set auxiliary.title_generation.model <cheap-model-id>
hermes config set auxiliary.skills_hub.provider openrouter
hermes config set auxiliary.skills_hub.model <cheap-model-id>
```

Add a backup model for when the main model is rate-limited or down:

```bash
hermes fallback add
```

### 4. Give it a personality (optional)

`SOUL.md` in the Hermes home sets how Hermes talks and works.
The home is `~/.hermes` on Path A and `~/hermes/data` on Path B.
Copy [this cluster's SOUL.md](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/development/hermes/config/SOUL.md)
as a start. Delete the homelab rules and keep the style rules you like.

## Verify

1. Run `hermes doctor`. Fix anything it marks as failed.
2. Run `hermes memory status`. Hindsight is active.
3. Tell Hermes a fact, start a new chat with `/new`, and ask about the fact.
4. Ask: "use a fast subagent to summarise this folder". The result names the `fast` route.

## Update, undo and back up

| Task | Path A | Path B |
|---|---|---|
| Update Hermes | `hermes update` | `docker compose pull && docker compose up -d` |
| Memory back to built-in only | `hermes memory off` | the same command, inside the container |
| Subagents back to the main model | `hermes config set delegation.backend default` | the same command, inside the container |
| Back up | copy `~/.hermes` and `~/.hindsight` | copy `~/hermes/data` and the `hindsight-data` volume |

## What this setup leaves out

This cluster also runs local GPUs behind LiteLLM, Omni and Talos access, SSH to other machines,
Kopiur backups and a hosted HTTPS address for the desktop apps.
Those parts exist only because Hermes runs in a cluster. You do not need them to start.
