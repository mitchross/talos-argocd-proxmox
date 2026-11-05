# Run Hermes on your PC

**Purpose:** install Hermes Agent on your own computer, then use skills to build things with it.
**Status:** guide. It copies the useful parts of [this cluster's Hermes](hermes.md) without the cluster.
**Scope:** one computer and one OpenRouter key. You need no GPU, server or Kubernetes.
**Have a cluster?** Use [Run Hermes on another cluster](hermes-other-clusters.md) instead.

| This cluster | Your PC |
|---|---|
| Hermes in a Kubernetes pod | Hermes installed in `~/.hermes` |
| Claude, Codex and local GPUs through LiteLLM | OpenRouter only |
| Hindsight server in the cluster | Built-in memory, or Hindsight in Docker Compose |
| Skills seeded from Git | Skills you install, or Hermes writes |

## 1. Install Hermes

On Linux, macOS or WSL2, run:

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
```

On Windows or macOS, you can install the desktop app from the
[Hermes website](https://hermes-agent.nousresearch.com/) instead.
Other platforms: [Installation](https://hermes-agent.nousresearch.com/docs/getting-started/installation).

**Expected result:** `hermes --version` prints a version.

## 2. Connect OpenRouter

1. Create an [OpenRouter](https://openrouter.ai) account, add some credit and make an API key.
2. Run `hermes model`.
3. Pick **OpenRouter** and paste the key.
4. Pick your main model. This model does the real work, so pick a strong one.

Hermes saves the key in `~/.hermes/.env`. Never put keys in `config.yaml`.
Model ids are listed at [openrouter.ai/models](https://openrouter.ai/models).

**Expected result:** `hermes chat -q "say hi"` answers.

Hermes makes small helper calls, for example to name chats. Point them at a cheap model to save money:

```bash
hermes config set auxiliary.title_generation.provider openrouter
hermes config set auxiliary.title_generation.model <cheap-model-id>
hermes config set auxiliary.skills_hub.provider openrouter
hermes config set auxiliary.skills_hub.model <cheap-model-id>
hermes fallback add   # optional backup model for when the main one is down
```

## 3. Pick a memory

| Option | What you get | Setup |
|---|---|---|
| **Built-in (start here)** | Two small notes files: facts about you and about your setup | Nothing. It is on by default. |
| **Hindsight in Docker** | Long-term memory of every chat, with search across all of them | About 5 minutes, below |

Start with built-in memory. Add Hindsight later if Hermes forgets things you want it to keep.

### Optional: Hindsight in Docker Compose

1. Make a folder and save this as `~/hindsight/compose.yaml`:

    ```yaml
    services:
      hindsight:
        image: ghcr.io/vectorize-io/hindsight:latest   # pin a version tag once it works
        restart: unless-stopped
        shm_size: 1g
        stop_grace_period: 75s
        ports:
          - "127.0.0.1:8888:8888"   # API, for Hermes on this PC only
          - "127.0.0.1:9999:9999"   # web UI, optional
        environment:
          HINDSIGHT_API_LLM_PROVIDER: openrouter
          HINDSIGHT_API_LLM_API_KEY: ${OPENROUTER_API_KEY}
          HINDSIGHT_API_LLM_MODEL: ${HINDSIGHT_MODEL}
        volumes:
          - hindsight-data:/home/hindsight/.pg0

    volumes:
      hindsight-data:
    ```

2. Save `~/hindsight/.env` with your key and a cheap model. Hindsight uses the model only to pull facts out of chats.

    ```bash
    OPENROUTER_API_KEY=<your OpenRouter key>
    HINDSIGHT_MODEL=<cheap-model-id>
    ```

3. Start it with `cd ~/hindsight && docker compose up -d`.
4. Run `hermes plugins install hindsight`. Answer **yes** to "Use 'hindsight' as the memory provider now?".
5. Run `hermes memory setup`, pick **hindsight**, pick mode `local_external` and enter `http://localhost:8888`.

**Expected result:** `hermes memory status` shows `hindsight` as active.
Tell Hermes a fact, start a new chat with `/new`, and ask about the fact.

No Docker? Pick mode `local_embedded` in step 5 instead. Hermes then runs Hindsight itself.
To undo, run `hermes memory off`. Hermes goes back to built-in memory.

## 4. Skills

Skills are the main reason to use Hermes. A skill is a Markdown how-to file (`SKILL.md`).
Hermes sees every skill's name and description, and loads the full file only when a task matches.

### Use a skill

- `/skills` lists your skills. `/skills browse` shows the official optional ones.
- Every skill is also a slash command: `/tdd add a login form`.
- Or ask in plain words: "use the grill-me skill on my plan".

### Install skills other people wrote

Install one skill at a time with `owner/repo/path`. These are good first picks:

```bash
hermes skills install mattpocock/skills/skills/engineering/tdd --category matt-pocock --yes
hermes skills install mattpocock/skills/skills/engineering/diagnosing-bugs --category matt-pocock --yes
hermes skills install mattpocock/skills/skills/productivity/grill-me --category matt-pocock --yes
hermes skills install backnotprop/pstack/skills/unslop --category pstack --yes
hermes skills install DietrichGebert/ponytail/skills/ponytail --category ponytail --yes
```

This cluster's full list is in
[`external-skills.txt`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/development/hermes/scripts/external-skills.txt).
Skip the homelab skills (`homelab-ops`, `homelab-triage` and similar). They only work with this cluster.

!!! warning "Start small"
    Every installed skill adds its name and description to every message.
    On OpenRouter you pay for that text on every turn.
    Start with 10–20 skills. Turn off the ones you do not use with `hermes skills config`.

### Let Hermes write skills

Hermes learns. After a hard task, it offers to save what worked as a skill.
You can also ask: "save what we just did as a skill".
The next time a similar task comes up, Hermes loads that skill first.

When a skill gets a step wrong, say so: "update the skill so it does X".
Hermes fixes the skill, not only the current chat.

### Write your own skill

Make `~/.hermes/skills/<category>/<name>/SKILL.md`:

```markdown
---
name: deploy-blog
description: Use when publishing the blog. Builds and uploads it.
---

# Deploy the blog

## Procedure
1. Run `npm run build` in `~/code/blog`.
2. Upload `dist/` with `rsync -av dist/ me@host:/var/www/blog/`.

## Pitfalls
- The build fails on Node older than 20. Run `node -v` first.
```

Keep the description short and start it with "Use when". Hermes picks skills by their descriptions.
Start a new chat with `/new` to load a new skill.

### Share skills

A skill is a folder. Copy it to a friend, or keep `~/.hermes/skills` in a Git repo.
To publish one, push it to GitHub. Others install it with `hermes skills install <owner>/<repo>/<path>`.

## 5. Build things

### Work in a project

1. Open a terminal in your project folder and run `hermes`.
2. Add an `AGENTS.md` at the repo root. Write the build command, the test command and your rules in it.
   Hermes reads it at the start of every chat in that repo. It also reads `CLAUDE.md` when there is no `AGENTS.md`.
3. Ask for a change: "add a dark mode toggle, then run the tests".

### Stay safe while it edits

- Run `hermes -w` to work in a separate Git worktree. Your main checkout stays clean.
  Use it whenever two chats work on the same repo.
- Run `hermes config set checkpoints.enabled true` to snapshot files before risky edits.
  Then `/rollback` undoes the last change.

### Route subagents to cheap and strong models

Hermes can hand parts of a task to subagents.
The `advanced-delegation` plugin gives each subagent a named route,
so easy work goes to a cheap model and hard work goes to a strong one.

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
Ask "use a fast subagent to summarise this folder". The result names the `fast` route.

## 6. Give it a personality (optional)

`~/.hermes/SOUL.md` sets how Hermes talks and works in every chat.
Copy [this cluster's SOUL.md](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/development/hermes/config/SOUL.md)
as a start. Delete the homelab rules and keep the style rules you like.

## Verify

1. Run `hermes doctor`. Fix anything it marks as failed.
2. Run `hermes skills list`. Your skills are there.
3. In a project, ask Hermes to run the tests. It finds the command in `AGENTS.md`.

## Update, undo and back up

| Task | Command |
|---|---|
| Update Hermes | `hermes update` |
| Update Hindsight | `cd ~/hindsight && docker compose pull && docker compose up -d` |
| Back to built-in memory | `hermes memory off` |
| Subagents back to the main model | `hermes config set delegation.backend default` |
| Back up | copy `~/.hermes`, plus the `hindsight-data` Docker volume if you use it |

## What this setup leaves out

This cluster also runs local GPUs behind LiteLLM, Omni and Talos access, SSH to other machines,
Kopiur backups and a hosted address for the desktop apps.
Those parts exist only because Hermes runs in a cluster. You do not need them to start.

For the skills, flows and habits that make this setup work, and what not to copy, read
[How I use Hermes: what to copy](hermes-how-i-work.md).
