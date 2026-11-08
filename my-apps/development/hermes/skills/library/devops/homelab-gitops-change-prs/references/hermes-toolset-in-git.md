# Keeping Hermes's own toolset in Git

A reinstall or cluster rebuild must come back complete, so whenever a skill, MCP server or plugin is added, open a PR in the same session.

## Hub/catalog skill

Inspect `$HERMES_HOME/skills/.hub/lock.json` for provenance and compare it with Git's actual install inputs. Inspect `hermes skills snapshot export --help` and `hermes skills snapshot import --help` before choosing native snapshots versus explicit pins; test what the export includes, whether versions are immutable, and whether import needs the network. Do not assume a snapshot embeds skill contents or preserves local modifications. For explicit pins, append `<owner/repo> <sha> <path> <category>` to `my-apps/development/hermes/scripts/external-skills.txt` using verified source metadata. Compare installed contents with the pinned source and preserve local edits separately. Inspect actual destination paths before deduplicating; uninstalling by name can remove the desired copy, so treat removal as a separate approved action.

## Skill Hermes wrote itself

Copy it (no dotfiles) into `my-apps/development/hermes/skills/library/<same rel path as on the volume>/`. The seed restores a library skill only when the volume lacks it, so live edits are never clobbered; refresh the Git copy by PR after big edits. Repo CI's Shell Script Lint runs on skill `scripts/*.sh` (use `cd ... || exit 1`, add `# shellcheck source=/dev/null` before `source "$VAR"`); fix the live and Git copies together. The `homelab-ops` skill's `references/` live only on the volume (Git ships its SKILL.md alone); add them to the library when they matter for a rebuild.

## MCP server

- Add it under `mcp_servers` in `config/config.yaml` with any token as `${env:NAME}`, and add `NAME` to `externalsecret.yaml`. Reuse an existing 1Password field when one fits (Cloudflare API token: `cloudflared-proxmox` → `api-token`); otherwise have the user create the field before merging, because a missing field fails the ExternalSecret sync.
- OAuth-only logins can't finish in the pod (the redirect lands on the pod); the Connectors page then shows "Needs authentication" — don't click Sign in. Use the vendor's API-token mode (Cloudflare: `https://mcp.cloudflare.com/mcp` with `Authorization: Bearer ${env:CLOUDFLARE_API_TOKEN}`).
- Cloudflare's MCP server rejects a zone-only token with 401 "Account token must resolve to exactly one Cloudflare account": it needs **Account Settings Read** with the account included. Test with a curl `initialize` POST before blaming config; after the user edits permissions, retest the same token (value unchanged; `mcp__cloudflare__*` tools appear without a restart).

## Skills bundled with an executable or MCP server

1. Inspect upstream setup documentation and run the installer's documented dry-run before allowing it to write; installers may change MCP config as well as copy a skill. Use the supported connector-management tool for live MCP registration rather than hand-editing live config; keep the Git-owned deployment config as the rebuild source.
2. Locate bundled SKILL.md and references in the chosen release tag, including embedded assets such as `include_str!` sources. Copy instructions from that tag rather than the default branch, because unreleased instructions can name tools absent from the installed binary.
3. Verify the release asset's platform and published checksum before execution. If the deployment installs it during seeding, use a versioned durable path rather than a scratch path; keep the version, checksum, configured executable path and skill source aligned.
4. Test the executable directly, then test the MCP protocol: send `initialize`, `notifications/initialized`, `tools/list`, and one harmless `tools/call`. Match responses by JSON-RPC id and check `isError` and structured errors; a successful transport can still carry a failed tool call.
5. For dynamic toolsets, call the server's toolset-listing tool and use its returned identifiers rather than guessing names. Check advertised `tools.listChanged` support and re-list after enabling a toolset; server support alone does not prove the Hermes client refreshes its cached tools.
6. Verify registration through Hermes with tool discovery and a harmless call before declaring the integration usable. Report copied instructions, standalone runtime tests, Git persistence and Hermes registration as separate states. Confirm reload behavior from the installed Hermes docs/source before claiming a restart is required.
7. Describe rollback's persistent residue explicitly: reverting configuration does not remove the binary or installed skill from the volume. Keep removal separate and obtain approval before deleting it.

## Hermes plugin

Add its name to the `for plugin in ...` loop in `scripts/seed.sh` (installs once on a fresh volume) AND to `plugins.enabled` in `config/config.yaml`, since the config copy overwrites what `hermes plugins enable` wrote. Installing on the live volume first is fine; it loads on the restart the merge triggers. Model routing: the `hermes-agent` skill's `references/model-routing.md`.

## Port desktop rules to coding agents

1. Read the actual desktop/repo rules and the installed skills before summarizing them. Distinguish installed skills from instructions that load automatically; Hermes's skill loader does not establish what Claude Code or Codex reads.
2. Inspect `HOME`, `CODEX_HOME`, `CLAUDE_CONFIG_DIR` and symlink targets through the Hermes terminal. Resolve the effective instruction paths for each CLI against its current docs; the terminal's home can differ from the pod's home.
3. Keep shared coding rules in a Git-managed seed input, not in the image. Keep CLI binaries in the image. Configure Hermes's own standing rules separately through `SOUL.md`; writing a CLI's global file does not update Hermes.
4. Preserve the user's comment cap, concise PR format, smallest-complete-change rules and plain-writing rules in the global instruction summary. Link to full skills for depth, but do not rely on a path reference alone to enforce standing rules.
5. Inspect existing destination files and any plugin installer that may modify them before choosing overwrite behavior. Update the seed, ConfigMap inputs, agent map and human guide together.
6. Render the app, syntax-check changed shell code and build docs strictly. Exercise the seed block in a temporary home before rollout. After rollout, read the exact files through the Hermes terminal and run a small coding-agent task. Report file installation separately from demonstrated instruction loading or compliant output.
7. Test rollback against persistent volume state. Reverting a seed copy does not remove files already written to the volume; describe cleanup explicitly and obtain approval before deleting them.

## Recovery and drift checks

1. Classify each dependency by recovery source: image for executable tools, Git for declared setup, external secret store for credentials, durable volumes or service backups for history, and disposable scratch for caches/build output. Locate memory databases separately; backing up the agent's home does not necessarily back up its external memory service.
2. Inventory active, disabled, archived, bundled, hub-installed and locally authored skills separately. Compare sets programmatically and report exact differences; a hub lock entry is provenance, not proof that a skill is absent from Git. Preserve deliberate disabled/archive state rather than reactivating everything during recovery.
3. Test the scenario matrix in an isolated home: restart with existing state, empty home without backup, restored home, and unavailable registries. For a net-zero cluster or friend's fork, identify required external secret-store access and bootstrap prerequisites; do not promise offline recovery or a startup duration without testing it.
4. Keep registry failure fallback distinct from clean bootstrap. A PVC last-good cache can help a restart but cannot rescue an empty PVC; identify a packaged source or report that network access remains a bootstrap dependency. Test interruption and failed fetches without replacing the last-good contents with partial output.
5. Test local-edit precedence explicitly. A seed that skips existing files preserves runtime edits but does not update restored copies; document which layer wins and how Git changes reach an existing volume. Include modified bundled skills and required support files in the inventory.
6. Document which logins require manual reauthentication after a no-backup rebuild. Check this choice with the user rather than silently copying renewable OAuth credentials into static secret storage.
7. Emit a non-destructive drift report for installed skills without a declared recovery source. Keep drift detection separate from automatic deletion or reinstall, because either can destroy local edits.

## Native snapshot recovery pitfalls

- Use `hermes skills snapshot import <file> --force` with stdin closed for an unattended init; `--force` skips confirmation and caution prompts but does not bypass dangerous community-skill blocks. Test with the installed CLI rather than piping `yes` into production seed.
- Reconcile existing pins against actual native imports, not only the Hub lock: an existing `external-skills.txt` entry may be importable through `skills-sh/<owner>/<repo>/<path>` even when it has no current lock record. Keep every existing commit pin even when native import works; name-only snapshots are not immutable replacements. Compare all pins with snapshot entries and exclude overlapping installed names, including aliases, from imports. Record stale registry paths and unsupported name collisions separately.
- Preserve names and categories separately: the Hub lock is keyed by name, so two sources' `tdd`/`teach` skills can collide despite different categories. Restore Pstack aliases after import and keep the competing source pinned unless native import supports distinct lock identifiers.
- Preserve a locally saved skill when its official identifier becomes stale; upstream Notion's split into `notion-apps`/`notion-cli` does not reproduce the old `notion` instructions. A library fallback keeps the old skill without silently replacing it with a different one.
- Exercise cold, warm and offline recovery in a disposable home as uid 10000. Verify the complete snapshot count, pinned exceptions, edited-bundled precedence, missing-skill recovery and unchanged last-good archive. A PVC cache cannot recover an empty offline PVC; document that bootstrap dependency.

## Prove seed changes first

Extract the seed block into a script with stubbed `as_hermes`/`chown`, point it at a temp `HERMES_HOME`, and check it adds missing items and skips existing ones. Test `[ -e "$REPO_DIR/.git" ]`, not `-d`, because `.git` is a file in a worktree.
