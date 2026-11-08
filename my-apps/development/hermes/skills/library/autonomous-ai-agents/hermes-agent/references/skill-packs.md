# Installing third-party skill packs (Matt Pocock, P-Stack and similar)

Use when Mitch asks to install a published skill collection into Hermes, or to plan which skills each repo should use.

## Procedure

1. Inventory first. List what's already installed with `ls /opt/data/skills/*/`. Shallow-clone the pack into the scratch dir to see every skill name. Many popular packs overlap with skills Hermes already has, so only install the gaps unless Mitch says "all".
2. Prefer a harness-neutral mirror over a Cursor- or Claude-only original when one exists. For P-Stack that's `backnotprop/pstack`, because its rewrites drop Cursor transcript paths and the Task API.
3. Install each skill through the hub so it gets scanned and tracked for updates:
   `/opt/hermes/bin/hermes skills install <owner>/<repo>/<path-to-skill-dir> --category <pack-name> --yes`
   Put each pack in its own category folder (`pstack`, `matt-pocock`) so it stays easy to find, disable or remove as a group.
4. Run the loop in the background (`terminal(background=true)` and then `process_manage wait`). Each install takes ~10 s, so 60 skills overrun the 600 s foreground cap. Log one line per skill (`Installed`, `BLOCKED`, `Error`) to a scratch file, then grep that file for anything that isn't `Installed`.
5. Fix name clashes in the frontmatter. `--name` only renames the folder, not the `name:` field, so two skills named `tdd` still collide. Set the clashing one's frontmatter name to `<pack>-<skill>`, for example `pstack-tdd`.
6. When the hub says a skill "is listed in the skills-sh index, but its files no longer exist upstream", copy that skill folder from your git clone into the category dir, together with the pack's LICENSE.
7. Leave `BLOCKED` skills (a dangerous or caution scan verdict) uninstalled. Report them with the verdict and ask Mitch before you use `--force`.
8. Check whether Hermes honors `disable-model-invocation` (grep the Hermes source for it). If it doesn't, every installed skill's description loads into every turn. Tell Mitch, and point him at `hermes skills config` to switch off the ones he doesn't use. On pay-per-token providers such as OpenRouter, that per-turn cost is billed directly, so recommend a small starter set to anyone without a subscription plan.
9. Record the install, the blocked list and the renames in Hindsight.

## Where skills should live (the answer to "how do I run skills per repo")

- **Hermes (cluster):** skills in `/opt/data/skills` are global. Call one by name in chat. To load a repo's own `.agents/skills`, run `hermes skills trust <checkout>`.
- **Desktops (Claude Code, Codex, Pi on CachyOS and the Mac):** use the `dotfiles` repo (chezmoi) as the single catalog. All three agents read `~/.agents/skills` natively. Claude Code also gets symlinks in `dot_claude/skills`. Use symlinks, never copies, because Pi lets the first copy it finds win and silently shadows the catalog.
- **Repos:** keep only repo-specific skills in each repo's `.agents/skills`, such as `new-app` and `add-layer`. Don't copy general packs into every repo.
- Before saying a repo doesn't exist, check both GitHub (`mitchross`) and Gitea (`gitea.vanillax.me/vanillax`, API with `$GITEA_TOKEN`).
