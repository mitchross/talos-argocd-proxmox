# Run Hermes on one computer

**Purpose:** set up Hermes Agent on one computer with OpenRouter for models and Hindsight for long-term memory.
**Status:** guide. It copies the useful parts of [this cluster's Hermes](hermes.md) without the cluster.
**Scope:** one machine, one API key. No Kubernetes, Docker, GPU, LiteLLM or 1Password.
**Have a cluster?** Use [Run Hermes on another cluster](hermes-other-clusters.md) instead.

| This cluster | Your computer |
|---|---|
| Hermes in a Kubernetes pod | Hermes installed in `~/.hermes` |
| Claude, Codex and local GPUs through LiteLLM | OpenRouter only |
| Hindsight server in the cluster (`local_external`) | Hindsight `local_embedded`, or Hindsight Cloud |
| Config and skills seeded from Git | Set once with `hermes` commands |

## What you need

- A computer that runs Linux, macOS (Apple Silicon), Windows or WSL2. An always-on mini PC or VPS also works.
- An [OpenRouter](https://openrouter.ai) account with some credit and an API key.
- No GPU. OpenRouter runs every model.

!!! note "Small machines"
    Hindsight's embedded mode runs a small database and local embedding models on your computer.
    On a Raspberry Pi or a small VPS, use Hindsight Cloud instead ([step 3](#3-turn-on-memory-with-hindsight)).

## 1. Install Hermes

On Linux, macOS or WSL2, run:

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
```

On Windows or macOS, you can install the desktop package from the
[Hermes website](https://hermes-agent.nousresearch.com/) instead.
Other platforms: [Installation](https://hermes-agent.nousresearch.com/docs/getting-started/installation).

**Expected result:** `hermes --version` prints a version.

## 2. Connect OpenRouter

1. Run `hermes model`.
2. Pick **OpenRouter** and paste your API key.
3. Pick your main model. This model does the real work, so pick a strong one.

Hermes saves the key in `~/.hermes/.env`. Never put keys in `config.yaml`.

**Expected result:** `hermes chat -q "say hi"` answers.

## 3. Turn on memory with Hindsight

Hindsight remembers facts across chats, for example your name, your projects and past decisions.

1. Run `hermes plugins install hindsight`. Answer **yes** to "Use 'hindsight' as the memory provider now?".
2. Run `hermes memory setup` and pick **hindsight**.
3. Pick a mode:
    - `local_embedded`: free. Memory stays on your computer.
    - `cloud`: no local load. Get a key at [ui.hindsight.vectorize.io](https://ui.hindsight.vectorize.io).
4. For `local_embedded`, set the LLM provider to `openrouter` and pick a cheap, fast model.
   Hindsight uses this model only to pull facts out of chats.
   Embeddings and reranking run locally, so you need no other key.

Hindsight reads `~/.hermes/hindsight/config.json`. It ignores a `memory.hindsight` section in `config.yaml`.

**Expected result:** `hermes memory status` shows `hindsight` as active.
Tell Hermes a fact, start a new chat with `/new`, and ask about the fact.

Full options: [Hindsight's Hermes guide](https://hindsight.vectorize.io/sdks/integrations/hermes).

## 4. Add skills

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

## 5. Route subagents to cheap and strong models

Hermes can hand work to subagents. The `advanced-delegation` plugin gives each subagent a named route,
so easy work goes to a cheap model and hard work goes to a strong one.
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

Copy model ids from [openrouter.ai/models](https://openrouter.ai/models). Hermes shows the main agent only the names and descriptions.

**Expected result:** `hermes delegation config --show` lists the three routes.

## 6. Save money on helper calls

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

## 7. Give it a personality (optional)

`~/.hermes/SOUL.md` sets how Hermes talks and works.
Copy [this cluster's SOUL.md](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/development/hermes/config/SOUL.md)
as a start. Delete the homelab rules and keep the style rules you like.

## Verify

1. Run `hermes doctor`. Fix anything it marks as failed.
2. Run `hermes memory status`. Hindsight is active.
3. Ask: "use a fast subagent to summarise this folder". The result names the `fast` route.
4. Run `hermes desktop` if you want the desktop app.

## Undo

| Undo | Command |
|---|---|
| Memory back to built-in only | `hermes memory off` |
| Subagents back to the main model | `hermes config set delegation.backend default` |
| Remove a skill or turn it off | `hermes skills config` |

## What this setup leaves out

This cluster also runs local GPUs behind LiteLLM, Omni and Talos access, SSH to other machines,
Kopiur backups and a hosted gateway for the desktop apps.
Those parts exist only because Hermes runs in a cluster. You do not need them on one computer.
To back up a single-computer setup, copy `~/.hermes` and, for embedded Hindsight, `~/.hindsight`.
