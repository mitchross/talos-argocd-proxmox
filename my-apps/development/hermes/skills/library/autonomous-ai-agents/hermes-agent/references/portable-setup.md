# Sharing Mitch's Hermes setup with someone else (no cluster)

Use when Mitch asks "how would a friend set up Hermes like mine", or asks for a starter kit or a guide anyone can follow on any hardware.

## The published guide comes first

A friend-facing guide already exists: `docs/domains/ai-gpu/hermes-one-computer.md` in `mitchross/talos-argocd-proxmox` ("Run Hermes on your PC"). Its siblings are `hermes.md` (this cluster) and `hermes-other-clusters.md` (someone else's Kubernetes, using the hermes-dev image). Link the right page instead of rewriting the steps in chat. When the setup changes (new plugin, new routing shape, skill list), update that page through a docs PR in the same session.

## Evaluate what is worth copying before explaining installation

1. Read the current SOUL, config, skill sources, relevant skill bodies and representative completed work. Pair this with the read-only usage procedure in `setup-audit.md`.
2. Explain the operating loop: short request → inspect and research → scoped work → tests and PR → human merge → live verification → save the reusable lesson into a skill. Treat the PR as a code-review gate, not permission for arbitrary terminal actions; destructive work still requires explicit approval.
3. Evaluate Ponytail, unslop/humanizer, audit/verifier/fix flows, Kanban, model routing and deterministic cron scripts. Explain what each improves and when a friend needs it; merely listing skill names does not teach the workflow.
4. Separate **copy**, **adapt**, **skip** and **not yet verified**. Recommend skills from demonstrated usefulness, not installation count alone; an unloaded specialist skill can still be valuable for an infrequent task.
5. Keep the beginner installation page intact. Put the evidence-backed workflow evaluation in a linked companion page when it would overwhelm the setup recipe. Read any existing companion before adding another page.

## The shape Mitch wants: normie PC first, skills and building as the focus

"Anyone, any hardware" means a normal person with one PC, not a homelab owner. Mitch rejected two heavier shapes in turn: Kubernetes, and Hermes itself in Docker Compose on a spare PC. The guide is:

1. Native installer on the reader's own PC, then `hermes model` → OpenRouter. Put cheap helper models (`auxiliary.*`) and `hermes fallback add` in the same short section.
2. Memory as a two-row choice. **Built-in memory is the default** (nothing to set up). Optional Hindsight runs as ONE Docker Compose service on localhost, with Hermes in `local_external` mode at `http://localhost:8888`. `local_embedded` gets one line, for readers without Docker.
3. **Most of the page is skills**: use them (`/skills`, `/skills browse`, a skill's name as a slash command), install packs, let Hermes write skills ("save what we just did as a skill", "update the skill so…"), write your own `SKILL.md` (with a small example), and share them.
4. **Building**: `AGENTS.md` at the repo root (Hermes falls back to `CLAUDE.md`), `hermes -w` worktrees, `hermes config set checkpoints.enabled true` plus `/rollback` (checkpoints are opt-in), and subagent routing.
5. Optional `SOUL.md`, then Verify, an Update/Undo/Backup table, and "what this leaves out".

Point cluster owners at `hermes-other-clusters.md`. Don't add a Hermes-container path unless someone asks for an always-on box.

## Where the source of truth lives

Read these instead of describing the setup from memory. Sparse-clone `mitchross/talos-argocd-proxmox` into scratch with `git sparse-checkout set my-apps/development/hermes`.

| Piece | Path under `my-apps/development/hermes/` |
|---|---|
| Main config (models, routing, aux, fallback) | `config/config.yaml` |
| Personality | `config/SOUL.md` |
| Hindsight plugin settings | `config/hindsight-hermes.json` |
| Pinned third-party skills (repo, sha, path, category, rename) | `scripts/external-skills.txt` |
| Skills Hermes wrote, kept in Git | `skills/library/<category>/<name>` |
| Plugin list and install commands | `scripts/seed.sh` |

## Shared content

- Skills come in three groups. Published packs install with `hermes skills install <owner>/<repo>/<path> --category <pack> --yes` (paths from `external-skills.txt`). Mitch-made general skills come from `skills/library/` (re-list the folder). Leave out homelab-only skills (`homelab-*`, Omni/Talos, node triage).
- Routing: `hermes plugins install advanced-delegation --enable`, then `fast` / `balanced` (default) / `deep` routes via `hermes delegation config` (`--show` prints them), all on OpenRouter. Depth is in `model-routing.md`.
- Map the pieces to drop: LiteLLM, Omni/talosctl, Pi SSH and egress, kopiur, the hosted HTTPS URL, `seed.sh`.
- Check every command against `hermes <cmd> --help` and `llms-full.txt`. State in the PR body that a compose file was not run when there is no Docker daemon to test it.

## Hindsight compose recipe (verified against upstream docs)

- Image `ghcr.io/vectorize-io/hindsight:<tag>` (amd64 + arm64; `-slim` variants exist). API 8888, web UI 9999, data volume `/home/hindsight/.pg0`, `shm_size: 1g`, `stop_grace_period: 75s`. Env: `HINDSIGHT_API_LLM_PROVIDER=openrouter`, `HINDSIGHT_API_LLM_API_KEY`, `HINDSIGHT_API_LLM_MODEL` (a cheap model; it only extracts facts). Publish on `127.0.0.1:8888:8888` so only that PC reaches it. Keys go in a compose `.env` next to the file.
- Hermes side: `hermes plugins install hindsight` (accept the provider prompt), then `hermes memory setup` → `local_external` → `http://localhost:8888`. This writes `$HERMES_HOME/hindsight/config.json`.
- Check image arches before claiming Pi support: anonymous `ghcr.io/token?scope=repository:<o>/<r>:pull` then GET the manifest index; the Docker Hub tags API lists `images[].architecture`.
- If someone does ask for Hermes itself in Docker: image `nousresearch/hermes-agent` (amd64 + arm64), `command: ["gateway", "run"]`, data at `/opt/data`, `HERMES_DASHBOARD=1` plus basic-auth env (a non-loopback dashboard refuses to start without an auth provider), and Desktop's remote gateway on port 9119. Run CLI commands as `docker compose exec -u hermes <service> hermes <cmd>`, because exec as root leaves root-owned files in the data dir.

## Pitfalls

- Put Hindsight settings in `$HERMES_HOME/hindsight/config.json` or set them with `hermes memory setup`. The plugin ignores a `memory.hindsight` section in `config.yaml`, so values there look set but do nothing (Mitch's own `config.yaml` still carries one; the seeded `config.json` is what works).
- Recommend 10–20 starter skills, not the full pinned list of about 100. Every installed skill adds its description to every turn, and on pay-per-token OpenRouter that text is billed each time.
- Never put OpenRouter model IDs or prices in the guide from memory. Use `<cheap-model-id>`-style placeholders and point at openrouter.ai/models or the `hermes model` picker.
- When restructuring a merged page, keep its filename so existing links and the published URL survive. Change the title and nav label instead, and fix any in-page `#anchor` links the restructure renames.
