# One map for all your repos (the home repo)

This page shows how agents find their way across many repos. Every repo keeps its own code and rules. One extra repo, `home`, holds a map of all of them.
Read it if you work in more than a handful of repos with Claude Code, Codex, Pi or Hermes.
The idea comes from Matt Pocock's [The Home Repo Pattern](https://www.aihero.dev/the-home-repo-pattern).

!!! tip "This repo works without it"
    You do not need a home repo to use this repo. Its own `AGENTS.md` and `CLAUDE.md` carry every rule an agent needs here.
    The one line that mentions `home` says "if it exists". The `test_home_repo_optional.py` check fails CI if that ever changes.

## The problem

An agent sees only the repo it starts in.
Ask it, from an app repo, to deploy that app, and it does not know where the cluster repo lives or which folder deploys the app.
It either guesses, searches every folder on the disk, or asks you. The fix most people try is to copy the same notes into every repo. The copies then drift apart.

## How the home repo fixes it

1. Make one repo, `home`, with no app code in it.
2. Put a map in it: one line per repo with what it does, where it is cloned and how to clone it.
3. Give every agent one rule: "for work across repos, read `home` first."
4. Leave each repo's own rules in that repo. The map points; it never copies.

One map line looks like this:

```text
- radar-ng (weather radar app): git@github.com:mitchross/radar-ng.git.
  Deployed from my-apps/personal-projects/radar-ng in talos.
```

## Watch an agent use the map

<div class="pacman-demo"></div>

The same walk, as steps:

1. You ask, from the `radar-ng` repo: "deploy my change."
2. The agent's rules say "cross-repo work? Read `home` first."
3. It reads the map. The map says talos is the cluster and `radar-ng` deploys from `my-apps/personal-projects/radar-ng`.
4. It reads the talos rules: pull requests only, and Argo CD deploys.
5. It goes straight to the deploy folder, bumps the image and opens a pull request.

The map is about 40 lines. An agent reads it only when a job crosses repos, so a one-repo job costs nothing extra.

## Where each agent gets the rule

| Agent | Where it runs | How it learns about `home` |
|---|---|---|
| Claude Code, Codex, Pi | Your PC | A shared rules file that [chezmoi](https://www.chezmoi.io/) installs on each PC. chezmoi also clones `home` to `~/programming/home`. |
| Hermes | A pod in this cluster | `SOUL.md`. The seed script clones `home` to `/opt/data/workspace/home` on every start. |
| Claude Code, Codex | Inside the Hermes pod | `config/agent-rules.md`, which the seed installs as `~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md`. |

Repos live at `~/programming/<repo>` on a PC and at `/opt/data/workspace/<repo>` in Hermes. The map uses the same rule on both.

## What goes in `home`

| Put it in `home` | Keep it in the repo |
|---|---|
| The repo map | Anything the repo needs to work on its own |
| Skills you use in two or more repos | Skills for one repo only (for example `new-app` here) |
| Private notes that span repos | Build, test and deploy rules |

Keep `home` private if your map names private repos. Keep secrets out of it either way.

## Make your own

1. Create a private repo called `home`.
2. Add `AGENTS.md` that says what the repo is for, and `repo-map.md` with one line per repo.
3. Add one rule to each agent's global rules: "for work across repos, read `~/programming/home/AGENTS.md` first."
4. In any public repo, word the pointer as "if `~/programming/home` exists, read it". People who clone only that repo then lose nothing.
5. When you add, rename or archive a repo, update the map in the same change.

## Source of truth

- [`AGENTS.md`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/AGENTS.md): the optional pointer in this repo.
- [`my-apps/development/hermes/scripts/seed.sh`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/development/hermes/scripts/seed.sh): clones `home` for Hermes.
- [`scripts/tests/test_home_repo_optional.py`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/scripts/tests/test_home_repo_optional.py): keeps this repo usable without `home`.
