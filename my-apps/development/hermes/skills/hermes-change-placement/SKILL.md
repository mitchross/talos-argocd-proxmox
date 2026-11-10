---
name: hermes-change-placement
description: Where a change to Hermes itself goes (image, talos Git, 1Password or the volume). Load before you install a tool, add a setting, skill, plugin, MCP server, cron job or secret, or when Mitch asks "is that in the image or in Kubernetes".
version: 1.0.0
platforms: [linux]
metadata:
  hermes:
    tags: [Hermes, Homelab, GitOps, Docker, Reproducibility]
    category: devops
---

# Where a change to Hermes goes

Hermes must rebuild from Git, the image and 1Password alone. A change that exists only on `/opt/data` is lost with the volume.

## The rule

| The change is | It goes in | How it reaches the pod |
|---|---|---|
| A program (CLI, runtime, compiler) | `mitchross/homelab-images`, `images/hermes-dev/Dockerfile` | Image build, then a digest bump in talos |
| A setting, rule, skill, plugin pin, MCP server, cron job or cron script | `mitchross/talos-argocd-proxmox`, `my-apps/development/hermes/` | `scripts/seed.sh` applies it on every pod start |
| A secret | 1Password, vault `homelab-prod` | `externalsecret.yaml` maps it into `hermes-secrets` |
| State Hermes produces (sessions, Kanban, memories, logins) | The `hermes-data` volume | The kopiur backup restores it. Nothing else does |

Caches are not state. `rustup`, `cargo`, Python venvs and build output are safe to lose.

## Add a program

1. Open a pull request on `homelab-images`. Pin the version with a `# renovate:` comment and an `ARG`. Verify the download against the publisher's checksum file.
2. Add the command to `images/hermes-dev/scripts/smoke.sh`.
3. Wait for Mitch to merge. The image build runs on `main`, not on the pull request.
4. Open a pull request on talos that sets the new digest in `deployment.yaml` and `image-prepull.yaml`. There are four references.

Never install a program under `/opt/data/tools` or with `curl` into the volume.

## Add a setting, skill or cron job

| Item | File in `my-apps/development/hermes/` |
|---|---|
| Model, fallback chain, MCP server, delegation route | `config/config.yaml` |
| A rule for you | `config/SOUL.md` |
| A rule for Claude Code and Codex in this pod | `config/agent-rules.md` |
| A cron job | One line in `cron/jobs.txt` and the script in `cron/`. Add the script to `kustomization.yaml` |
| A skill you made | `skills/library/<category>/<name>/` |
| A pinned third-party skill | `scripts/external-skills.txt` |

Open one pull request. Merging restarts the pod, and the seed applies the change.

## Add a secret

1. Ask Mitch to add the field in 1Password. You cannot write to the vault.
2. After the field exists, map it in `externalsecret.yaml`. An ExternalSecret that names a missing field fails to sync.
3. Read it in `config.yaml` as `${env:NAME}`.

## Check for drift

Read `/opt/data/logs/seed-drift.log`. The seed writes it on every start. It lists tools, plugins, cron scripts and cron jobs on the volume that Git and the image do not install.

For each line, move the item to the correct place with a pull request, or ask Mitch for a yes to delete it.

## Know these limits

- The seed copies a library skill only when the volume lacks it. An edit in Git does not replace the live copy.
- `config.yaml`, `SOUL.md`, this skill and `homelab-ops` are copied on every start. An edit on the volume is lost at the next restart.
- A cron job deleted in the dashboard returns at the next start unless `cron/jobs.txt` drops it too.
