# Keeping Hermes's own toolset in Git

A reinstall or cluster rebuild must come back complete, so whenever a skill, MCP server or plugin is added, open a PR in the same session.

## Hub/catalog skill

Append `<owner/repo> <sha> <path> <category>` to `my-apps/development/hermes/scripts/external-skills.txt`. Take repo, path and pinned sha from `$HERMES_HOME/skills/.hub/lock.json` (`metadata.source_url`). The seed installs it under `skills/<category>/` while the hub put it at `skills/<name>/`, so after the merge rolls the pod, `hermes skills uninstall <name>` to avoid two copies.

## Skill Hermes wrote itself

Copy it (no dotfiles) into `my-apps/development/hermes/skills/library/<same rel path as on the volume>/`. The seed restores a library skill only when the volume lacks it, so live edits are never clobbered; refresh the Git copy by PR after big edits. Repo CI's Shell Script Lint runs on skill `scripts/*.sh` (use `cd ... || exit 1`, add `# shellcheck source=/dev/null` before `source "$VAR"`); fix the live and Git copies together. The `homelab-ops` skill's `references/` live only on the volume (Git ships its SKILL.md alone); add them to the library when they matter for a rebuild.

## MCP server

- Add it under `mcp_servers` in `config/config.yaml` with any token as `${env:NAME}`, and add `NAME` to `externalsecret.yaml`. Reuse an existing 1Password field when one fits (Cloudflare API token: `cloudflared-proxmox` → `api-token`); otherwise have the user create the field before merging, because a missing field fails the ExternalSecret sync.
- OAuth-only logins can't finish in the pod (the redirect lands on the pod); the Connectors page then shows "Needs authentication" — don't click Sign in. Use the vendor's API-token mode (Cloudflare: `https://mcp.cloudflare.com/mcp` with `Authorization: Bearer ${env:CLOUDFLARE_API_TOKEN}`).
- Cloudflare's MCP server rejects a zone-only token with 401 "Account token must resolve to exactly one Cloudflare account": it needs **Account Settings Read** with the account included. Test with a curl `initialize` POST before blaming config; after the user edits permissions, retest the same token (value unchanged; `mcp__cloudflare__*` tools appear without a restart).

## Hermes plugin

Add its name to the `for plugin in ...` loop in `scripts/seed.sh` (installs once on a fresh volume) AND to `plugins.enabled` in `config/config.yaml`, since the config copy overwrites what `hermes plugins enable` wrote. Installing on the live volume first is fine; it loads on the restart the merge triggers. Model routing: the `hermes-agent` skill's `references/model-routing.md`.

## Prove seed changes first

Extract the seed block into a script with stubbed `as_hermes`/`chown`, point it at a temp `HERMES_HOME`, and check it adds missing items and skips existing ones. Test `[ -e "$REPO_DIR/.git" ]`, not `-d`, because `.git` is a file in a worktree.
